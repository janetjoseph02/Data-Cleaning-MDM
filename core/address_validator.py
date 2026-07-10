# core/address_validator.py — 3-Tier Address Validation
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import urllib3

from config import (
    ADDRESS_COMPLETENESS_FIELDS,
    ADDRESS_PLACEHOLDER_PATTERNS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    GOOGLE_MAPS_API_BASE,
    PATTERNS,
)


class AddressValidator:
    """
    3-Tier address validation:
      Tier 1 — Reference file match
      Tier 2 — Structural checks (pincode regex, pincode→city/state/district, placeholder, completeness)
      Tier 3 — Google Maps API (on-demand, API key from config)

    FIX Issue 6:  Tier 2 now checks city against ALL matching rows (1:N support).
    FIX Issue 10: SSL cert handling, Tier 3 called as fallback not only on MATCHED,
                  location_type → confidence, retry logic, address dedup cache.
    FIX Bug G:    Address strings are deduplicated before geocoding to avoid
                  N sequential HTTP calls for the same address.
    """

    _PLACEHOLDER_RE = [
        re.compile(p, re.IGNORECASE) for p in ADDRESS_PLACEHOLDER_PATTERNS
    ]

    # FIX Issue 10 / Bug G: geocode result cache {address_str: (lat, lng, location_type)}
    _geocode_cache: Dict[str, Tuple] = {}

    # Google location_type → confidence boost
    _LOCATION_TYPE_CONFIDENCE = {
        "ROOFTOP": 100,
        "RANGE_INTERPOLATED": 85,
        "GEOMETRIC_CENTER": 70,
        "APPROXIMATE": 55,
    }

    def __init__(
        self,
        address_config: Dict,
        reference_files: Optional[Dict[str, pd.DataFrame]] = None,
        ssl_verify: bool = True,           # FIX Issue 10a
        geocode_rate_limit: float = 0.05,  # FIX Issue 10b: seconds between API calls
        max_geocode_per_run: int = 500,    # FIX Issue 10b: hard cap per pipeline run
    ):
        self.address_config = address_config
        self.reference_files = reference_files or {}
        self.ssl_verify = ssl_verify
        self.geocode_rate_limit = geocode_rate_limit
        self.max_geocode_per_run = max_geocode_per_run
        self._geocode_calls_this_run = 0
        self._last_geocode_time = 0.0

        # Suppress SSL warnings if verification is disabled (corporate proxies)
        if not ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def validate(self, df: pd.DataFrame, chunk_index: int = 0) -> pd.DataFrame:
        """Run address validation for all configured groups. Returns df with new columns."""
        df = df.copy()
        groups = self.address_config.get("groups", [])
        for group in groups:
            df = self._validate_group(df, group)
        return df

    # ─────────────────────────────────────────
    # Group-level validation
    # ─────────────────────────────────────────

    def _validate_group(self, df: pd.DataFrame, group: Dict) -> pd.DataFrame:
        prefix = group.get("output_prefix", group.get("group_name", "addr"))
        street_col = group.get("street_col")
        city_col = group.get("city_col")
        state_col = group.get("state_col")
        district_col = group.get("district_col")   # FIX Issue 6
        town_col = group.get("town_col")            # FIX Issue 6
        pincode_col = group.get("pincode_col")
        country_col = group.get("country_col")

        status_col = f"{prefix}_addr_match_status"
        confidence_col = f"{prefix}_addr_confidence"
        suggested_col = f"{prefix}_addr_suggested"
        completeness_col = f"{prefix}_addr_completeness_score"
        lat_col = f"{prefix}_lat"
        lng_col = f"{prefix}_lng"
        location_type_col = f"{prefix}_geocode_type"  # FIX Issue 10d

        df[status_col] = "UNMATCHED"
        df[confidence_col] = 0
        df[suggested_col] = np.nan
        df[completeness_col] = 0.0
        df[lat_col] = np.nan
        df[lng_col] = np.nan
        df[location_type_col] = np.nan

        for idx, row in df.iterrows():
            def _get(col):
                if not col:
                    return ""
                v = str(row.get(col, "") or "").strip()
                return "" if v.lower() in {"nan", "none", "null"} else v

            addr_parts = {
                "street": _get(street_col),
                "city": _get(city_col),
                "state": _get(state_col),
                "district": _get(district_col),  # FIX Issue 6
                "town": _get(town_col),           # FIX Issue 6
                "pincode": _get(pincode_col),
                "country": _get(country_col),
            }

            status, confidence, suggested, completeness = self._run_tiers(addr_parts, group)

            df.at[idx, status_col] = status
            df.at[idx, confidence_col] = confidence
            df.at[idx, suggested_col] = suggested
            df.at[idx, completeness_col] = completeness

            # FIX Issue 10c: call Tier 3 when confidence is low OR as explicit fallback,
            # not only when already MATCHED at high confidence
            should_geocode = (
                group.get("tier3_enabled") and
                group.get("tier3_api_key") and
                self._geocode_calls_this_run < self.max_geocode_per_run and
                not self._is_placeholder(" ".join(v for v in addr_parts.values() if v))
            )
            if should_geocode:
                lat, lng, loc_type, geo_conf = self._tier3_geocode(addr_parts, group)
                if lat is not None:
                    df.at[idx, lat_col] = lat
                    df.at[idx, lng_col] = lng
                    df.at[idx, location_type_col] = loc_type or ""
                    # FIX Issue 10d: update confidence using location_type
                    if geo_conf is not None:
                        df.at[idx, confidence_col] = max(confidence, geo_conf)
                    if status in ("UNMATCHED", "PARTIAL"):
                        df.at[idx, status_col] = "MATCHED"

        return df

    # ─────────────────────────────────────────
    # Tier orchestration
    # ─────────────────────────────────────────

    def _run_tiers(
        self,
        addr_parts: Dict[str, str],
        group: Dict,
    ) -> Tuple[str, int, str, float]:
        completeness = self._completeness_score(addr_parts, group)

        full_addr = " ".join(v for v in addr_parts.values() if v)
        if self._is_placeholder(full_addr) or not full_addr.strip():
            return "PLACEHOLDER", 0, "", completeness

        t1_status, t1_confidence, t1_suggested = self._tier1_match(addr_parts, group)
        if t1_confidence >= CONFIDENCE_HIGH:
            return t1_status, t1_confidence, t1_suggested, completeness

        t2_status, t2_confidence, t2_suggested = self._tier2_structural(addr_parts, group)
        if t2_confidence >= CONFIDENCE_MEDIUM:
            return t2_status, t2_confidence, t2_suggested, completeness

        if completeness < 0.5:
            return "INCOMPLETE", int(completeness * 50), "", completeness

        best_conf = max(t1_confidence, t2_confidence)
        best_status = t1_status if t1_confidence >= t2_confidence else t2_status
        best_suggested = t1_suggested or t2_suggested
        return best_status, best_conf, best_suggested, completeness

    # ─────────────────────────────────────────
    # Tier 1: Reference file match
    # ─────────────────────────────────────────

    def _tier1_match(self, addr_parts, group) -> Tuple[str, int, str]:
        ref_name = group.get("tier1_ref_name")
        ref_key_col = group.get("tier1_ref_key_col")
        ref_val_col = group.get("tier1_ref_val_col")

        if not ref_name:
            return "UNMATCHED", 0, ""

        ref_df = self.reference_files.get(ref_name)
        if ref_df is None or not ref_key_col or ref_key_col not in ref_df.columns:
            return "UNMATCHED", 0, ""

        lookup_key = addr_parts.get("pincode") or addr_parts.get("city", "")
        if not lookup_key:
            return "UNMATCHED", 0, ""

        match_rows = ref_df[ref_df[ref_key_col].astype(str).str.strip() == lookup_key]
        if match_rows.empty:
            return "UNMATCHED", 30, ""

        suggested = ""
        if ref_val_col and ref_val_col in ref_df.columns:
            suggested = str(match_rows.iloc[0][ref_val_col])

        return "MATCHED", 95, suggested

    # ─────────────────────────────────────────
    # Tier 2: Structural checks
    # FIX Issue 6: 1:N — check city against ALL matching pincode rows
    # ─────────────────────────────────────────

    def _tier2_structural(self, addr_parts, group) -> Tuple[str, int, str]:
        confidence = 50
        issues = []
        suggested_parts = []

        pincode = addr_parts.get("pincode", "")
        city = addr_parts.get("city", "")
        state = addr_parts.get("state", "")
        district = addr_parts.get("district", "")

        # Pincode format check
        pincode_pattern = group.get("pincode_pattern", "pincode_india")
        pattern_re = PATTERNS.get(pincode_pattern, r"^\d{6}$")
        if pincode:
            if re.match(pattern_re, pincode):
                confidence += 20
            else:
                issues.append("invalid_pincode_format")
                confidence -= 10
        else:
            issues.append("missing_pincode")
            confidence -= 15

        pincode_ref_name = group.get("tier2_pincode_ref")
        pin_col_ref = group.get("tier2_pincode_col")
        city_col_ref = group.get("tier2_city_col")
        state_col_ref = group.get("tier2_state_col")       # FIX Issue 6
        district_col_ref = group.get("tier2_district_col")  # FIX Issue 6

        if pincode and pincode_ref_name and pin_col_ref:
            ref_df = self.reference_files.get(pincode_ref_name)
            if ref_df is not None and pin_col_ref in ref_df.columns:
                # FIX Issue 6: get ALL rows matching this pincode (1:N)
                matches = ref_df[ref_df[pin_col_ref].astype(str).str.strip() == pincode]

                if matches.empty:
                    issues.append("pincode_not_in_reference")
                    confidence -= 15
                else:
                    # City check: valid if city matches ANY of the mapped rows
                    if city_col_ref and city_col_ref in ref_df.columns:
                        valid_cities = set(
                            matches[city_col_ref].dropna().astype(str).str.strip().str.lower()
                        )
                        all_cities_str = ", ".join(sorted(
                            matches[city_col_ref].dropna().astype(str).str.strip().unique()
                        ))
                        if city.lower() in valid_cities:
                            confidence += 15
                        elif city:
                            issues.append("city_pincode_mismatch")
                            confidence -= 10
                            suggested_parts.append(f"Valid cities: {all_cities_str}")

                    # State check: valid if state matches ANY of the mapped rows
                    if state_col_ref and state_col_ref in ref_df.columns:
                        valid_states = set(
                            matches[state_col_ref].dropna().astype(str).str.strip().str.lower()
                        )
                        if state.lower() in valid_states:
                            confidence += 10
                        elif state:
                            all_states_str = ", ".join(sorted(
                                matches[state_col_ref].dropna().astype(str).str.strip().unique()
                            ))
                            issues.append("state_pincode_mismatch")
                            confidence -= 5
                            suggested_parts.append(f"Valid states: {all_states_str}")

                    # District check: FIX Issue 6
                    if district_col_ref and district_col_ref in ref_df.columns:
                        valid_districts = set(
                            matches[district_col_ref].dropna().astype(str).str.strip().str.lower()
                        )
                        if district.lower() in valid_districts:
                            confidence += 5
                        elif district:
                            issues.append("district_pincode_mismatch")
                            confidence -= 3

        # Placeholder sub-field check
        for field, val in addr_parts.items():
            if val and self._is_placeholder(val):
                issues.append(f"placeholder_{field}")
                confidence -= 10

        confidence = max(0, min(100, confidence))
        status = "PARTIAL" if issues else "MATCHED"
        suggested = "; ".join(suggested_parts) if suggested_parts else ""
        return status, confidence, suggested

    # ─────────────────────────────────────────
    # Tier 3: Google Maps API
    # FIX Issue 10: SSL, retry, location_type confidence, dedup cache
    # ─────────────────────────────────────────

    def _tier3_geocode(
        self, addr_parts: Dict[str, str], group: Dict
    ) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[int]]:
        """Returns (lat, lng, location_type, confidence)."""
        api_key = group.get("tier3_api_key", "")
        if not api_key:
            return None, None, None, None

        address_str = ", ".join(v for v in [
            addr_parts.get("street", ""),
            addr_parts.get("city", ""),
            addr_parts.get("state", ""),
            addr_parts.get("pincode", ""),
            addr_parts.get("country", ""),
        ] if v)

        if not address_str.strip():
            return None, None, None, None

        # FIX Bug G: check dedup cache first
        if address_str in self._geocode_cache:
            cached = self._geocode_cache[address_str]
            return cached

        # FIX Issue 10b: rate limiting
        now = time.time()
        elapsed_since_last = now - self._last_geocode_time
        if elapsed_since_last < self.geocode_rate_limit:
            time.sleep(self.geocode_rate_limit - elapsed_since_last)

        # FIX Issue 10a/10e: SSL handling + retry
        result = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    GOOGLE_MAPS_API_BASE,
                    params={"address": address_str, "key": api_key},
                    timeout=10,
                    verify=self.ssl_verify,  # FIX Issue 10a
                )
                data = resp.json()
                if data.get("status") == "OK" and data.get("results"):
                    geo = data["results"][0]
                    loc = geo["geometry"]["location"]
                    loc_type = geo["geometry"].get("location_type", "")
                    # FIX Issue 10d: map location_type to confidence
                    conf = self._LOCATION_TYPE_CONFIDENCE.get(loc_type, 60)
                    result = (loc.get("lat"), loc.get("lng"), loc_type, conf)
                elif data.get("status") in ("OVER_QUERY_LIMIT", "RESOURCE_EXHAUSTED"):
                    time.sleep(2 ** attempt)  # FIX Issue 10e: exponential backoff
                    continue
                else:
                    result = (None, None, None, None)
                break
            except requests.exceptions.SSLError:
                if self.ssl_verify and attempt == 0:
                    # Retry once without SSL verification (corporate proxy)
                    self.ssl_verify = False
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    continue
                result = (None, None, None, None)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(1)
                else:
                    result = (None, None, None, None)

        self._last_geocode_time = time.time()
        self._geocode_calls_this_run += 1

        # FIX Bug G: cache the result
        if result:
            self._geocode_cache[address_str] = result

        return result or (None, None, None, None)

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _completeness_score(self, addr_parts: Dict[str, str], group: Dict) -> float:
        expected_fields = group.get("completeness_fields", ADDRESS_COMPLETENESS_FIELDS)
        if not expected_fields:
            return 1.0
        filled = sum(1 for f in expected_fields if addr_parts.get(f, "").strip())
        return filled / len(expected_fields)

    def _is_placeholder(self, value: str) -> bool:
        v = value.strip()
        if not v:
            return True
        for pat in self._PLACEHOLDER_RE:
            if pat.match(v):
                return True
        return False

    @staticmethod
    def output_columns(group: Dict) -> List[str]:
        prefix = group.get("output_prefix", group.get("group_name", "addr"))
        return [
            f"{prefix}_addr_match_status",
            f"{prefix}_addr_confidence",
            f"{prefix}_addr_suggested",
            f"{prefix}_addr_completeness_score",
            f"{prefix}_lat",
            f"{prefix}_lng",
            f"{prefix}_geocode_type",   # FIX Issue 10d: new column
        ]
