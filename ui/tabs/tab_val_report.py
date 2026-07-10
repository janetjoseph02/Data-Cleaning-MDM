# ui/tabs/tab_val_report.py — Tab 8: Validation Report
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import (
    ISSUE_TYPES,
    SEVERITY_LEVELS,
    REPORT_SEVERITY_COLORS,
    SEVERITY_EMOJI,
    VALIDATION_REPORT_COLS,
)


def render(state: dict) -> None:
    """Render Tab 8: Validation Report."""
    st.header("📋 Tab 8 — Validation Report")

    if not st.session_state.get("run_complete"):
        st.info("Run the pipeline (Tab 5) first.")
        return

    validation_results = st.session_state.get("validation_results", [])

    if not validation_results:
        st.success("✅ No validation issues found!")
        return

    issues_df = pd.DataFrame(validation_results)
    for col in VALIDATION_REPORT_COLS:
        if col not in issues_df.columns:
            issues_df[col] = ""
    issues_df = issues_df[VALIDATION_REPORT_COLS]

    total_issues = len(issues_df)
    st.caption(f"Total issues: **{total_issues:,}**")

    # ── Summary metrics by severity
    st.subheader("Summary by Severity")
    sev_cols = st.columns(len(SEVERITY_LEVELS))
    for i, sev in enumerate(SEVERITY_LEVELS):
        count = int((issues_df["Severity"] == sev).sum())
        color = REPORT_SEVERITY_COLORS.get(sev, "#888")
        emoji = SEVERITY_EMOJI.get(sev, "")
        sev_cols[i].markdown(
            f"<div style='text-align:center;padding:8px;border-top:4px solid {color}'>"
            f"<b>{emoji} {sev}</b><br><span style='font-size:1.8em;color:{color}'>{count:,}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Filters
    st.subheader("Filters")
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        sev_filter = st.multiselect(
            "Severity",
            SEVERITY_LEVELS,
            default=SEVERITY_LEVELS,
            key="val_sev_filter",
        )

    with f2:
        issue_type_filter = st.multiselect(
            "Issue Type",
            ISSUE_TYPES,
            default=ISSUE_TYPES,
            key="val_type_filter",
        )

    with f3:
        available_fields = ["(all)"] + sorted(issues_df["Field Name"].dropna().unique().tolist())
        field_filter = st.selectbox("Field", available_fields, key="val_field_filter")

    with f4:
        chunk_vals = sorted(issues_df["Chunk Number"].dropna().unique().tolist())
        chunk_options = ["(all)"] + [str(c) for c in chunk_vals]
        chunk_filter = st.selectbox("Chunk", chunk_options, key="val_chunk_filter")

    search_text = st.text_input("🔎 Search (Rule Description / Actual)", value="", key="val_search")

    # ── Apply filters
    filtered = issues_df.copy()
    if sev_filter:
        filtered = filtered[filtered["Severity"].isin(sev_filter)]
    if issue_type_filter:
        filtered = filtered[filtered["Issue Type"].isin(issue_type_filter)]
    if field_filter != "(all)":
        filtered = filtered[filtered["Field Name"] == field_filter]
    if chunk_filter != "(all)":
        filtered = filtered[filtered["Chunk Number"].astype(str) == chunk_filter]
    if search_text:
        mask = (
            filtered["Rule Description"].astype(str).str.contains(search_text, case=False, na=False) |
            filtered["Actual"].astype(str).str.contains(search_text, case=False, na=False)
        )
        filtered = filtered[mask]

    st.caption(f"Showing **{len(filtered):,}** of {total_issues:,} issues after filters")

    # ── Paginated table
    PAGE_SIZE = 500
    total_pages = max(1, (len(filtered) - 1) // PAGE_SIZE + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key="val_page")
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_df = filtered.iloc[start:end].copy()

    # Color severity column
    def _color_sev(val):
        color = REPORT_SEVERITY_COLORS.get(val, "#000")
        return f"color: {color}; font-weight: bold"

    try:
        styled = page_df.style.applymap(_color_sev, subset=["Severity"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(page_df, use_container_width=True, hide_index=True)

    # ── Download filtered
    st.divider()
    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Filtered Issues (CSV)",
        data=csv_bytes,
        file_name="validation_issues_filtered.csv",
        mime="text/csv",
        key="dl_val_csv",
    )
