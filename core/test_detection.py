# core/test_detection.py — 5 Test Detection Methods
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from config import TEST_DETECTION_METHODS, TEST_ENV_ROWS


class TestDetectionEngine:
    """
    Detects test records using up to 5 configurable methods.
    First TEST_ENV_ROWS rows are the test environment scope.
    Flags matching rows with flag_test_record=True.
    Test records are excluded from quality metrics.
    """

    def __init__(self, detection_config: List[Dict]):
        """
        detection_config: list of rule dicts, each with 'method' and method-specific params.
        """
        self.detection_config = detection_config

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply all detection rules. Returns df with flag_test_record column added/updated.
        Only the first TEST_ENV_ROWS rows are in scope for test detection.
        """
        df = df.copy()
        if "flag_test_record" not in df.columns:
            df["flag_test_record"] = False

        # Restrict detection scope to first TEST_ENV_ROWS
        scope_mask = pd.Series(False, index=df.index)
        if len(df) > 0:
            first_n = df.index[:TEST_ENV_ROWS]
            scope_mask.loc[first_n] = True

        for rule in self.detection_config:
            method = rule.get("method")
            if method not in TEST_DETECTION_METHODS:
                continue
            try:
                match_mask = self._dispatch(df, rule, scope_mask)
                df.loc[match_mask, "flag_test_record"] = True
            except Exception:
                continue

        return df

    # ─────────────────────────────────────────
    # Dispatcher
    # ─────────────────────────────────────────

    def _dispatch(
        self,
        df: pd.DataFrame,
        rule: Dict,
        scope_mask: pd.Series,
    ) -> pd.Series:
        method = rule.get("method")
        if method == "field_value_match":
            return self._field_value_match(df, rule, scope_mask)
        elif method == "prefix_suffix_pattern":
            return self._prefix_suffix_pattern(df, rule, scope_mask)
        elif method == "regex_pattern":
            return self._regex_pattern(df, rule, scope_mask)
        elif method == "value_in_list":
            return self._value_in_list(df, rule, scope_mask)
        elif method == "null_pk":
            return self._null_pk(df, rule, scope_mask)
        return pd.Series(False, index=df.index)

    # ─────────────────────────────────────────
    # Method 1: Field value match
    # ─────────────────────────────────────────

    def _field_value_match(
        self, df: pd.DataFrame, rule: Dict, scope_mask: pd.Series
    ) -> pd.Series:
        """Flag rows where column exactly equals a specified value."""
        col = rule.get("column")
        value = rule.get("value", "")
        case_sensitive = rule.get("case_sensitive", False)

        if col not in df.columns:
            return pd.Series(False, index=df.index)

        if case_sensitive:
            match = df[col].astype(str).str.strip() == str(value)
        else:
            match = df[col].astype(str).str.strip().str.lower() == str(value).lower()

        return match & scope_mask

    # ─────────────────────────────────────────
    # Method 2: Prefix / Suffix pattern
    # ─────────────────────────────────────────

    def _prefix_suffix_pattern(
        self, df: pd.DataFrame, rule: Dict, scope_mask: pd.Series
    ) -> pd.Series:
        """Flag rows where column starts or ends with a given string."""
        col = rule.get("column")
        prefix = rule.get("prefix", "")
        suffix = rule.get("suffix", "")
        case_sensitive = rule.get("case_sensitive", False)

        if col not in df.columns:
            return pd.Series(False, index=df.index)

        series = df[col].astype(str).str.strip()
        if not case_sensitive:
            series = series.str.lower()
            prefix = prefix.lower()
            suffix = suffix.lower()

        match = pd.Series(False, index=df.index)
        if prefix:
            match = match | series.str.startswith(prefix)
        if suffix:
            match = match | series.str.endswith(suffix)

        return match & scope_mask

    # ─────────────────────────────────────────
    # Method 3: Regex pattern
    # ─────────────────────────────────────────

    def _regex_pattern(
        self, df: pd.DataFrame, rule: Dict, scope_mask: pd.Series
    ) -> pd.Series:
        """Flag rows where column matches a regex pattern."""
        col = rule.get("column")
        pattern = rule.get("pattern", "")
        flags_str = rule.get("flags", "")

        if col not in df.columns or not pattern:
            return pd.Series(False, index=df.index)

        re_flags = re.IGNORECASE if "i" in flags_str.lower() else 0
        try:
            compiled = re.compile(pattern, re_flags)
            match = df[col].astype(str).str.contains(compiled, na=False)
        except re.error:
            return pd.Series(False, index=df.index)

        return match & scope_mask

    # ─────────────────────────────────────────
    # Method 4: Value in list
    # ─────────────────────────────────────────

    def _value_in_list(
        self, df: pd.DataFrame, rule: Dict, scope_mask: pd.Series
    ) -> pd.Series:
        """Flag rows where column value is in a specified list."""
        col = rule.get("column")
        values = rule.get("values", [])
        case_sensitive = rule.get("case_sensitive", False)

        if col not in df.columns or not values:
            return pd.Series(False, index=df.index)

        str_values = [str(v) for v in values]
        series = df[col].astype(str).str.strip()

        if case_sensitive:
            match = series.isin(str_values)
        else:
            lower_values = {v.lower() for v in str_values}
            match = series.str.lower().isin(lower_values)

        return match & scope_mask

    # ─────────────────────────────────────────
    # Method 5: Null PK
    # ─────────────────────────────────────────

    def _null_pk(
        self, df: pd.DataFrame, rule: Dict, scope_mask: pd.Series
    ) -> pd.Series:
        """Flag rows where the primary key column is null/empty."""
        col = rule.get("column")

        if col not in df.columns:
            return pd.Series(False, index=df.index)

        match = df[col].isna() | (df[col].astype(str).str.strip() == "")
        return match & scope_mask

    # ─────────────────────────────────────────
    # Stats helper
    # ─────────────────────────────────────────

    @staticmethod
    def test_record_summary(df: pd.DataFrame) -> Dict:
        if "flag_test_record" not in df.columns:
            return {"total": len(df), "test": 0, "production": len(df)}
        test_count = int(df["flag_test_record"].sum())
        total = len(df)
        return {
            "total": total,
            "test": test_count,
            "production": total - test_count,
        }
