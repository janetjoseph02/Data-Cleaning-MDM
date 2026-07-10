# ui/tabs/tab_report.py — Tab 10: Report Generation & Download
from __future__ import annotations

import datetime
from pathlib import Path
from typing import List

import streamlit as st

from config import BRAND_COLOR, REPORT_SHEETS
from utils.session import get_prod_path


def render(state: dict) -> None:
    """Render Tab 10: Report Generation."""
    st.header("📥 Tab 10 — Report")

    if not st.session_state.get("run_complete"):
        st.info("Run the pipeline (Tab 5) first.")
        return

    project_name = st.session_state.get("project_name")
    raw_df = st.session_state.get("raw_df")
    cleaned_df = st.session_state.get("cleaned_df")

    if cleaned_df is None:
        st.error("No cleaned data available.")
        return

    # ── Sheet selection
    st.subheader("Report Configuration")
    st.caption(f"The report will contain up to {len(REPORT_SHEETS)} sheets.")

    with st.form("form_report_config"):
        selected_sheets = st.multiselect(
            "Sheets to include",
            REPORT_SHEETS,
            default=REPORT_SHEETS,
            key="report_sheets",
        )
        report_name = st.text_input(
            "Report filename (without extension)",
            value=f"{project_name}_mdm_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            key="report_name",
        )
        include_raw = st.checkbox("Include Raw Data sheet", value=True, key="rpt_raw")
        max_rows_per_sheet = st.number_input(
            "Max rows per data sheet (Excel limit: 1,048,576)",
            min_value=1000, max_value=1_048_576,
            value=1_000_000, step=10000,
            key="rpt_max_rows",
        )
        generate_btn = st.form_submit_button("🚀 Generate Report", type="primary")

    if generate_btn:
        _generate_report(
            project_name=project_name,
            report_name=report_name,
            selected_sheets=selected_sheets,
            include_raw=include_raw,
        )

    # ── Report history
    st.divider()
    st.subheader("📁 Report History")
    prod_path = get_prod_path(project_name)
    report_files = sorted(prod_path.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not report_files:
        st.info("No reports generated yet for this project.")
    else:
        for rf in report_files[:20]:
            size_kb = rf.stat().st_size / 1024
            mtime = datetime.datetime.fromtimestamp(rf.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            col1, col2, col3 = st.columns([4, 2, 2])
            col1.markdown(f"📊 **{rf.name}**")
            col2.caption(f"{size_kb:.1f} KB | {mtime}")
            with open(rf, "rb") as f:
                col3.download_button(
                    "⬇️ Download",
                    data=f.read(),
                    file_name=rf.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_hist_{rf.name}",
                )


def _generate_report(
    project_name: str,
    report_name: str,
    selected_sheets: List[str],
    include_raw: bool,
) -> None:
    from reports.generator import ReportGenerator

    with st.spinner("Generating report…"):
        try:
            raw_df = st.session_state.get("raw_df")
            cleaned_df = st.session_state.get("cleaned_df")
            validation_issues = st.session_state.get("validation_results", [])
            analysis_tables = st.session_state.get("analysis_tables", {})
            cleaning_log = []  # populated from orchestrator run_log entries
            run_log = st.session_state.get("run_log", [])
            field_registry = st.session_state.get("field_registry", {})
            cleaning_rules = st.session_state.get("cleaning_rules", {})
            validation_rules = st.session_state.get("validation_rules", [])
            address_config = st.session_state.get("address_config", {"groups": []})
            test_detection_config = st.session_state.get("test_detection_config", [])
            review_decisions = st.session_state.get("review_decisions", {})

            # Extract cleaning log from run_log
            cleaning_log = [
                e for e in run_log
                if e.get("level") in ("INFO", "ERROR") and "chunk" in str(e.get("message", "")).lower()
            ]

            generator = ReportGenerator(
                raw_df=raw_df if include_raw else cleaned_df.iloc[0:0],
                cleaned_df=cleaned_df,
                validation_issues=validation_issues,
                cleaning_log=cleaning_log,
                field_registry=field_registry,
                cleaning_rules=cleaning_rules,
                validation_rules=validation_rules,
                address_config=address_config,
                test_detection_config=test_detection_config,
                review_decisions=review_decisions,
                project_name=project_name,
                run_log=run_log,
                analysis_tables=analysis_tables,
            )

            prod_path = get_prod_path(project_name)
            output_path = prod_path / f"{report_name}.xlsx"
            report_bytes = generator.generate(output_path=str(output_path))

            # Track in history
            history: List[str] = st.session_state.get("report_history", [])
            history.insert(0, str(output_path))
            st.session_state["report_history"] = history[:50]

            st.success(f"✅ Report generated: `{output_path.name}` ({len(report_bytes)/1024:.1f} KB)")

            st.download_button(
                "⬇️ Download Report Now",
                data=report_bytes,
                file_name=f"{report_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_report_now",
            )

            # Sheet summary
            st.subheader("Report Sheets Generated")
            for sheet in REPORT_SHEETS:
                included = sheet in selected_sheets or (sheet == "Raw Data" and include_raw)
                icon = "✅" if included else "⬜"
                st.caption(f"{icon} {sheet}")

        except Exception as e:
            st.error(f"Report generation failed: {e}")
            import traceback
            st.code(traceback.format_exc())
