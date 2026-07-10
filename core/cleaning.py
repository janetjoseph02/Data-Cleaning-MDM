# core/cleaning.py — 26 Cleaning Rules engine
from __future__ import annotations

import re
import ast
import copy
import datetime
import difflib
import html
import math
import traceback
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    ALL_CLEANING_RULES,
    BOOLEAN_TRUE_VALUES,
    BOOLEAN_FALSE_VALUES,
    BOOLEAN_TRUE_OUTPUT,
    BOOLEAN_FALSE_OUTPUT,
    CURRENCY_SYMBOLS,
    DATE_INPUT_FORMATS,
    DATE_OUTPUT_FORMAT,
    FUZZY_DEFAULT_THRESHOLD,
    FUZZY_FIRST_CHAR_BLOCK,
    LEGAL_ENTITY_MAP,
    CUSTOM_EXPR_PREVIEW_ROWS,
)


# ─────────────────────────────────────────────
# Null-safe string helpers
# ─────────────────────────────────────────────
# Problem: df[col].astype(str) turns NaN/None into the literal text "nan"/"None",
# which then fails reference checks and pollutes the data. These helpers keep
# nulls as real NaN through any string transformation.

_NULL_TOKENS = {"nan", "none", "null", "nat", "<na>", ""}


def _null_mask(s: pd.Series) -> pd.Series:
    """True where the value should be treated as null (real NaN or null-like text)."""
    base = s.isna()
    as_text = s.astype(str).str.strip().str.lower()
    return base | as_text.isin(_NULL_TOKENS)


def _str_series(s: pd.Series) -> pd.Series:
    """Cast to string for processing but remember where the nulls were."""
    return s.astype(str)


def _restore_nulls(result: pd.Series, original: pd.Series) -> pd.Series:
    """Put NaN back wherever the original was null-like."""
    mask = _null_mask(original)
    return result.where(~mask, np.nan)

# ─────────────────────────────────────────────
# Public ALL_RULES list (fixes missing constant bug)
# ─────────────────────────────────────────────
ALL_RULES = ALL_CLEANING_RULES


