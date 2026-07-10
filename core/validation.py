# core/validation.py — 19 Validation Types engine
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from config import (
    ALL_VALIDATION_TYPES,
    DATE_INPUT_FORMATS,
    ISSUE_TYPES,
    PATTERNS,
    VALIDATION_REPORT_COLS,
)


class ValidationEngine:
    """
    Runs configured validation rules against a DataFrame (chunk).
    Returns issues as a list of dicts conforming to VALIDATION_REPORT_COLS.
    """

    def __init__(
        self,
        validation_rules: List[Dict],
        reference_files: Optional[Dict[str, pd.DataFrame]] = None,
        pk_seen: Optional[Set] = None,
    ):
        self.validation_rules = validation_rules
        self.reference_files = reference_files or {}
        self.pk_seen: Set = pk_seen if pk_seen is not None else set()
        self._issues: List[Dict] = []
        self._log: List[Dict] = []
        # Rich analysis tables (dict of name -> DataFrame) produced by
        # mapping_cardinality and cross_file_cardinality, for dedicated
        # report sheets.
        self._analysis_tables: Dict[str, pd.DataFrame] = {}

    # ─────────────────────────────────────────
    # Main entry
    # ─────────────────────────────────────────

    def validate(
        self,
        df: pd.DataFrame,
        chunk_index: int = 0,
        exclude_test_records: bool = True,
    ) -> List[Dict]:
        ts = datetime.datetime.now().isoformat()

        if exclude_test_records and "flag_test_record" in df.columns:
            work_df = df[df["flag_test_record"] != True].copy()
        else:
            work_df = df.copy()

        chunk_issues: List[Dict] = []

        for rule in self.validation_rules:
            vtype = rule.get("type")
            if vtype not in ALL_VALIDATION_TYPES:
                continue
            try:
                new_issues = self._dispatch(work_df, rule, chunk_index, ts)
                chunk_issues.extend(new_issues)
                self._log.append({
                    "timestamp": ts, "chunk": chunk_index,
                    "type": vtype, "issues_found": len(new_issues),
                })
            except Exception as exc:
                self._log.append({
                    "timestamp": ts, "chunk": chunk_index,
                    "type": vtype, "error": str(exc),
                })

        self._issues.extend(chunk_issues)
        return chunk_issues

    def get_all_issues(self) -> List[Dict]:
        return list(self._issues)

    def get_log(self) -> List[Dict]:
        return list(self._log)

    def get_analysis_tables(self) -> Dict[str, pd.DataFrame]:
        """Return rich analysis tables (mapping / cross-file cardinality)."""
        return dict(self._analysis_tables)

    def clear(self) -> None:
        self._issues = []
        self._log = []
        self._analysis_tables = {}

    def issues_as_dataframe(self) -> pd.DataFrame:
        if not self._issues:
            return pd.DataFrame(columns=VALIDATION_REPORT_COLS)
        return pd.DataFrame(self._issues)[VALIDATION_REPORT_COLS]

    # ─────────────────────────────────────────
    # Dispatcher
    # ─────────────────────────────────────────

    def _dispatch(self, df, rule, chunk_index, ts) -> List[Dict]:
        vtype = rule.get("type")
        dispatchers = {
            "mandatory_null": self._check_mandatory_null,
            "data_type": self._check_data_type,
            "pattern_format": self._check_pattern_format,
            "allowed_values": self._check_allowed_values,
            "range": self._check_range,
            "pk_uniqueness": self._check_pk_uniqueness,
            "string_length": self._check_string_length,
            "trim_validation": self._check_trim_validation,
            "cardinality_1_to_1": self._check_cardinality_1_1,
            "cardinality_1_to_n": self._check_cardinality_1_n,
            "reference_existence": self._check_reference_existence,
            "cross_field_tuple": self._check_cross_field_tuple,
            "conditional_rule": self._check_conditional_rule,
            "mutual_exclusivity": self._check_mutual_exclusivity,
            "co_occurrence": self._check_co_occurrence,
            "value_dependency": self._check_value_dependency,
            "arithmetic_consistency": self._check_arithmetic_consistency,
            "date_sequence": self._check_date_sequence,
            "completeness_score": self._check_completeness_score,
            "date_year_range": self._check_date_year_range,
            "grouped_fuzzy_duplicate": self._check_grouped_fuzzy_duplicate,
            "mapping_cardinality": self._check_mapping_cardinality,
            "cross_file_cardinality": self._check_cross_file_cardinality,
            "suspicious_number": self._check_suspicious_number,
        }
        fn = dispatchers.get(vtype)
        if not fn:
            return []
        return fn(df, rule, chunk_index, ts)

    # ─────────────────────────────────────────
    # Issue factory
    # ─────────────────────────────────────────

    @staticmethod
    def _make_issue(
        record_id: Any, field: str, issue_type: str,
        rule_desc: str, expected: Any, actual: Any,
        severity: str, chunk_index: int, ts: str,
    ) -> Dict:
        # FIX: distinguish a genuinely empty/blank value from a normal value
        # so the report never shows a confusing blank cell that looks like
        # a missing-data false positive when it's actually a real (bad) value
        # such as '0' or '' left over after cleaning.
        actual_str = str(actual)
        if actual_str.strip() == "":
            actual_str = "(empty value)"

        return {
            "Record ID": str(record_id),
            "Field Name": field,
            "Issue Type": issue_type,
            "Rule Description": rule_desc,
            "Expected": str(expected),
            "Actual": actual_str,
            "Severity": severity,
            "Chunk Number": chunk_index,
            "Timestamp": ts,
        }

    # ─────────────────────────────────────────
    # V1: Mandatory / Null
    # ─────────────────────────────────────────

    def _check_mandatory_null(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        severity = rule.get("severity", "High")
        if col not in df.columns:
            return []
        issues = []
        null_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        for idx in df[null_mask].index:
            issues.append(self._make_issue(
                idx, col, "NULL_VIOLATION",
                f"Field '{col}' must not be null/empty",
                "Non-null value", "null/empty", severity, chunk_index, ts
            ))
        return issues

    # ─────────────────────────────────────────
    # V2: Data type — FIX Issue 1: handles pincode
    # ─────────────────────────────────────────

    def _check_data_type(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        dtype = rule.get("data_type", "string")
        severity = rule.get("severity", "Medium")
        if col not in df.columns:
            return []
        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            if not _check_dtype(str(val), dtype):
                issues.append(self._make_issue(
                    idx, col, "TYPE_MISMATCH",
                    f"Field '{col}' expected type '{dtype}'",
                    dtype, str(val), severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V3: Pattern / Format
    # ─────────────────────────────────────────

    def _check_pattern_format(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        pattern_key = rule.get("pattern_key", "custom")
        custom_pattern = rule.get("custom_pattern", "")
        severity = rule.get("severity", "Medium")
        if col not in df.columns:
            return []

        pattern = custom_pattern if pattern_key == "custom" else PATTERNS.get(pattern_key, "")
        if not pattern:
            return []

        compiled = re.compile(pattern)
        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            if not compiled.match(str(val).strip()):
                issues.append(self._make_issue(
                    idx, col, "FORMAT_VIOLATION",
                    f"Field '{col}' must match pattern '{pattern_key}'",
                    f"Pattern: {pattern}", str(val), severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V4: Allowed values
    # ─────────────────────────────────────────

    def _check_allowed_values(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        allowed = set(str(v) for v in rule.get("values", []))
        case_sensitive = rule.get("case_sensitive", False)
        severity = rule.get("severity", "High")
        if col not in df.columns or not allowed:
            return []

        if not case_sensitive:
            allowed_lower = {v.lower() for v in allowed}

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            s = str(val)
            ok = (s in allowed) if case_sensitive else (s.lower() in allowed_lower)
            if not ok:
                issues.append(self._make_issue(
                    idx, col, "INVALID_VALUE",
                    f"Field '{col}' must be one of: {', '.join(sorted(allowed)[:10])}",
                    f"One of: {', '.join(sorted(allowed)[:10])}", s, severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V5: Range
    # ─────────────────────────────────────────

    def _check_range(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        min_val = rule.get("min")
        max_val = rule.get("max")
        severity = rule.get("severity", "Medium")
        if col not in df.columns:
            return []

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            try:
                n = float(str(val).replace(",", ""))
            except ValueError:
                continue
            if (min_val is not None and n < min_val) or (max_val is not None and n > max_val):
                expected = f"[{min_val}, {max_val}]"
                issues.append(self._make_issue(
                    idx, col, "OUT_OF_RANGE",
                    f"Field '{col}' must be in range {expected}",
                    expected, str(val), severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V6: PK Uniqueness (cross-chunk)
    # ─────────────────────────────────────────

    def _check_pk_uniqueness(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        severity = rule.get("severity", "Critical")
        if col not in df.columns:
            return []

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            key = str(val).strip()
            if key in self.pk_seen:
                issues.append(self._make_issue(
                    idx, col, "UNIQUENESS_VIOLATION",
                    f"Field '{col}' must be unique (PK) — duplicate found",
                    "Unique value", key, severity, chunk_index, ts
                ))
            else:
                self.pk_seen.add(key)
        return issues

    # ─────────────────────────────────────────
    # V7: String length
    # ─────────────────────────────────────────

    def _check_string_length(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        min_len = rule.get("min_length")
        max_len = rule.get("max_length")
        severity = rule.get("severity", "Low")
        if col not in df.columns:
            return []

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            l = len(str(val))
            if (min_len is not None and l < min_len) or (max_len is not None and l > max_len):
                issues.append(self._make_issue(
                    idx, col, "LENGTH_VIOLATION",
                    f"Field '{col}' length must be between {min_len} and {max_len}",
                    f"Length between {min_len} and {max_len}", f"Length = {l}", severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V8: Trim validation
    # ─────────────────────────────────────────

    def _check_trim_validation(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        severity = rule.get("severity", "Low")
        if col not in df.columns:
            return []

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            s = str(val)
            if s != s.strip():
                issues.append(self._make_issue(
                    idx, col, "TRIM_VIOLATION",
                    f"Field '{col}' has leading/trailing whitespace",
                    s.strip(), repr(s), severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V9: 1:1 Cardinality
    # ─────────────────────────────────────────

    def _check_cardinality_1_1(self, df, rule, chunk_index, ts):
        col_a = rule.get("column_a")
        col_b = rule.get("column_b")
        severity = rule.get("severity", "High")
        # direction: "both" (default), "a_to_b" (one A -> one B only), "b_to_a"
        direction = rule.get("direction", "both")
        if col_a not in df.columns or col_b not in df.columns:
            return []

        valid = df[[col_a, col_b]].dropna()
        a_to_b = valid.groupby(col_a)[col_b].nunique()
        b_to_a = valid.groupby(col_b)[col_a].nunique()
        violations_a = set(a_to_b[a_to_b > 1].index.tolist())  # A maps to >1 B
        violations_b = set(b_to_a[b_to_a > 1].index.tolist())  # B maps to >1 A

        # Readable expected map: for each A, the distinct B values it maps to
        a_to_b_map = valid.groupby(col_a)[col_b].apply(
            lambda x: ", ".join(sorted(x.unique().astype(str)))
        ).to_dict()
        b_to_a_map = valid.groupby(col_b)[col_a].apply(
            lambda x: ", ".join(sorted(x.unique().astype(str)))
        ).to_dict()

        issues = []
        for idx, row in df.iterrows():
            a_val = row.get(col_a)
            b_val = row.get(col_b)

            # Direction-aware flagging
            flag_a = (a_val in violations_a)  # one A -> many B
            flag_b = (b_val in violations_b)  # one B -> many A

            if direction == "a_to_b":
                # Only care that each A maps to exactly one B
                if flag_a:
                    issues.append(self._make_issue(
                        idx, f"{col_a}→{col_b}", "CARDINALITY_VIOLATION",
                        f"'{col_a}' must map to exactly 1 '{col_b}'",
                        f"{col_a}='{a_val}' → exactly 1 {col_b}",
                        f"{col_a}='{a_val}' maps to: {a_to_b_map.get(a_val)}",
                        severity, chunk_index, ts
                    ))
            elif direction == "b_to_a":
                if flag_b:
                    issues.append(self._make_issue(
                        idx, f"{col_b}→{col_a}", "CARDINALITY_VIOLATION",
                        f"'{col_b}' must map to exactly 1 '{col_a}'",
                        f"{col_b}='{b_val}' → exactly 1 {col_a}",
                        f"{col_b}='{b_val}' maps to: {b_to_a_map.get(b_val)}",
                        severity, chunk_index, ts
                    ))
            else:  # both
                if flag_a or flag_b:
                    expected_b = a_to_b_map.get(a_val, "Single value")
                    issues.append(self._make_issue(
                        idx, f"{col_a}↔{col_b}", "CARDINALITY_VIOLATION",
                        f"1:1 cardinality violated between '{col_a}' and '{col_b}'",
                        f"{col_a}='{a_val}' → should map to exactly 1 {col_b}",
                        f"{col_a}='{a_val}' maps to: {expected_b}",
                        severity, chunk_index, ts
                    ))
        return issues

    # ─────────────────────────────────────────
    # V10: 1:N Cardinality
    # FIX Bug C: clarified semantics — flags when N-side maps to multiple 1-side values
    # ─────────────────────────────────────────

    def _check_cardinality_1_n(self, df, rule, chunk_index, ts):
        col_one = rule.get("column_one")   # the "1" side (e.g. Department)
        col_many = rule.get("column_many") # the "N" side (e.g. Employee) — each must map to ONE parent
        severity = rule.get("severity", "Medium")
        if col_one not in df.columns or col_many not in df.columns:
            return []

        # Violation: a value on the many-side maps to more than one parent on the one-side
        # e.g. Employee "E001" appears in both "HR" and "Finance" departments → violation
        valid = df[[col_one, col_many]].dropna()
        many_to_parents = valid.groupby(col_many)[col_one].apply(
            lambda x: sorted(x.unique().astype(str))
        ).to_dict()
        violations = {k: v for k, v in many_to_parents.items() if len(v) > 1}

        issues = []
        for idx, row in df.iterrows():
            many_val = row.get(col_many)
            if many_val in violations:
                parents = ", ".join(violations[many_val])
                issues.append(self._make_issue(
                    idx, f"{col_one}→{col_many}", "CARDINALITY_VIOLATION",
                    f"1:N violated: '{col_many}' value maps to multiple '{col_one}' values",
                    f"Single '{col_one}' parent",
                    f"'{many_val}' maps to: {parents}",
                    severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V11: Reference existence
    # FIX Issue 5: Expected column shows actual valid values from reference
    # ─────────────────────────────────────────

    def _check_reference_existence(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        ref_name = rule.get("reference_file")
        ref_col = rule.get("reference_column")
        severity = rule.get("severity", "High")
        # Optional: key columns for meaningful expected value lookup
        key_col_data = rule.get("key_column_in_data")
        key_col_ref = rule.get("key_column_in_ref")

        if col not in df.columns:
            return []

        ref_df = self.reference_files.get(ref_name)
        if ref_df is None or ref_col not in ref_df.columns:
            return []

        valid_values = set(ref_df[ref_col].dropna().astype(str).str.strip())

        # FIX Issue 5: build a key→valid_values map if key columns are configured
        key_to_valid: Dict[str, str] = {}
        if key_col_data and key_col_ref and key_col_ref in ref_df.columns:
            for key_val, grp in ref_df.groupby(key_col_ref):
                valid_for_key = ", ".join(
                    sorted(grp[ref_col].dropna().astype(str).str.strip().unique())
                )
                key_to_valid[str(key_val).strip()] = valid_for_key

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            s = str(val).strip()
            if s not in valid_values:
                # FIX Issue 5: look up what values ARE valid for this record's key
                expected_str = "Value must exist in reference"
                if key_col_data and key_col_data in df.columns:
                    data_key = str(df.at[idx, key_col_data]).strip()
                    if data_key in key_to_valid:
                        expected_str = f"Valid values for {key_col_data}='{data_key}': {key_to_valid[data_key]}"
                    else:
                        expected_str = f"No reference entry found for {key_col_data}='{data_key}'"

                issues.append(self._make_issue(
                    idx, col, "REFERENCE_NOT_FOUND",
                    f"'{col}' value not found in reference '{ref_name}.{ref_col}'",
                    expected_str, s, severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V12: Cross-field tuple match
    # FIX Issue 7: Expected column shows all valid values for the key field
    # ─────────────────────────────────────────

    def _check_cross_field_tuple(self, df, rule, chunk_index, ts):
        columns = rule.get("columns", [])
        ref_name = rule.get("reference_file")
        ref_columns = rule.get("reference_columns", columns)
        severity = rule.get("severity", "High")
        # match_mode: "exact" (default), "fuzzy", "code_only"
        match_mode = rule.get("match_mode", "exact")
        fuzzy_threshold = rule.get("fuzzy_threshold", 80)

        ref_df = self.reference_files.get(ref_name)
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols or ref_df is None:
            return []

        if isinstance(ref_columns, str):
            ref_columns = [c.strip() for c in ref_columns.split(",") if c.strip()]

        missing_ref_cols = [c for c in ref_columns if c not in ref_df.columns]
        if missing_ref_cols:
            return []

        # ── code_only mode: just check first (key) column exists in reference
        if match_mode == "code_only" and len(ref_columns) >= 1:
            key_col_data = columns[0]
            key_col_ref = ref_columns[0]
            valid_keys = set(ref_df[key_col_ref].dropna().astype(str).str.strip())
            issues = []
            for idx, row in df.iterrows():
                kv = str(row[key_col_data]).strip()
                if kv and kv.lower() not in {"none", "nan", ""} and kv not in valid_keys:
                    issues.append(self._make_issue(
                        idx, "+".join(columns), "CROSS_FIELD_VIOLATION",
                        f"Key '{key_col_data}'='{kv}' not found in reference '{ref_name}'",
                        f"'{key_col_data}' must exist in reference", kv,
                        severity, chunk_index, ts
                    ))
            return issues

        # Build set of all valid tuples (exact mode)
        valid_tuples: set = set(
            tuple(str(row[c]).strip() for c in ref_columns)
            for _, row in ref_df.iterrows()
        )

        # Build key→valid_dependents map (deduplicated) for report Expected column
        key_to_valid: Dict[str, List[str]] = {}
        # Also a key→set-of-dependent-value-strings for fuzzy comparison
        key_to_dep_values: Dict[str, List[str]] = {}
        if len(ref_columns) >= 2:
            key_ref_col = ref_columns[0]
            dep_ref_cols = ref_columns[1:]
            for key_val, grp in ref_df.groupby(key_ref_col):
                dep_strs_seen = set()
                dep_strs = []
                dep_values = []
                for _, dep_row in grp.iterrows():
                    dep_str = " | ".join(
                        f"{dc}={str(dep_row[dc]).strip()}" for dc in dep_ref_cols if dc in dep_row
                    )
                    # FIX: dedup the displayed combinations
                    if dep_str not in dep_strs_seen:
                        dep_strs_seen.add(dep_str)
                        dep_strs.append(dep_str)
                    # store raw dependent value (first dep col) for fuzzy
                    dep_values.append(str(dep_row[dep_ref_cols[0]]).strip())
                key_to_valid[str(key_val).strip()] = dep_strs
                key_to_dep_values[str(key_val).strip()] = list(set(dep_values))

        issues = []
        for idx, row in df.iterrows():
            t = tuple(str(row[c]).strip() for c in columns)
            key_data_val = t[0] if t else ""

            # ── fuzzy mode: key must match exactly, dependent value compared by similarity
            if match_mode == "fuzzy" and len(columns) >= 2:
                if key_data_val not in key_to_dep_values:
                    # key itself not in reference
                    if key_data_val and key_data_val.lower() not in {"none", "nan", ""}:
                        issues.append(self._make_issue(
                            idx, "+".join(columns), "CROSS_FIELD_VIOLATION",
                            f"Key '{columns[0]}'='{key_data_val}' not found in reference '{ref_name}'",
                            f"No reference entry for {columns[0]}='{key_data_val}'", str(t),
                            severity, chunk_index, ts
                        ))
                    continue
                actual_dep = t[1].strip()
                candidates = key_to_dep_values[key_data_val]
                best = max(
                    (_similarity(actual_dep, cand) for cand in candidates),
                    default=0
                )
                if best < fuzzy_threshold:
                    valid_list = key_to_valid.get(key_data_val, [])
                    shown = "; ".join(valid_list[:10])
                    issues.append(self._make_issue(
                        idx, "+".join(columns), "CROSS_FIELD_VIOLATION",
                        f"'{columns[1]}' does not match (fuzzy {best}% < {fuzzy_threshold}%) for {columns[0]}='{key_data_val}'",
                        f"For {columns[0]}='{key_data_val}', expected: {shown}",
                        str(t), severity, chunk_index, ts
                    ))
                continue

            # ── exact mode (default)
            if t not in valid_tuples:
                if key_data_val in key_to_valid:
                    valid_list = key_to_valid[key_data_val]
                    if len(valid_list) <= 10:
                        expected_str = f"For {columns[0]}='{key_data_val}', valid combinations: {'; '.join(valid_list)}"
                    else:
                        shown = "; ".join(valid_list[:10])
                        expected_str = (
                            f"For {columns[0]}='{key_data_val}', valid combinations "
                            f"({len(valid_list)} total, showing first 10): {shown}"
                        )
                else:
                    expected_str = f"No reference entry found for {columns[0]}='{key_data_val}'"

                issues.append(self._make_issue(
                    idx, "+".join(columns), "CROSS_FIELD_VIOLATION",
                    f"Tuple ({', '.join(columns)}) not found in reference '{ref_name}'",
                    expected_str,
                    str(t),
                    severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V13: Conditional rule (bidirectional)
    # ─────────────────────────────────────────

    def _check_conditional_rule(self, df, rule, chunk_index, ts):
        col_a = rule.get("column_a")
        col_b = rule.get("column_b")
        condition_value = rule.get("condition_value")
        expected_value = rule.get("expected_value")
        bidirectional = rule.get("bidirectional", False)
        severity = rule.get("severity", "Medium")
        if col_a not in df.columns or col_b not in df.columns:
            return []

        issues = []
        for idx, row in df.iterrows():
            a_val = str(row[col_a]) if not pd.isna(row[col_a]) else None
            b_val = str(row[col_b]) if not pd.isna(row[col_b]) else None

            if a_val == str(condition_value):
                b_ok = (b_val == str(expected_value)) if expected_value is not None else (b_val is not None)
                if not b_ok:
                    issues.append(self._make_issue(
                        idx, col_b, "CUSTOM_RULE_VIOLATION",
                        f"When '{col_a}'='{condition_value}', '{col_b}' must be '{expected_value}'",
                        f"'{expected_value}'", b_val, severity, chunk_index, ts
                    ))

            if bidirectional and b_val == str(expected_value):
                if a_val != str(condition_value):
                    issues.append(self._make_issue(
                        idx, col_a, "CUSTOM_RULE_VIOLATION",
                        f"When '{col_b}'='{expected_value}', '{col_a}' must be '{condition_value}'",
                        f"'{condition_value}'", a_val, severity, chunk_index, ts
                    ))
        return issues

    # ─────────────────────────────────────────
    # V14: Mutual exclusivity
    # ─────────────────────────────────────────

    def _check_mutual_exclusivity(self, df, rule, chunk_index, ts):
        columns = rule.get("columns", [])
        direction = rule.get("direction", "at_most_one")
        severity = rule.get("severity", "High")

        valid_cols = [c for c in columns if c in df.columns]
        if not valid_cols:
            return []

        issues = []
        for idx, row in df.iterrows():
            non_null = [c for c in valid_cols if not pd.isna(row[c]) and str(row[c]).strip() != ""]
            count = len(non_null)
            violated = False
            if direction == "at_most_one" and count > 1:
                violated = True
            elif direction == "exactly_one" and count != 1:
                violated = True
            elif direction == "none_or_one" and count > 1:
                violated = True

            if violated:
                issues.append(self._make_issue(
                    idx, "+".join(valid_cols), "CROSS_FIELD_VIOLATION",
                    f"Mutual exclusivity ({direction}) violated for: {valid_cols}",
                    f"{direction} — only 1 of {valid_cols} should be filled",
                    f"{count} fields filled: {non_null}",
                    severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V15: Co-occurrence
    # ─────────────────────────────────────────

    def _check_co_occurrence(self, df, rule, chunk_index, ts):
        col_a = rule.get("column_a")
        col_b = rule.get("column_b")
        mode = rule.get("mode", "both_required")
        severity = rule.get("severity", "Medium")
        if col_a not in df.columns or col_b not in df.columns:
            return []

        issues = []
        for idx, row in df.iterrows():
            a_filled = not pd.isna(row[col_a]) and str(row[col_a]).strip() != ""
            b_filled = not pd.isna(row[col_b]) and str(row[col_b]).strip() != ""

            if mode == "both_required":
                if a_filled != b_filled:
                    issues.append(self._make_issue(
                        idx, f"{col_a}+{col_b}", "CROSS_FIELD_VIOLATION",
                        f"Both '{col_a}' and '{col_b}' must be filled or both empty",
                        "Both fields filled",
                        f"'{col_a}' filled={a_filled}, '{col_b}' filled={b_filled}",
                        severity, chunk_index, ts
                    ))
            elif mode == "both_empty":
                if a_filled or b_filled:
                    issues.append(self._make_issue(
                        idx, f"{col_a}+{col_b}", "CROSS_FIELD_VIOLATION",
                        f"Both '{col_a}' and '{col_b}' must be empty",
                        "Both fields empty",
                        f"'{col_a}' filled={a_filled}, '{col_b}' filled={b_filled}",
                        severity, chunk_index, ts
                    ))
        return issues

    # ─────────────────────────────────────────
    # V16: Value dependency
    # ─────────────────────────────────────────

    def _check_value_dependency(self, df, rule, chunk_index, ts):
        col_a = rule.get("column_a")
        col_b = rule.get("column_b")
        bidirectional = rule.get("bidirectional", True)
        severity = rule.get("severity", "Medium")
        if col_a not in df.columns or col_b not in df.columns:
            return []

        issues = []
        for idx, row in df.iterrows():
            a_filled = not pd.isna(row[col_a]) and str(row[col_a]).strip() != ""
            b_filled = not pd.isna(row[col_b]) and str(row[col_b]).strip() != ""

            if a_filled and not b_filled:
                issues.append(self._make_issue(
                    idx, col_b, "CUSTOM_RULE_VIOLATION",
                    f"When '{col_a}' is filled, '{col_b}' must also be filled",
                    "Non-empty value", "Empty", severity, chunk_index, ts
                ))
            if bidirectional and b_filled and not a_filled:
                issues.append(self._make_issue(
                    idx, col_a, "CUSTOM_RULE_VIOLATION",
                    f"When '{col_b}' is filled, '{col_a}' must also be filled",
                    "Non-empty value", "Empty", severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V17: Arithmetic consistency
    # ─────────────────────────────────────────

    def _check_arithmetic_consistency(self, df, rule, chunk_index, ts):
        col_result = rule.get("column_result")
        operands = rule.get("operands", [])
        operator = rule.get("operator", "+")
        tolerance = rule.get("tolerance", 0.01)
        severity = rule.get("severity", "Medium")

        all_cols = operands + ([col_result] if col_result else [])
        if not all(c in df.columns for c in all_cols):
            return []

        issues = []
        for idx, row in df.iterrows():
            try:
                vals = [float(str(row[c]).replace(",", "")) for c in operands]
                result_val = float(str(row[col_result]).replace(",", "")) if col_result else None

                if operator == "+":
                    computed = sum(vals)
                elif operator == "-" and len(vals) == 2:
                    computed = vals[0] - vals[1]
                elif operator == "*" and len(vals) == 2:
                    computed = vals[0] * vals[1]
                elif operator == "/" and len(vals) == 2:
                    computed = vals[0] / vals[1] if vals[1] != 0 else None
                else:
                    computed = sum(vals)

                if result_val is not None and computed is not None:
                    if abs(computed - result_val) > tolerance:
                        issues.append(self._make_issue(
                            idx, col_result, "CROSS_FIELD_VIOLATION",
                            f"Arithmetic check: {' '.join(operands)} {operator} should equal {col_result}",
                            f"Computed = {computed:.4f}", f"Actual = {result_val:.4f}",
                            severity, chunk_index, ts
                        ))
            except (ValueError, TypeError):
                continue

        return issues

    # ─────────────────────────────────────────
    # V18: Date sequence
    # ─────────────────────────────────────────

    def _check_date_sequence(self, df, rule, chunk_index, ts):
        col_start = rule.get("column_start")
        col_end = rule.get("column_end")
        strict = rule.get("strict", False)
        severity = rule.get("severity", "High")
        if col_start not in df.columns or col_end not in df.columns:
            return []

        issues = []
        for idx, row in df.iterrows():
            try:
                start_val = _parse_any_date(str(row[col_start]))
                end_val = _parse_any_date(str(row[col_end]))
                if start_val is None or end_val is None:
                    continue
                violated = (start_val >= end_val) if strict else (start_val > end_val)
                if violated:
                    op = "<" if strict else "<="
                    issues.append(self._make_issue(
                        idx, f"{col_start}→{col_end}", "CROSS_FIELD_VIOLATION",
                        f"Date sequence: '{col_start}' must be {op} '{col_end}'",
                        f"{col_start} {op} {col_end}",
                        f"{row[col_start]} > {row[col_end]}",
                        severity, chunk_index, ts
                    ))
            except Exception:
                continue

        return issues

    # ─────────────────────────────────────────
    # V19: Completeness score per record
    # ─────────────────────────────────────────

    def _check_completeness_score(self, df, rule, chunk_index, ts):
        columns = rule.get("columns", df.columns.tolist())
        threshold = rule.get("threshold", 0.8)
        severity = rule.get("severity", "Low")

        valid_cols = [c for c in columns if c in df.columns]
        if not valid_cols:
            return []

        issues = []
        for idx, row in df.iterrows():
            filled = sum(
                1 for c in valid_cols
                if not pd.isna(row[c]) and str(row[c]).strip() != ""
            )
            score = filled / len(valid_cols)
            if score < threshold:
                missing = [c for c in valid_cols if pd.isna(row[c]) or str(row[c]).strip() == ""]
                issues.append(self._make_issue(
                    idx,
                    "+".join(valid_cols[:3]) + ("..." if len(valid_cols) > 3 else ""),
                    "COMPLETENESS_BELOW_THRESHOLD",
                    f"Record completeness {score:.0%} below threshold {threshold:.0%}",
                    f">= {threshold:.0%} ({int(threshold * len(valid_cols))} of {len(valid_cols)} fields filled)",
                    f"{score:.0%} — missing: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
                    severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V20: Date year range (for MMM YYYY or any date)
    # ─────────────────────────────────────────

    def _check_date_year_range(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        min_year = rule.get("min_year", 2000)
        max_year = rule.get("max_year", 2100)
        severity = rule.get("severity", "Medium")
        if col not in df.columns:
            return []

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            year = _extract_year(str(val))
            if year is None:
                issues.append(self._make_issue(
                    idx, col, "FORMAT_VIOLATION",
                    f"Field '{col}' year could not be parsed",
                    f"Year between {min_year} and {max_year}", str(val),
                    severity, chunk_index, ts
                ))
            elif year < min_year or year > max_year:
                issues.append(self._make_issue(
                    idx, col, "OUT_OF_RANGE",
                    f"Field '{col}' year must be between {min_year} and {max_year}",
                    f"Year in [{min_year}, {max_year}]", f"Year = {year} (from '{val}')",
                    severity, chunk_index, ts
                ))
        return issues

    # ─────────────────────────────────────────
    # V21: Grouped Fuzzy Duplicate
    # Groups rows by group_by_columns, then within each group finds
    # exact and fuzzy duplicates in the compare_column.
    # ─────────────────────────────────────────

    def _check_grouped_fuzzy_duplicate(self, df, rule, chunk_index, ts):
        group_cols = rule.get("group_by_columns", [])
        compare_col = rule.get("compare_column")
        threshold = rule.get("threshold", 80)
        severity = rule.get("severity", "High")

        group_cols = [c for c in group_cols if c in df.columns]
        if not group_cols or compare_col not in df.columns:
            return []

        issues = []

        def _norm(v):
            if pd.isna(v):
                return ""
            return str(v).strip().lower()

        # Build IDF (rare-word weights) from ALL compare values in this df,
        # so distinctive words (shop names) outweigh common suffixes
        # like 'paint', 'hardware', 'store'.
        idf = _build_idf(df[compare_col].dropna().astype(str).tolist())

        work = df[[compare_col] + group_cols].copy()
        work["_grpkey"] = work[group_cols].apply(
            lambda r: "||".join(_norm(r[c]) for c in group_cols), axis=1
        )

        for grp_key, grp in work.groupby("_grpkey"):
            if grp_key.replace("|", "").strip() == "":
                continue
            members = [
                (idx, str(row[compare_col]).strip())
                for idx, row in grp.iterrows()
                if not pd.isna(row[compare_col]) and str(row[compare_col]).strip() != ""
            ]
            if len(members) < 2:
                continue

            n = len(members)

            # Performance: block by first distinctive token so we don't do a
            # full O(n^2) scan on very large groups. Names that share no
            # distinctive token are almost never duplicates.
            blocks: Dict[str, List] = {}
            for idx_m, name_m in members:
                toks = _tokenize_name(name_m)
                # pick the most distinctive (highest IDF) token as the block key
                if toks:
                    block_key = max(toks, key=lambda t: idf.get(t, 0))
                else:
                    block_key = name_m.lower()
                blocks.setdefault(block_key, []).append((idx_m, name_m))

            grp_desc = " / ".join(f"{c}='{grp.iloc[0][c]}'" for c in group_cols)

            for block_key, block_members in blocks.items():
                bn = len(block_members)
                if bn < 2:
                    continue
                for i in range(bn):
                    idx_i, name_i = block_members[i]
                    best_score = 0
                    best_match_name = None
                    best_match_idx = None
                    for j in range(bn):
                        if i == j:
                            continue
                        idx_j, name_j = block_members[j]
                        score = _weighted_name_similarity(name_i, name_j, idf)
                        if score > best_score:
                            best_score = score
                            best_match_name = name_j
                            best_match_idx = idx_j

                    if best_score >= threshold:
                        dup_type = "EXACT" if best_score >= 100 else f"FUZZY {best_score}%"
                        issues.append(self._make_issue(
                            idx_i, compare_col, "CARDINALITY_VIOLATION",
                            f"Possible duplicate '{compare_col}' within group ({grp_desc})",
                            f"Unique '{compare_col}' per group",
                            f"{dup_type} duplicate of Record {best_match_idx} "
                            f"('{best_match_name}') — both have {grp_desc}",
                            severity, chunk_index, ts
                        ))

        return issues

    # ─────────────────────────────────────────
    # V22: Mapping Cardinality (single file)
    # Task 1 — e.g. Sales Group -> Sales Office (expected 1:many).
    # Produces a mapping table + anomaly table (stored in _analysis_tables)
    # and emits issue rows for the anomalies.
    # ─────────────────────────────────────────

    def _check_mapping_cardinality(self, df, rule, chunk_index, ts):
        group_col = rule.get("group_column")      # e.g. Sales Group
        list_col = rule.get("list_column")         # e.g. Sales Office
        severity = rule.get("severity", "Medium")
        max_display = int(rule.get("max_display_values", 15))
        if group_col not in df.columns or list_col not in df.columns:
            return []

        def _n(v):
            return "" if pd.isna(v) else str(v).strip()

        work = df[[group_col, list_col]].copy()
        work[group_col] = work[group_col].map(_n)
        work[list_col] = work[list_col].map(_n)

        # ── Mapping summary: each group -> distinct list values.
        # Rule: one Sales Group must map to exactly ONE Sales Office.
        #   1 office  -> 1:1  (OK)
        #   >1 office -> 1:many  (VIOLATION — same SG in multiple SOs)
        # (A Sales Office having multiple Sales Groups is allowed and NOT flagged.)
        mapping_rows = []
        group_to_vals: Dict[str, list] = {}
        for gval, grp in work.groupby(group_col):
            vals = sorted(set(v for v in grp[list_col] if v != ""))
            group_to_vals[gval] = vals
            shown = ", ".join(vals[:max_display])
            if len(vals) > max_display:
                shown += f"  …(+{len(vals) - max_display} more)"

            if gval == "":
                cardinality = "-"
                flag = "BLANK GROUP"
            elif len(vals) == 0:
                cardinality = "-"
                flag = "NO MAPPING"
            elif len(vals) == 1:
                cardinality = "1:1"
                flag = ""
            else:
                cardinality = "1:many"
                flag = "VIOLATION"

            mapping_rows.append({
                group_col: gval if gval else "(blank)",
                f"{list_col} Count": len(vals),
                f"{list_col} Values": shown,
                "Cardinality": cardinality,
                "Flag": flag,
            })
        mapping_df = pd.DataFrame(mapping_rows).sort_values(
            f"{list_col} Count", ascending=False
        ).reset_index(drop=True)

        # ── Anomalies: Sales Groups mapped to MULTIPLE Sales Offices (the violation)
        anomaly_rows = []
        issues = []

        for gval, vals in group_to_vals.items():
            if gval == "":
                continue
            if len(vals) > 1:
                shown = ", ".join(vals[:max_display])
                if len(vals) > max_display:
                    shown += f"  …(+{len(vals) - max_display} more)"
                anomaly_rows.append({
                    "Anomaly Type": f"{group_col} mapped to multiple {list_col}s",
                    group_col: gval,
                    f"{list_col} Count": len(vals),
                    f"{list_col}s": shown,
                    "Detail": f"'{gval}' maps to {len(vals)} different {list_col} values (should be 1)",
                })
                # Emit an issue row for the Validation Report
                issues.append(self._make_issue(
                    gval, group_col, "CARDINALITY_VIOLATION",
                    f"{group_col} must map to a single {list_col}",
                    f"One {list_col} per {group_col}",
                    f"'{gval}' maps to {len(vals)} {list_col}s: {shown}",
                    severity, chunk_index, ts
                ))

        # Also record blank-group / blank-office as informational anomalies
        blank_grp = int((work[group_col] == "").sum())
        blank_list = int((work[list_col] == "").sum())
        if blank_grp:
            anomaly_rows.append({
                "Anomaly Type": f"Blank {group_col}",
                group_col: "(blank)",
                f"{list_col} Count": "-",
                f"{list_col}s": "-",
                "Detail": f"{blank_grp} row(s) have a blank {group_col}",
            })
        if blank_list:
            anomaly_rows.append({
                "Anomaly Type": f"Blank {list_col}",
                group_col: "-",
                f"{list_col} Count": "-",
                f"{list_col}s": "(blank)",
                "Detail": f"{blank_list} row(s) have a blank {list_col}",
            })

        anomaly_df = pd.DataFrame(anomaly_rows) if anomaly_rows else pd.DataFrame(
            columns=["Anomaly Type", group_col, f"{list_col} Count", f"{list_col}s", "Detail"]
        )

        # ── Full expanded pairs sheet (every group+value pair, nothing hidden)
        expanded_rows = []
        for gval, vals in group_to_vals.items():
            for v in vals:
                expanded_rows.append({group_col: gval if gval else "(blank)", list_col: v})
        expanded_df = pd.DataFrame(expanded_rows) if expanded_rows else pd.DataFrame(
            columns=[group_col, list_col]
        )

        # Store tables for the report generator
        self._analysis_tables["SG-SO Mapping"] = mapping_df
        self._analysis_tables["SG-SO Anomalies"] = anomaly_df
        self._analysis_tables["SG-SO Full Pairs"] = expanded_df

        return issues

    # ─────────────────────────────────────────
    # V23: Cross-File Cardinality (two reference files)
    # Task 2 — match Sales Group between dealer file and employee file.
    # Classifies 1:1 / 1:many / many:1 / many:many and flags gap cases.
    # ─────────────────────────────────────────

    def _check_cross_file_cardinality(self, df, rule, chunk_index, ts):
        file_a = rule.get("file_a")            # e.g. dealer reference
        file_b = rule.get("file_b")            # e.g. employee reference
        sg_col_a = rule.get("sg_column_a")     # Customer Sales Group
        sg_col_b = rule.get("sg_column_b")     # Sales Group 1
        key_col_a = rule.get("key_column_a")   # Customer (dealer code)
        key_col_b = rule.get("key_column_b")   # Employee ID
        label_a = rule.get("label_a", "Dealer")
        label_b = rule.get("label_b", "Employee")
        severity = rule.get("severity", "Medium")
        max_display = int(rule.get("max_display_values", 15))

        df_a = self.reference_files.get(file_a)
        df_b = self.reference_files.get(file_b)
        if df_a is None or df_b is None:
            return []
        if sg_col_a not in df_a.columns or sg_col_b not in df_b.columns:
            return []
        if key_col_a not in df_a.columns or key_col_b not in df_b.columns:
            return []

        def _n(v):
            return "" if pd.isna(v) else str(v).strip()

        # Build SG -> set of keys, for each file
        a_map: Dict[str, list] = {}
        for _, r in df_a[[sg_col_a, key_col_a]].iterrows():
            sg = _n(r[sg_col_a]); key = _n(r[key_col_a])
            if sg == "":
                continue
            a_map.setdefault(sg, [])
            if key:
                a_map[sg].append(key)

        b_map: Dict[str, list] = {}
        for _, r in df_b[[sg_col_b, key_col_b]].iterrows():
            sg = _n(r[sg_col_b]); key = _n(r[key_col_b])
            if sg == "":
                continue
            b_map.setdefault(sg, [])
            if key:
                b_map[sg].append(key)

        all_sgs = sorted(set(a_map.keys()) | set(b_map.keys()))

        def _fmt(vals):
            uniq = sorted(set(vals))
            shown = ", ".join(uniq[:max_display])
            if len(uniq) > max_display:
                shown += f"  …(+{len(uniq) - max_display} more)"
            return shown if shown else "-"

        rows = []
        issues = []
        for sg in all_sgs:
            a_keys = sorted(set(a_map.get(sg, [])))
            b_keys = sorted(set(b_map.get(sg, [])))
            na, nb = len(a_keys), len(b_keys)

            # Classify.
            # Gap cases (one side missing) -> REASSIGN (both directions).
            # Cardinality verdicts (Nerolac field-sales ownership logic):
            #   1:1      -> Valid   (clean single ownership)
            #   many:1   -> Valid   (one employee handles many dealers — normal)
            #   1:many   -> Invalid (one dealer split across many employees)
            #   many:many-> Invalid (tangled, no clear accountability)
            if na > 0 and nb == 0:
                cardinality = "-"
                flag = "REASSIGN"
                flag_detail = f"{label_a} SG has no matching {label_b}"
            elif na == 0 and nb > 0:
                cardinality = "-"
                flag = "REASSIGN"
                flag_detail = f"{label_b} SG has no matching {label_a}"
            else:
                if na == 1 and nb == 1:
                    cardinality = "1:1"
                    flag = "Valid"
                    flag_detail = "Clean single ownership"
                elif na > 1 and nb == 1:
                    cardinality = "many:1"
                    flag = "Valid"
                    flag_detail = "One employee handles many dealers"
                elif na == 1 and nb > 1:
                    cardinality = "1:many"
                    flag = "Invalid"
                    flag_detail = "One dealer split across multiple employees"
                else:
                    cardinality = "many:many"
                    flag = "Invalid"
                    flag_detail = "Multiple dealers and employees — no clear ownership"

            rows.append({
                "Sales Group": sg,
                f"{label_a} Count": na,
                f"{label_a}s": _fmt(a_keys),
                f"{label_b} Count": nb,
                f"{label_b}s": _fmt(b_keys),
                "Cardinality": cardinality,
                "Flag": flag,
                "Flag Detail": flag_detail,
            })

            # Emit issue rows for REASSIGN and Invalid cases
            if flag == "REASSIGN":
                issues.append(self._make_issue(
                    sg, "Sales Group", "CARDINALITY_VIOLATION",
                    f"Sales Group gap — reassign",
                    f"Matching {label_a} and {label_b} for this Sales Group",
                    flag_detail + f" ({label_a}={na}, {label_b}={nb})",
                    severity, chunk_index, ts
                ))
            elif flag == "Invalid":
                issues.append(self._make_issue(
                    sg, "Sales Group", "CARDINALITY_VIOLATION",
                    f"Invalid {cardinality} mapping between {label_a} and {label_b}",
                    "Valid ownership (1:1 or many:1)",
                    f"{cardinality}: {na} {label_a.lower()}(s), {nb} {label_b.lower()}(s) — {flag_detail}",
                    severity, chunk_index, ts
                ))

        cardinality_df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["Sales Group", f"{label_a} Count", f"{label_a}s",
                     f"{label_b} Count", f"{label_b}s", "Cardinality", "Flag", "Flag Detail"]
        )

        self._analysis_tables["Cross-File Cardinality"] = cardinality_df

        return issues

    # ─────────────────────────────────────────
    # V24: Suspicious Number (fake / placeholder phone numbers)
    # Configurable detection of: all-same-digit, repeating blocks,
    # low digit variety, sequential runs, and wrong length.
    # Nulls are skipped (use a separate mandatory rule if needed).
    # ─────────────────────────────────────────

    def _check_suspicious_number(self, df, rule, chunk_index, ts):
        col = rule.get("column")
        severity = rule.get("severity", "Medium")
        expected_length = int(rule.get("expected_length", 10))
        check_length = rule.get("check_length", True)
        check_all_same = rule.get("check_all_same", True)
        check_repeating = rule.get("check_repeating_block", True)
        repeat_max_block = int(rule.get("repeat_max_block", 3))
        check_low_variety = rule.get("check_low_variety", True)
        min_distinct = int(rule.get("min_distinct_digits", 3))
        check_sequential = rule.get("check_sequential", False)

        if col not in df.columns:
            return []

        issues = []
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            raw = str(val).strip()
            if raw == "" or raw.lower() in ("none", "nan"):
                continue
            digits = re.sub(r"\D", "", raw)
            if digits == "":
                continue  # no digits at all — a format rule should catch this

            reasons = []

            # 1. Length check
            if check_length and len(digits) != expected_length:
                reasons.append(f"length {len(digits)} != {expected_length}")

            # 2. All-same-digit
            if check_all_same and len(set(digits)) == 1:
                reasons.append(f"all digits same ('{digits[0]}')")

            # 3. Low digit variety
            if check_low_variety:
                nd = len(set(digits))
                if nd < min_distinct:
                    reasons.append(f"only {nd} distinct digit(s) (min {min_distinct})")

            # 4. Repeating block (a block of length 1..repeat_max_block repeated
            #    to fill the whole string)
            if check_repeating and _is_repeating_block(digits, repeat_max_block):
                blk = _repeating_block_of(digits, repeat_max_block)
                reasons.append(f"repeating block '{blk}'")

            # 5. Sequential ascending/descending
            if check_sequential and _is_sequential(digits):
                reasons.append("sequential digits")

            if reasons:
                issues.append(self._make_issue(
                    idx, col, "FORMAT_VIOLATION",
                    f"'{col}' looks like a fake/placeholder number",
                    f"Valid {expected_length}-digit number",
                    f"{raw} — {'; '.join(reasons)}",
                    severity, chunk_index, ts
                ))
        return issues


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

# Words that carry no business identity — ignored when comparing names
_NAME_STOPWORDS = {"and", "the", "of", "&", "a"}
# Common abbreviation / plural normalizations for business names
_NAME_NORMALIZE = {
    "h/w": "hardware", "hw": "hardware", "hdw": "hardware", "hardwares": "hardware",
    "paints": "paint", "traders": "trader", "trdrs": "trader", "trd": "trader",
    "stores": "store", "sanitry": "sanitary", "co": "company", "co.": "company",
    "ent": "enterprises", "enterprise": "enterprises",
}


def _tokenize_name(s: str) -> list:
    """Lowercase, strip punctuation, drop stopwords, normalize abbreviations."""
    import re as _re
    s = _re.sub(r"[^\w\s]", " ", s.lower())
    toks = [t for t in s.split() if t and t not in _NAME_STOPWORDS]
    return [_NAME_NORMALIZE.get(t, t) for t in toks]


def _build_idf(names: list) -> dict:
    """Build inverse-document-frequency weights from a list of names."""
    import math as _math
    from collections import Counter as _Counter
    dfc = _Counter()
    total = 0
    for name in names:
        total += 1
        for t in set(_tokenize_name(str(name))):
            dfc[t] += 1
    if total == 0:
        return {}
    return {t: _math.log((total + 1) / (c + 1)) + 1 for t, c in dfc.items()}


def _weighted_name_similarity(a: str, b: str, idf: dict) -> int:
    """
    Similarity (0-100) that weights DISTINCTIVE words over common ones.
    'Garg Paint And Hardware' vs 'Gulati Paint And Hardware' scores low
    (distinctive words differ), while 'Vishal Paint & Hardwares' vs
    'Vishal Paint And Hardware' scores high (same distinctive word,
    only common-suffix formatting differs).
    """
    import difflib as _dl
    ta, tb = _tokenize_name(a), _tokenize_name(b)
    if not ta or not tb:
        return 0
    sa, sb = set(ta), set(tb)
    if sa == sb:
        return 100
    shared = sa & sb
    allw = sa | sb
    num = sum(idf.get(t, 1.0) for t in shared)
    den = sum(idf.get(t, 1.0) for t in allw)
    token_score = (num / den) if den else 0
    # small char-level tie-breaker (helps within-token typos), order-independent
    char = _dl.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return int((0.85 * token_score + 0.15 * char) * 100)


def _char_similarity(a: str, b: str) -> int:
    """
    Plain character-level similarity (0-100) using SequenceMatcher.
    Kept for backward compatibility / person-name dedup.
    """
    import difflib
    if not a and not b:
        return 100
    if not a or not b:
        return 0
    ratio = difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
    return int(ratio * 100)


def _similarity(a: str, b: str) -> int:
    """
    Return similarity percentage (0-100) between two strings.
    Uses the max of:
      - full-string SequenceMatcher ratio
      - token-overlap ratio (handles reordered words)
      - containment bonus (handles 'PURNIMA' vs 'PURNIMA PAINTS')
    This is more forgiving of added suffixes/prefixes common in dealer names.
    Used by the cross_field_tuple fuzzy mode.
    """
    import difflib
    if not a and not b:
        return 100
    if not a or not b:
        return 0
    a_l = a.lower().strip()
    b_l = b.lower().strip()

    # 1. full ratio
    full = difflib.SequenceMatcher(None, a_l, b_l).ratio()

    # 2. token overlap (set-based, order independent)
    ta = set(a_l.split())
    tb = set(b_l.split())
    token = (len(ta & tb) / max(len(ta | tb), 1)) if (ta and tb) else 0

    # 3. containment — if shorter string's words are all inside longer
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    contain = (len(shorter & longer) / max(len(shorter), 1)) if shorter else 0

    best = max(full, token, contain)
    return int(best * 100)


def _is_repeating_block(digits: str, max_block: int) -> bool:
    """
    True if `digits` is a single block of length 1..max_block repeated to
    fill the whole string. E.g. '1212121212' (block '12'), '111...' (block '1').
    """
    n = len(digits)
    for blen in range(1, max_block + 1):
        if n % blen != 0:
            continue
        block = digits[:blen]
        if block * (n // blen) == digits:
            return True
    return False


def _repeating_block_of(digits: str, max_block: int) -> str:
    """Return the repeating block that fills `digits`, or '' if none."""
    n = len(digits)
    for blen in range(1, max_block + 1):
        if n % blen != 0:
            continue
        block = digits[:blen]
        if block * (n // blen) == digits:
            return block
    return ""


def _is_sequential(digits: str) -> bool:
    """
    True if the digits form a strictly ascending or descending run with
    step 1 (wrapping allowed for the classic '1234567890').
    """
    if len(digits) < 3:
        return False
    asc = all((int(digits[i + 1]) - int(digits[i])) % 10 == 1 for i in range(len(digits) - 1))
    desc = all((int(digits[i]) - int(digits[i + 1])) % 10 == 1 for i in range(len(digits) - 1))
    return asc or desc


def _extract_year(val: str) -> Optional[int]:
    """Extract a 4-digit year from a string like 'Jan 2025', '2025-01', '01/2025'."""
    if not val:
        return None
    m = re.search(r"(19|20)\d{2}", val)
    if m:
        return int(m.group(0))
    parsed = _parse_any_date(val)
    if parsed:
        return parsed.year
    return None

def _check_dtype(val: str, dtype: str) -> bool:
    """FIX Issue 1: added pincode and postal_code dtype checks."""
    if dtype == "integer":
        return bool(re.match(r"^-?\d+$", val.strip()))
    elif dtype == "float":
        try:
            float(val.replace(",", ""))
            return True
        except ValueError:
            return False
    elif dtype == "date":
        return _parse_any_date(val) is not None
    elif dtype == "boolean":
        return val.strip().lower() in {"true", "false", "yes", "no", "1", "0", "t", "f"}
    elif dtype == "email":
        return bool(re.match(PATTERNS.get("email", ""), val.strip()))
    elif dtype == "phone":
        return (
            bool(re.match(PATTERNS.get("phone_india", ""), val.strip())) or
            bool(re.match(PATTERNS.get("phone_e164", ""), val.strip())) or
            bool(re.match(PATTERNS.get("phone_generic_10", ""), val.strip()))
        )
    elif dtype in ("pincode", "postal_code"):
        # FIX Issue 1: validate against India 6-digit pattern; also accept other postal formats
        return (
            bool(re.match(PATTERNS.get("pincode_india", r"^\d{6}$"), val.strip())) or
            bool(re.match(PATTERNS.get("postal_us", ""), val.strip())) or
            bool(re.match(PATTERNS.get("postal_uk", ""), val.strip())) or
            bool(re.match(PATTERNS.get("postal_canada", ""), val.strip()))
        )
    return True  # string — anything goes


def _parse_any_date(val: str) -> Optional[datetime.date]:
    if not val or val.lower() in {"nan", "none", "null", ""}:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(val, dayfirst=True).date()
    except Exception:
        return None
