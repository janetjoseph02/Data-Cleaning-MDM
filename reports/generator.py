# reports/generator.py — 12-Sheet Excel Report Generator
from __future__ import annotations

import datetime
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from config import (
    APP_TITLE,
    BRAND_COLOR,
    REPORT_SEVERITY_COLORS,
    REPORT_SHEETS,
    VALIDATION_REPORT_COLS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_COLOR_HIGH,
    CONFIDENCE_COLOR_MEDIUM,
    CONFIDENCE_COLOR_LOW,
)


class ReportGenerator:
    """
    Generates a 12-sheet Excel workbook using xlsxwriter.

    Sheets
    ──────
    1.  Raw Data
    2.  Cleaned Data (with flag* cols)
    3.  Configuration Summary
    4.  Duplicate Report
    5.  Test Records Report
    6.  Validation Report
    7.  Data Quality Summary
    8.  Reference Validation Detail
    9.  Cross-field Consistency Report
    10. Address Validation Detail
    11. Review Decisions Report
    12. Cleaning & Validation Log
    """

    def __init__(
        self,
        raw_df: pd.DataFrame,
        cleaned_df: pd.DataFrame,
        validation_issues: List[Dict],
        cleaning_log: List[Dict],
        field_registry: Dict,
        cleaning_rules: Dict,
        validation_rules: List[Dict],
        address_config: Dict,
        test_detection_config: List[Dict],
        review_decisions: Dict,
        project_name: str,
        run_log: Optional[List[Dict]] = None,
        analysis_tables: Optional[Dict[str, pd.DataFrame]] = None,
    ):
        self.raw_df = raw_df
        self.cleaned_df = cleaned_df
        self.validation_issues = validation_issues
        self.cleaning_log = cleaning_log
        self.field_registry = field_registry
        self.cleaning_rules = cleaning_rules
        self.validation_rules = validation_rules
        self.address_config = address_config
        self.test_detection_config = test_detection_config
        self.review_decisions = review_decisions
        self.project_name = project_name
        self.run_log = run_log or []
        self.analysis_tables = analysis_tables or {}

    # ─────────────────────────────────────────
    # Main generate
    # ─────────────────────────────────────────

    def generate(self, output_path: Optional[str] = None) -> bytes:
        """
        Generate the workbook. Returns raw bytes.
        Optionally saves to output_path.
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            wb = writer.book
            # Shared formats
            fmts = self._build_formats(wb)

            self._sheet_raw_data(writer, wb, fmts)
            self._sheet_cleaned_data(writer, wb, fmts)
            self._sheet_config_summary(writer, wb, fmts)
            self._sheet_duplicate_report(writer, wb, fmts)
            self._sheet_test_records(writer, wb, fmts)
            self._sheet_validation_report(writer, wb, fmts)
            self._sheet_data_quality_summary(writer, wb, fmts)
            self._sheet_reference_validation(writer, wb, fmts)
            self._sheet_cross_field(writer, wb, fmts)
            self._sheet_analysis_tables(writer, wb, fmts)
            self._sheet_address_validation(writer, wb, fmts)
            self._sheet_review_decisions(writer, wb, fmts)
            self._sheet_cleaning_log(writer, wb, fmts)

        data = buf.getvalue()

        if output_path:
            Path(output_path).write_bytes(data)

        return data

    # ─────────────────────────────────────────
    # Format factory
    # ─────────────────────────────────────────

    def _build_formats(self, wb) -> Dict:
        brand = BRAND_COLOR.lstrip("#")

        header_fmt = wb.add_format({
            "bold": True, "font_color": "white",
            "bg_color": BRAND_COLOR, "border": 1,
            "text_wrap": True, "valign": "vcenter",
        })
        cell_fmt = wb.add_format({"border": 1, "valign": "vcenter"})
        title_fmt = wb.add_format({
            "bold": True, "font_size": 14,
            "font_color": BRAND_COLOR,
        })
        section_fmt = wb.add_format({
            "bold": True, "bg_color": "#D6E4F0",
            "border": 1,
        })
        red_fmt = wb.add_format({"font_color": "#E74C3C", "bold": True, "border": 1})
        amber_fmt = wb.add_format({"font_color": "#F39C12", "bold": True, "border": 1})
        green_fmt = wb.add_format({"font_color": "#27AE60", "bold": True, "border": 1})
        num_fmt = wb.add_format({"border": 1, "num_format": "#,##0"})
        pct_fmt = wb.add_format({"border": 1, "num_format": "0.0%"})
        date_fmt = wb.add_format({"border": 1, "num_format": "yyyy-mm-dd hh:mm"})
        wrap_fmt = wb.add_format({"border": 1, "text_wrap": True, "valign": "top"})

        severity_fmts = {}
        for sev, color in REPORT_SEVERITY_COLORS.items():
            severity_fmts[sev] = wb.add_format({
                "font_color": color, "bold": True, "border": 1,
            })

        return {
            "header": header_fmt,
            "cell": cell_fmt,
            "title": title_fmt,
            "section": section_fmt,
            "red": red_fmt,
            "amber": amber_fmt,
            "green": green_fmt,
            "num": num_fmt,
            "pct": pct_fmt,
            "date": date_fmt,
            "wrap": wrap_fmt,
            "severity": severity_fmts,
        }

    # ─────────────────────────────────────────
    # Helper: write DataFrame to sheet
    # ─────────────────────────────────────────

    def _write_df(
        self,
        writer,
        wb,
        fmts: Dict,
        sheet_name: str,
        df: pd.DataFrame,
        title: str = "",
        start_row: int = 0,
        col_widths: Optional[List[int]] = None,
    ) -> None:
        ws = writer.sheets.get(sheet_name)
        if ws is None:
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row)
            ws = writer.sheets[sheet_name]
        else:
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row)

        # Title row
        if title and start_row > 0:
            ws.write(0, 0, title, fmts["title"])

        # Header row formatting
        header_row = start_row
        for col_idx, col_name in enumerate(df.columns):
            ws.write(header_row, col_idx, col_name, fmts["header"])

        # Column widths
        for col_idx, col_name in enumerate(df.columns):
            w = 18
            if col_widths and col_idx < len(col_widths):
                w = col_widths[col_idx]
            else:
                max_data = df[col_name].astype(str).str.len().max() if len(df) > 0 else 0
                w = max(len(str(col_name)), min(int(max_data), 40)) + 2
            ws.set_column(col_idx, col_idx, w)

        ws.freeze_panes(start_row + 1, 0)

    # ─────────────────────────────────────────
    # Sheet 1: Raw Data
    # ─────────────────────────────────────────

    def _sheet_raw_data(self, writer, wb, fmts):
        df = self.raw_df.copy()
        # Limit to 1M rows for Excel limits
        if len(df) > 1_000_000:
            df = df.head(1_000_000)
        # Add a Record ID column (matches the Record ID used in the Validation
        # Report) as the FIRST column so issues can be traced back to a row.
        # Validation runs on the concatenated cleaned frame (ignore_index=True),
        # so Record IDs are positional 0-based — use the same here.
        record_ids = [str(i) for i in range(len(df))]
        df.insert(0, "Record ID", record_ids)
        df.to_excel(writer, sheet_name="Raw Data", index=False)
        ws = writer.sheets["Raw Data"]
        for col_idx, col_name in enumerate(df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, 18)
        ws.set_column(0, 0, 12)  # Record ID column narrower
        ws.freeze_panes(1, 1)  # freeze header row + Record ID column

    # ─────────────────────────────────────────
    # Sheet 2: Cleaned Data
    # ─────────────────────────────────────────

    def _sheet_cleaned_data(self, writer, wb, fmts):
        df = self.cleaned_df.copy()
        if len(df) > 1_000_000:
            df = df.head(1_000_000)
        # Move flag_ columns to end
        flag_cols = [c for c in df.columns if c.startswith("flag_")]
        other_cols = [c for c in df.columns if not c.startswith("flag_")]
        df = df[other_cols + flag_cols]

        # Add Record ID as first column. The validation engine indexes the
        # cleaned frame by position (ignore_index=True), so use the df's own
        # index which is that same 0-based sequence.
        record_ids = [str(i) for i in df.index]
        df.insert(0, "Record ID", record_ids)

        df.to_excel(writer, sheet_name="Cleaned Data", index=False)
        ws = writer.sheets["Cleaned Data"]
        for col_idx, col_name in enumerate(df.columns):
            fmt = fmts["header"]
            ws.write(0, col_idx, col_name, fmt)
            ws.set_column(col_idx, col_idx, 18)
        ws.set_column(0, 0, 12)  # Record ID narrower
        ws.freeze_panes(1, 1)  # freeze header + Record ID column

    # ─────────────────────────────────────────
    # Sheet 3: Configuration Summary
    # ─────────────────────────────────────────

    def _sheet_config_summary(self, writer, wb, fmts):
        rows = [
            ["Project Name", self.project_name],
            ["Report Generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["Total Rows (Raw)", len(self.raw_df)],
            ["Total Rows (Cleaned)", len(self.cleaned_df)],
            ["Selected Columns", len(self.field_registry)],
            ["Cleaning Rules Configured", sum(len(v) for v in self.cleaning_rules.values())],
            ["Validation Rules Configured", len(self.validation_rules)],
            ["Address Groups", len(self.address_config.get("groups", []))],
            ["Test Detection Rules", len(self.test_detection_config)],
            ["", ""],
            ["=== Field Registry ===", ""],
        ]
        for col, meta in self.field_registry.items():
            rows.append([col, json.dumps(meta, default=str)])

        rows += [
            ["", ""],
            ["=== Cleaning Rules ===", ""],
        ]
        for col, rules in self.cleaning_rules.items():
            for r in rules:
                rows.append([col, json.dumps(r, default=str)])

        rows += [
            ["", ""],
            ["=== Validation Rules ===", ""],
        ]
        for rule in self.validation_rules:
            rows.append([rule.get("type", ""), json.dumps(rule, default=str)])

        df = pd.DataFrame(rows, columns=["Parameter", "Value"])
        df.to_excel(writer, sheet_name="Configuration Summary", index=False)
        ws = writer.sheets["Configuration Summary"]
        ws.write(0, 0, "Parameter", fmts["header"])
        ws.write(0, 1, "Value", fmts["header"])
        ws.set_column(0, 0, 35)
        ws.set_column(1, 1, 80)

    # ─────────────────────────────────────────
    # Sheet 4: Duplicate Report
    # ─────────────────────────────────────────

    def _sheet_duplicate_report(self, writer, wb, fmts):
        df = self.cleaned_df.copy()
        flag_cols = [c for c in df.columns if c.startswith("flag_duplicate")]
        dup_rows_list = []
        for fc in flag_cols:
            dups = df[df[fc] == 1].copy()
            if len(dups) > 0:
                # Preserve Record ID (row index) before any concat resets it
                dups.insert(0, "Record ID", [str(i) for i in dups.index])
                dups["_dup_flag_col"] = fc
                dup_rows_list.append(dups)

        if dup_rows_list:
            dup_df = pd.concat(dup_rows_list, ignore_index=True)
        else:
            dup_df = pd.DataFrame(columns=["Record ID"] + list(df.columns) + ["_dup_flag_col"])

        dup_df.to_excel(writer, sheet_name="Duplicate Report", index=False)
        ws = writer.sheets["Duplicate Report"]
        for col_idx, col_name in enumerate(dup_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, 18)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Sheet 5: Test Records Report
    # ─────────────────────────────────────────

    def _sheet_test_records(self, writer, wb, fmts):
        df = self.cleaned_df.copy()
        if "flag_test_record" in df.columns:
            test_df = df[df["flag_test_record"] == True].copy()
        else:
            test_df = pd.DataFrame(columns=df.columns)

        # Add Record ID (row index) as first column for traceability
        if len(test_df) > 0:
            test_df.insert(0, "Record ID", [str(i) for i in test_df.index])
        else:
            test_df = pd.DataFrame(columns=["Record ID"] + list(df.columns))

        test_df.to_excel(writer, sheet_name="Test Records Report", index=False)
        ws = writer.sheets["Test Records Report"]
        for col_idx, col_name in enumerate(test_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, 18)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Sheet 6: Validation Report
    # ─────────────────────────────────────────

    def _sheet_validation_report(self, writer, wb, fmts):
        if self.validation_issues:
            issues_df = pd.DataFrame(self.validation_issues)
            # Ensure all VALIDATION_REPORT_COLS present
            for col in VALIDATION_REPORT_COLS:
                if col not in issues_df.columns:
                    issues_df[col] = ""
            issues_df = issues_df[VALIDATION_REPORT_COLS]
        else:
            issues_df = pd.DataFrame(columns=VALIDATION_REPORT_COLS)

        issues_df.to_excel(writer, sheet_name="Validation Report", index=False)
        ws = writer.sheets["Validation Report"]
        widths = [12, 20, 22, 40, 20, 20, 10, 10, 20]
        for col_idx, col_name in enumerate(issues_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            w = widths[col_idx] if col_idx < len(widths) else 18
            ws.set_column(col_idx, col_idx, w)

        # Color severity cells
        sev_col_idx = VALIDATION_REPORT_COLS.index("Severity")
        for row_idx, issue in enumerate(self.validation_issues, start=1):
            sev = issue.get("Severity", "")
            fmt = fmts["severity"].get(sev, fmts["cell"])
            ws.write(row_idx, sev_col_idx, sev, fmt)

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(issues_df), len(VALIDATION_REPORT_COLS) - 1)

    # ─────────────────────────────────────────
    # Sheet 7: Data Quality Summary
    # ─────────────────────────────────────────

    def _sheet_data_quality_summary(self, writer, wb, fmts):
        df = self.cleaned_df.copy()
        prod_df = df[df.get("flag_test_record", pd.Series(False)) != True] if "flag_test_record" in df.columns else df

        issues_df = pd.DataFrame(self.validation_issues) if self.validation_issues else pd.DataFrame()

        summary_rows = []
        for col in [c for c in df.columns if not c.startswith("flag_")]:
            total = len(prod_df)
            null_count = prod_df[col].isna().sum() if col in prod_df.columns else 0
            null_pct = null_count / total if total > 0 else 0
            issue_count = 0
            if not issues_df.empty and "Field Name" in issues_df.columns:
                issue_count = int((issues_df["Field Name"] == col).sum())

            completeness = 1.0 - null_pct
            summary_rows.append({
                "Field": col,
                "Total Records": total,
                "Null Count": null_count,
                "Null %": f"{null_pct:.1%}",
                "Completeness %": f"{completeness:.1%}",
                "Validation Issues": issue_count,
            })

        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="Data Quality Summary", index=False)
        ws = writer.sheets["Data Quality Summary"]
        widths = [30, 15, 12, 10, 15, 18]
        for col_idx, col_name in enumerate(summary_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, widths[col_idx] if col_idx < len(widths) else 15)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Sheet 8: Reference Validation Detail
    # ─────────────────────────────────────────

    def _sheet_reference_validation(self, writer, wb, fmts):
        issues_df = pd.DataFrame(self.validation_issues) if self.validation_issues else pd.DataFrame(columns=VALIDATION_REPORT_COLS)
        if not issues_df.empty and "Issue Type" in issues_df.columns:
            ref_df = issues_df[issues_df["Issue Type"] == "REFERENCE_NOT_FOUND"].copy()
        else:
            ref_df = pd.DataFrame(columns=VALIDATION_REPORT_COLS)

        ref_df.to_excel(writer, sheet_name="Reference Validation Detail", index=False)
        ws = writer.sheets["Reference Validation Detail"]
        for col_idx, col_name in enumerate(ref_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, 22)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Sheet 9: Cross-field Consistency Report
    # ─────────────────────────────────────────

    def _sheet_cross_field(self, writer, wb, fmts):
        issues_df = pd.DataFrame(self.validation_issues) if self.validation_issues else pd.DataFrame(columns=VALIDATION_REPORT_COLS)
        cross_types = {"CROSS_FIELD_VIOLATION", "CARDINALITY_VIOLATION", "CUSTOM_RULE_VIOLATION"}
        if not issues_df.empty and "Issue Type" in issues_df.columns:
            cross_df = issues_df[issues_df["Issue Type"].isin(cross_types)].copy()
        else:
            cross_df = pd.DataFrame(columns=VALIDATION_REPORT_COLS)

        cross_df.to_excel(writer, sheet_name="Cross-field Consistency", index=False)
        ws = writer.sheets["Cross-field Consistency"]
        for col_idx, col_name in enumerate(cross_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, 22)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Dedicated sheets: mapping / cross-file cardinality
    # ─────────────────────────────────────────

    def _sheet_analysis_tables(self, writer, wb, fmts):
        """
        Write each rich analysis table (from mapping_cardinality and
        cross_file_cardinality) into its own dedicated sheet.
        Sheet names are the keys of self.analysis_tables.
        """
        if not self.analysis_tables:
            return

        for sheet_name, table_df in self.analysis_tables.items():
            if table_df is None:
                continue
            # Excel sheet names max 31 chars, no special chars
            safe_name = str(sheet_name)[:31]
            for ch in "[]:*?/\\":
                safe_name = safe_name.replace(ch, "-")

            if not isinstance(table_df, pd.DataFrame) or table_df.empty:
                empty = pd.DataFrame({"Note": [f"No data for {sheet_name}."]})
                empty.to_excel(writer, sheet_name=safe_name, index=False)
                ws = writer.sheets[safe_name]
                ws.write(0, 0, "Note", fmts["header"])
                ws.set_column(0, 0, 40)
                continue

            table_df.to_excel(writer, sheet_name=safe_name, index=False)
            ws = writer.sheets[safe_name]
            for col_idx, col_name in enumerate(table_df.columns):
                ws.write(0, col_idx, col_name, fmts["header"])
                # widen value-listing columns
                lname = str(col_name).lower()
                if "values" in lname or lname.endswith("s") or "detail" in lname:
                    ws.set_column(col_idx, col_idx, 45)
                else:
                    ws.set_column(col_idx, col_idx, 20)
            ws.freeze_panes(1, 0)

            # Highlight Flag column values with distinct colors
            if "Flag" in table_df.columns:
                flag_col_idx = list(table_df.columns).index("Flag")
                fmt_warn = wb.add_format({"bg_color": "#FCE4B8", "bold": True, "border": 1})   # orange
                fmt_bad = wb.add_format({"bg_color": "#F8CBAD", "bold": True, "border": 1})     # red-ish
                fmt_good = wb.add_format({"bg_color": "#C6EFCE", "bold": True, "border": 1})     # green
                for row_i, fval in enumerate(table_df["Flag"].tolist(), start=1):
                    fv = str(fval).strip()
                    if fv in ("REASSIGN", "CHECK", "VIOLATION"):
                        ws.write(row_i, flag_col_idx, fv, fmt_warn)
                    elif fv == "Invalid":
                        ws.write(row_i, flag_col_idx, fv, fmt_bad)
                    elif fv == "Valid":
                        ws.write(row_i, flag_col_idx, fv, fmt_good)

    # ─────────────────────────────────────────
    # Sheet 10: Address Validation Detail
    # ─────────────────────────────────────────

    def _sheet_address_validation(self, writer, wb, fmts):
        df = self.cleaned_df.copy()
        addr_cols = [c for c in df.columns if "_addr_" in c or c.endswith(("_lat", "_lng"))]

        if addr_cols:
            base_cols = [c for c in df.columns if c not in addr_cols and not c.startswith("flag_")]
            addr_df = df[base_cols[:5] + addr_cols].copy()
        else:
            addr_df = pd.DataFrame({"Note": ["No address validation configured or run."]})

        addr_df.to_excel(writer, sheet_name="Address Validation Detail", index=False)
        ws = writer.sheets["Address Validation Detail"]
        for col_idx, col_name in enumerate(addr_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, 22)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Sheet 11: Review Decisions Report
    # ─────────────────────────────────────────

    def _sheet_review_decisions(self, writer, wb, fmts):
        rows = []
        for key, decision in self.review_decisions.items():
            if isinstance(key, tuple) and len(key) == 3:
                record_id, field, rule = key
            else:
                record_id, field, rule = str(key), "", ""
            rows.append({
                "Record ID": record_id,
                "Field": field,
                "Rule": rule,
                "Decision": decision.get("action", "") if isinstance(decision, dict) else str(decision),
                "Edited Value": decision.get("edited_value", "") if isinstance(decision, dict) else "",
                "Reviewer Note": decision.get("note", "") if isinstance(decision, dict) else "",
                "Timestamp": decision.get("timestamp", "") if isinstance(decision, dict) else "",
            })

        review_df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["Record ID", "Field", "Rule", "Decision", "Edited Value", "Reviewer Note", "Timestamp"]
        )
        review_df.to_excel(writer, sheet_name="Review Decisions Report", index=False)
        ws = writer.sheets["Review Decisions Report"]
        widths = [15, 25, 30, 12, 25, 35, 22]
        for col_idx, col_name in enumerate(review_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, widths[col_idx] if col_idx < len(widths) else 18)
        ws.freeze_panes(1, 0)

    # ─────────────────────────────────────────
    # Sheet 12: Cleaning & Validation Log
    # ─────────────────────────────────────────

    def _sheet_cleaning_log(self, writer, wb, fmts):
        all_log = []
        for entry in self.cleaning_log:
            entry["log_type"] = "Cleaning"
            all_log.append(entry)
        for entry in self.run_log:
            e2 = dict(entry)
            e2["log_type"] = "Orchestrator"
            e2.setdefault("chunk", "")
            e2.setdefault("column", "")
            e2.setdefault("rule", "")
            e2.setdefault("status", e2.get("level", ""))
            e2.setdefault("detail", e2.get("message", ""))
            all_log.append(e2)

        if all_log:
            log_df = pd.DataFrame(all_log)
        else:
            log_df = pd.DataFrame(columns=["timestamp", "log_type", "chunk", "column", "rule", "status", "detail"])

        # Normalize columns
        for col in ["timestamp", "log_type", "chunk", "column", "rule", "status", "detail"]:
            if col not in log_df.columns:
                log_df[col] = ""

        log_df = log_df[["timestamp", "log_type", "chunk", "column", "rule", "status", "detail"]]
        log_df.to_excel(writer, sheet_name="Cleaning & Validation Log", index=False)
        ws = writer.sheets["Cleaning & Validation Log"]
        widths = [22, 14, 8, 25, 30, 10, 60]
        for col_idx, col_name in enumerate(log_df.columns):
            ws.write(0, col_idx, col_name, fmts["header"])
            ws.set_column(col_idx, col_idx, widths[col_idx] if col_idx < len(widths) else 20)
        ws.freeze_panes(1, 0)