class CleaningEngine:
    """
    Applies configured cleaning rules to a DataFrame (or chunks thereof).
    Rules are applied in order. Each rule is configured via a dict.
    """

    def __init__(
        self,
        cleaning_rules: Dict[str, List[Dict]],
        reference_files: Optional[Dict[str, pd.DataFrame]] = None,
    ):
        """
        Parameters
        ----------
        cleaning_rules : {column_name: [rule_config_dict, ...]}
        reference_files : {name: DataFrame} for lookup rules
        """
        self.cleaning_rules = cleaning_rules
        self.reference_files = reference_files or {}
        self._log: List[Dict] = []

    # ─────────────────────────────────────────
    # Main entry
    # ─────────────────────────────────────────

    def apply(self, df: pd.DataFrame, chunk_index: int = 0) -> pd.DataFrame:
        """
        Apply all configured cleaning rules to df.
        Returns a new DataFrame with additional flag_* columns.
        Appends to internal log.
        """
        df = df.copy()
        ts = datetime.datetime.now().isoformat()

        for col, rules in self.cleaning_rules.items():
            if col not in df.columns:
                continue
            for rule_cfg in rules:
                rule_name = rule_cfg.get("rule")
                if rule_name not in ALL_RULES:
                    continue
                try:
                    df = self._dispatch(df, col, rule_name, rule_cfg, chunk_index)
                    self._log.append({
                        "timestamp": ts,
                        "chunk": chunk_index,
                        "column": col,
                        "rule": rule_name,
                        "status": "OK",
                    })
                except Exception as exc:
                    self._log.append({
                        "timestamp": ts,
                        "chunk": chunk_index,
                        "column": col,
                        "rule": rule_name,
                        "status": "ERROR",
                        "detail": str(exc),
                    })

        return df

    def get_log(self) -> List[Dict]:
        return list(self._log)

    def clear_log(self) -> None:
        self._log = []

    # ─────────────────────────────────────────
    # Dispatcher
    # ─────────────────────────────────────────

    def _dispatch(
        self,
        df: pd.DataFrame,
        col: str,
        rule: str,
        cfg: Dict,
        chunk_index: int,
    ) -> pd.DataFrame:
        fns = {
            "trim_whitespace": _trim_whitespace,
            "collapse_internal_spaces": _collapse_internal_spaces,
            "case_normalize": _case_normalize,
            "null_handling": _null_handling,
            "pattern_replace": _pattern_replace,
            "remove_html": _remove_html,
            "remove_special_chars": _remove_special_chars,
            "prefix_remap": _prefix_remap,
            "trim_leading_zeros": _trim_leading_zeros,
            "trim_trailing_zeros": _trim_trailing_zeros,
            "pad_leading_zeros": _pad_leading_zeros,
            "trim_leading_trailing_special": _trim_leading_trailing_special,
            "date_standardize": _date_standardize,
            "phone_standardize": _phone_standardize,
            "legal_entity_suffix_norm": _legal_entity_suffix_norm,
            "boolean_norm": _boolean_norm,
            "currency_norm": _currency_norm,
            "extract_substring": _extract_substring,
            "concatenate_fields": _concatenate_fields,
            "split_field": _split_field,
            "deduplicate_multivalue": _deduplicate_multivalue,
            "flag_duplicate_records": _flag_duplicate_records,
            "custom_regex_replace": _custom_regex_replace,
        }

        if rule == "fuzzy_match":
            return _fuzzy_match(df, col, cfg, self.reference_files)
        if rule == "reference_lookup_replace":
            return _reference_lookup_replace(df, col, cfg, self.reference_files)
        if rule == "custom_python_expression":
            return _custom_python_expression(df, col, cfg, preview_only=False)
        if rule == "custom_lookup_transform":
            return _custom_lookup_transform(df, col, cfg, self.reference_files)

        fn = fns.get(rule)
        if fn:
            return fn(df, col, cfg)
        raise ValueError(f"Unknown cleaning rule: {rule}")


# ─────────────────────────────────────────────
# Rule 1: Trim whitespace
# ─────────────────────────────────────────────

def _trim_whitespace(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    orig = df[col]
    result = _str_series(orig).str.strip()
    df[col] = _restore_nulls(result, orig)
    return df


# ─────────────────────────────────────────────
# Rule 2: Collapse internal spaces
# ─────────────────────────────────────────────

def _collapse_internal_spaces(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    orig = df[col]
    result = _str_series(orig).str.replace(r"\s+", " ", regex=True).str.strip()
    df[col] = _restore_nulls(result, orig)
    return df


# ─────────────────────────────────────────────
# Rule 3: Case normalization
# ─────────────────────────────────────────────

def _case_normalize(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    mode = cfg.get("mode", "upper")  # upper | lower | title | sentence
    orig = df[col]
    s = _str_series(orig)
    if mode == "upper":
        result = s.str.upper()
    elif mode == "lower":
        result = s.str.lower()
    elif mode == "title":
        result = s.str.title()
    elif mode == "sentence":
        result = s.str.capitalize()
    else:
        result = s
    df[col] = _restore_nulls(result, orig)
    return df


# ─────────────────────────────────────────────
# Rule 4: Null handling — fill or flag only (no deletion)
# ─────────────────────────────────────────────

def _null_handling(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    action = cfg.get("action", "flag")  # fill | flag
    fill_value = cfg.get("fill_value", "")
    flag_col = f"flag_null_{col}"

    is_null = df[col].isna() | (df[col].astype(str).str.strip() == "")

    if action == "fill":
        df[col] = df[col].where(~is_null, fill_value)
    # flag in all cases
    df[flag_col] = is_null.astype(int)
    return df


# ─────────────────────────────────────────────
# Rule 5: Pattern replace
# ─────────────────────────────────────────────

def _pattern_replace(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    pattern = cfg.get("pattern", "")
    replacement = cfg.get("replacement", "")
    if not pattern:
        return df
    orig = df[col]
    result = _str_series(orig).str.replace(pattern, replacement, regex=True)
    df[col] = _restore_nulls(result, orig)
    return df


# ─────────────────────────────────────────────
# Rule 6: Remove HTML tags
# ─────────────────────────────────────────────

def _remove_html(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    tag_re = re.compile(r"<[^>]+>")

    def strip_html(val):
        if pd.isna(val):
            return val
        s = html.unescape(str(val))
        return tag_re.sub("", s).strip()

    df[col] = df[col].apply(strip_html)
    return df


# ─────────────────────────────────────────────
# Rule 7: Remove special characters
# ─────────────────────────────────────────────

def _remove_special_chars(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    keep_spaces = cfg.get("keep_spaces", True)
    keep_alphanumeric = cfg.get("keep_alphanumeric", True)
    extra_keep = cfg.get("extra_keep", "")  # chars to additionally keep

    def clean(val):
        if pd.isna(val):
            return val
        s = str(val)
        pattern = r"[^a-zA-Z0-9"
        if keep_spaces:
            pattern += r"\s"
        if extra_keep:
            pattern += re.escape(extra_keep)
        pattern += r"]"
        return re.sub(pattern, "", s)

    df[col] = df[col].apply(clean)
    return df


# ─────────────────────────────────────────────
# Rule 8: Prefix remap
# ─────────────────────────────────────────────

def _prefix_remap(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    """Replace old prefixes with new ones. cfg['mapping'] = {old_prefix: new_prefix}"""
    mapping = cfg.get("mapping", {})
    if not mapping:
        return df

    def remap(val):
        if pd.isna(val):
            return val
        s = str(val)
        for old, new in mapping.items():
            if s.startswith(old):
                return new + s[len(old):]
        return s

    df[col] = df[col].apply(remap)
    return df


# ─────────────────────────────────────────────
# Rule 9: Trim leading zeros
# ─────────────────────────────────────────────

def _trim_leading_zeros(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    df[col] = df[col].astype(str).str.lstrip("0")
    # restore "0" for a value that was "00..."
    df[col] = df[col].apply(lambda x: "0" if x == "" else x)
    df[col] = df[col].replace("nan", np.nan)
    return df


# ─────────────────────────────────────────────
# Rule 10: Trim trailing zeros (decimal)
# ─────────────────────────────────────────────

def _trim_trailing_zeros(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    def trim_tz(val):
        if pd.isna(val):
            return val
        s = str(val)
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    df[col] = df[col].apply(trim_tz)
    return df


# ─────────────────────────────────────────────
# Rule 11: Pad leading zeros
# ─────────────────────────────────────────────

def _pad_leading_zeros(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    width = cfg.get("width", 6)

    def pad(val):
        if pd.isna(val):
            return val
        s = str(val).strip()
        if s.isdigit():
            return s.zfill(width)
        return s

    df[col] = df[col].apply(pad)
    return df


# ─────────────────────────────────────────────
# Rule 12: Trim leading/trailing special chars
# ─────────────────────────────────────────────

def _trim_leading_trailing_special(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    chars = cfg.get("chars", r"[^a-zA-Z0-9\s]")

    def trim_spec(val):
        if pd.isna(val):
            return val
        s = str(val)
        # Remove from start
        s = re.sub(r"^" + chars + r"+", "", s)
        # Remove from end
        s = re.sub(chars + r"+$", "", s)
        return s.strip()

    df[col] = df[col].apply(trim_spec)
    return df


# ─────────────────────────────────────────────
# Rule 13: Fuzzy match (difflib WRatio + first-char blocking)
# ─────────────────────────────────────────────

def _fuzzy_match(
    df: pd.DataFrame, col: str, cfg: Dict, reference_files: Dict
) -> pd.DataFrame:
    threshold = cfg.get("threshold", FUZZY_DEFAULT_THRESHOLD)
    ref_name = cfg.get("reference_file")
    ref_col = cfg.get("reference_column")
    output_col = cfg.get("output_column", col)
    first_char_block = cfg.get("first_char_block", FUZZY_FIRST_CHAR_BLOCK)

    ref_df = reference_files.get(ref_name)
    if ref_df is None or ref_col not in ref_df.columns:
        return df

    lookup_values = ref_df[ref_col].dropna().astype(str).tolist()

    def fuzzy_replace(val):
        if pd.isna(val):
            return val
        s = str(val).strip()
        if not s:
            return val

        candidates = lookup_values
        if first_char_block and s:
            fc = s[0].lower()
            candidates = [v for v in candidates if v and v[0].lower() == fc]

        if not candidates:
            return val

        matcher = difflib.SequenceMatcher(None, s.lower(), "")
        best_ratio = 0
        best_match = val
        for c in candidates:
            matcher.set_seq2(c.lower())
            ratio = matcher.ratio() * 100
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = c

        if best_ratio >= threshold:
            return best_match
        return val

    df[output_col] = df[col].apply(fuzzy_replace)
    return df


# ─────────────────────────────────────────────
# Rule 14: Reference lookup replace
# ─────────────────────────────────────────────

def _reference_lookup_replace(
    df: pd.DataFrame, col: str, cfg: Dict, reference_files: Dict
) -> pd.DataFrame:
    ref_name = cfg.get("reference_file")
    key_col = cfg.get("key_column")
    value_col = cfg.get("value_column")
    unmatched_action = cfg.get("unmatched_action", "keep")  # keep | blank | flag

    ref_df = reference_files.get(ref_name)
    if ref_df is None:
        return df
    if key_col not in ref_df.columns or value_col not in ref_df.columns:
        return df

    lookup_map = dict(zip(
        ref_df[key_col].astype(str).str.strip(),
        ref_df[value_col].astype(str).str.strip(),
    ))

    flag_col = f"flag_ref_nomatch_{col}"

    def do_replace(val):
        if pd.isna(val):
            return val
        k = str(val).strip()
        result = lookup_map.get(k)
        return result if result is not None else val

    def is_unmatched(val):
        if pd.isna(val):
            return False
        return str(val).strip() not in lookup_map

    df[flag_col] = df[col].apply(is_unmatched).astype(int)

    if unmatched_action == "blank":
        df[col] = df[col].apply(lambda v: do_replace(v) if not is_unmatched(v) else np.nan)
    else:
        df[col] = df[col].apply(do_replace)

    return df


# ─────────────────────────────────────────────
# Rule 15: Date standardization
# ─────────────────────────────────────────────

def _date_standardize(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    output_format = cfg.get("output_format", DATE_OUTPUT_FORMAT)
    input_formats = cfg.get("input_formats", DATE_INPUT_FORMATS)

    def parse_date(val):
        if pd.isna(val):
            return val

        # If the value is ALREADY a datetime/date/Timestamp, format directly.
        # Reparsing its string form with dayfirst=True corrupts the month
        # (e.g. 2022-07-01 → treated as day=07 month=01 → wrong).
        if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
            try:
                return pd.Timestamp(val).strftime(output_format)
            except Exception:
                return val

        s = str(val).strip()

        # Try explicit input formats first (exact match)
        for fmt in input_formats:
            try:
                return datetime.datetime.strptime(s, fmt).strftime(output_format)
            except ValueError:
                continue

        # ISO-like strings (start with YYYY-) must NOT use dayfirst,
        # otherwise 2022-07-01 is misread as day-first.
        iso_like = bool(re.match(r"^\d{4}-\d{1,2}-\d{1,2}", s))
        try:
            parsed = pd.to_datetime(s, dayfirst=not iso_like, errors="raise")
            return parsed.strftime(output_format)
        except Exception:
            return val  # keep original if unparseable

    df[col] = df[col].apply(parse_date)
    return df


# ─────────────────────────────────────────────
# Rule 16: Phone standardization
# ─────────────────────────────────────────────

def _phone_standardize(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    output_format = cfg.get("output_format", "e164")  # e164 | national | local
    country_code = cfg.get("country_code", "+91")

    def clean_phone(val):
        if pd.isna(val):
            return val
        digits = re.sub(r"[^\d+]", "", str(val))
        if digits == "":
            return val  # nothing digit-like at all — leave original for visibility

        # FIX: placeholder numbers like '0', '00', '000...' must NOT collapse
        # to an empty string (that makes them look like blanks in reports).
        # Keep them as-is so validation flags them as a real bad value.
        if digits.strip("0") == "":
            return digits

        if output_format == "e164":
            if digits.startswith("+"):
                return digits
            if digits.startswith("0"):
                digits = digits[1:]
            if digits.strip("0") == "" or digits == "":
                return val
            return country_code + digits
        elif output_format == "national":
            if digits.startswith("+"):
                stripped = digits[len(country_code.replace("+", "")):]
                return stripped if stripped else digits
            local = digits.lstrip("0")
            # FIX: if stripping leading zeros empties the string, keep the
            # original digits instead of returning "" (e.g. '0' -> '0', not '').
            return local if local else digits
        return digits

    df[col] = df[col].apply(clean_phone)
    return df


# ─────────────────────────────────────────────
# Rule 17: Legal entity suffix normalization
# ─────────────────────────────────────────────

def _legal_entity_suffix_norm(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    custom_map = cfg.get("custom_map", {})
    full_map = {**LEGAL_ENTITY_MAP, **custom_map}

    def normalize(val):
        if pd.isna(val):
            return val
        s = str(val)
        for pattern, replacement in full_map.items():
            s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
        return s.strip()

    df[col] = df[col].apply(normalize)
    return df


# ─────────────────────────────────────────────
# Rule 18: Boolean normalization
# ─────────────────────────────────────────────

def _boolean_norm(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    true_out = cfg.get("true_output", BOOLEAN_TRUE_OUTPUT)
    false_out = cfg.get("false_output", BOOLEAN_FALSE_OUTPUT)
    null_out = cfg.get("null_output", np.nan)

    def norm_bool(val):
        if pd.isna(val):
            return null_out
        s = str(val).strip().lower()
        if s in BOOLEAN_TRUE_VALUES:
            return true_out
        if s in BOOLEAN_FALSE_VALUES:
            return false_out
        return val  # unknown

    df[col] = df[col].apply(norm_bool)
    return df


# ─────────────────────────────────────────────
# Rule 19: Currency normalization
# ─────────────────────────────────────────────

def _currency_norm(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    strip_symbols = cfg.get("strip_symbols", True)
    strip_commas = cfg.get("strip_commas", True)
    target_symbol = cfg.get("target_symbol", "")
    decimal_places = cfg.get("decimal_places", 2)

    def norm_currency(val):
        if pd.isna(val):
            return val
        s = str(val).strip()
        if strip_symbols:
            for sym in CURRENCY_SYMBOLS:
                s = s.replace(sym, "")
        if strip_commas:
            s = s.replace(",", "")
        s = s.strip()
        try:
            num = float(s)
            formatted = f"{num:.{decimal_places}f}"
            return (target_symbol + formatted) if target_symbol else formatted
        except ValueError:
            return s

    df[col] = df[col].apply(norm_currency)
    return df


# ─────────────────────────────────────────────
# Rule 20: Extract substring → new column
# ─────────────────────────────────────────────

def _extract_substring(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    method = cfg.get("method", "regex")  # regex | position
    pattern = cfg.get("pattern", "")
    start = cfg.get("start", 0)
    end = cfg.get("end", None)
    new_col = cfg.get("new_column", f"{col}_extracted")
    group = cfg.get("group", 0)

    if method == "regex" and pattern:
        df[new_col] = df[col].astype(str).str.extract(f"({pattern})", expand=False)
    else:
        df[new_col] = df[col].astype(str).str[start:end]

    return df


# ─────────────────────────────────────────────
# Rule 21: Concatenate fields → new column
# ─────────────────────────────────────────────

def _concatenate_fields(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    fields = cfg.get("fields", [col])
    separator = cfg.get("separator", " ")
    new_col = cfg.get("new_column", "_".join(fields) + "_concat")
    skip_null = cfg.get("skip_null", True)

    def concat_row(row):
        parts = []
        for f in fields:
            v = row.get(f, "")
            if skip_null and pd.isna(v):
                continue
            parts.append(str(v))
        return separator.join(parts)

    df[new_col] = df.apply(concat_row, axis=1)
    return df


# ─────────────────────────────────────────────
# Rule 22: Split field → new columns
# ─────────────────────────────────────────────

def _split_field(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    delimiter = cfg.get("delimiter", ",")
    max_splits = cfg.get("max_splits", -1)
    new_col_prefix = cfg.get("new_col_prefix", f"{col}_part")
    n = cfg.get("n", 2)  # expected number of parts

    if max_splits == -1:
        split_df = df[col].astype(str).str.split(delimiter, expand=True)
    else:
        split_df = df[col].astype(str).str.split(delimiter, n=max_splits, expand=True)

    for i in range(split_df.shape[1]):
        df[f"{new_col_prefix}_{i+1}"] = split_df[i]

    return df


# ─────────────────────────────────────────────
# Rule 23: Deduplicate multi-value within field
# ─────────────────────────────────────────────

def _deduplicate_multivalue(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    delimiter = cfg.get("delimiter", ",")
    sort_values = cfg.get("sort", False)
    case_insensitive = cfg.get("case_insensitive", True)

    def dedup(val):
        if pd.isna(val):
            return val
        parts = [p.strip() for p in str(val).split(delimiter)]
        seen = set()
        result = []
        for p in parts:
            key = p.lower() if case_insensitive else p
            if key not in seen:
                seen.add(key)
                result.append(p)
        if sort_values:
            result.sort(key=lambda x: x.lower() if case_insensitive else x)
        return delimiter.join(result)

    df[col] = df[col].apply(dedup)
    return df


# ─────────────────────────────────────────────
# Rule 24: Flag duplicate records
# ─────────────────────────────────────────────

def _flag_duplicate_records(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    subset_cols = cfg.get("subset", [col])
    keep = cfg.get("keep", "first")  # first | last | False
    flag_col = cfg.get("flag_column", "flag_duplicate_record")

    # Validate columns exist
    valid_cols = [c for c in subset_cols if c in df.columns]
    if not valid_cols:
        valid_cols = [col]

    if keep == "first":
        is_dup = df.duplicated(subset=valid_cols, keep="first")
    elif keep == "last":
        is_dup = df.duplicated(subset=valid_cols, keep="last")
    else:
        is_dup = df.duplicated(subset=valid_cols, keep=False)

    df[flag_col] = is_dup.astype(int)
    return df


# ─────────────────────────────────────────────
# Rule 25: Custom regex replace
# ─────────────────────────────────────────────

def _custom_regex_replace(df: pd.DataFrame, col: str, cfg: Dict) -> pd.DataFrame:
    pattern = cfg.get("pattern", "")
    replacement = cfg.get("replacement", "")
    flags_str = cfg.get("flags", "")  # "IGNORECASE|MULTILINE" etc.
    if not pattern:
        return df

    re_flags = 0
    if "IGNORECASE" in flags_str or "I" in flags_str:
        re_flags |= re.IGNORECASE
    if "MULTILINE" in flags_str or "M" in flags_str:
        re_flags |= re.MULTILINE
    if "DOTALL" in flags_str or "S" in flags_str:
        re_flags |= re.DOTALL

    compiled = re.compile(pattern, re_flags)
    df[col] = df[col].astype(str).apply(
        lambda v: compiled.sub(replacement, v) if not pd.isna(v) else v
    )
    df[col] = df[col].replace("nan", np.nan)
    return df


# ─────────────────────────────────────────────
# Rule 26a: Custom Python expression (sandboxed)
# ─────────────────────────────────────────────

_SAFE_BUILTINS = {
    "__builtins__": {},
    "len": len, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "set": set,
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "sorted": sorted, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter,
    "re": re, "math": math,
}


def _custom_python_expression(
    df: pd.DataFrame,
    col: str,
    cfg: Dict,
    preview_only: bool = False,
) -> pd.DataFrame:
    expression = cfg.get("expression", "")
    new_col = cfg.get("new_column", col)
    if not expression:
        return df

    target_df = df.head(CUSTOM_EXPR_PREVIEW_ROWS) if preview_only else df

    def safe_eval(row):
        local_env = {**_SAFE_BUILTINS, "value": row[col], "row": row.to_dict()}
        try:
            return eval(expression, {"__builtins__": {}}, local_env)
        except Exception as e:
            return f"__EXPR_ERROR__: {e}"

    result = target_df.apply(safe_eval, axis=1)
    if preview_only:
        return result  # return Series for preview display
    df[new_col] = result
    return df


def preview_custom_expression(
    df: pd.DataFrame, col: str, expression: str
) -> pd.DataFrame:
    """Return 5-row preview for UI gate."""
    cfg = {"expression": expression, "new_column": f"{col}_preview"}
    result = _custom_python_expression(df, col, cfg, preview_only=True)
    preview = df[[col]].head(CUSTOM_EXPR_PREVIEW_ROWS).copy()
    preview[f"{col}_after"] = result.values
    return preview


# ─────────────────────────────────────────────
# Rule 26b: Custom lookup transform
# ─────────────────────────────────────────────

def _custom_lookup_transform(
    df: pd.DataFrame, col: str, cfg: Dict, reference_files: Dict
) -> pd.DataFrame:
    """
    Multi-key lookup: row-level match on (key1, key2, ...) → output value.
    cfg:
        key_fields: [col1, col2, ...]  (list of fields to match on)
        ref_name: name of reference file
        ref_key_fields: [ref_col1, ref_col2, ...]
        ref_value_field: column in ref to use as replacement
        output_column: where to write result
        unmatched_action: keep | blank | flag
    """
    key_fields = cfg.get("key_fields", [col])
    ref_name = cfg.get("ref_name")
    ref_key_fields = cfg.get("ref_key_fields", key_fields)
    ref_value_field = cfg.get("ref_value_field")
    output_column = cfg.get("output_column", col)
    unmatched_action = cfg.get("unmatched_action", "keep")

    ref_df = reference_files.get(ref_name)
    if ref_df is None or ref_value_field not in ref_df.columns:
        return df

    # Build multi-key lookup dict
    lookup: Dict[Tuple, Any] = {}
    for _, ref_row in ref_df.iterrows():
        k = tuple(str(ref_row[f]).strip() for f in ref_key_fields if f in ref_row)
        lookup[k] = ref_row[ref_value_field]

    flag_col = f"flag_lookup_nomatch_{col}"
    no_matches = []

    def do_lookup(row):
        k = tuple(str(row[f]).strip() for f in key_fields if f in row)
        return lookup.get(k)

    results = df.apply(do_lookup, axis=1)
    df[flag_col] = results.isna().astype(int)

    if unmatched_action == "keep":
        df[output_column] = results.where(results.notna(), df[col])
    elif unmatched_action == "blank":
        df[output_column] = results
    else:
        df[output_column] = results.where(results.notna(), df[col])

    return df
