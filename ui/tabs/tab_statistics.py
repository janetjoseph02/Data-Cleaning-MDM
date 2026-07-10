# ui/tabs/tab_statistics.py — Tab 6: Statistics Dashboard
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import (
    BRAND_COLOR,
    REPORT_SEVERITY_COLORS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_COLOR_HIGH,
    CONFIDENCE_COLOR_MEDIUM,
    CONFIDENCE_COLOR_LOW,
)


def render(state: dict) -> None:
    """Render Tab 6: Statistics."""
    st.header("📊 Tab 6 — Statistics")

    if not st.session_state.get("run_complete"):
        st.info("Run the pipeline (Tab 5) first to see statistics.")
        return

    cleaned_df: pd.DataFrame = st.session_state.get("cleaned_df")
    raw_df: pd.DataFrame = st.session_state.get("raw_df")
    validation_results = st.session_state.get("validation_results", [])

    if cleaned_df is None:
        st.warning("No cleaned data available.")
        return

    # ── Top-level metrics
    st.subheader("Overview")

    # Exclude test records from all quality metrics (fix)
    if "flag_test_record" in cleaned_df.columns:
        prod_df = cleaned_df[cleaned_df["flag_test_record"] != True].copy()
        test_count = int(cleaned_df["flag_test_record"].sum())
    else:
        prod_df = cleaned_df.copy()
        test_count = 0

    total_prod = len(prod_df)
    total_raw = len(raw_df) if raw_df is not None else 0
    issues_df = pd.DataFrame(validation_results) if validation_results else pd.DataFrame()
    total_issues = len(issues_df)
    fields = [c for c in cleaned_df.columns if not c.startswith("flag_")]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Raw Rows", f"{total_raw:,}")
    c2.metric("Production Rows", f"{total_prod:,}")
    c3.metric("🧪 Test Records", f"{test_count:,}")
    c4.metric("Total Issues", f"{total_issues:,}")
    c5.metric("Fields", f"{len(fields):,}")

    # ── Overall data quality score
    if total_prod > 0 and fields:
        total_cells = total_prod * len(fields)
        null_cells = sum(
            prod_df[c].isna().sum()
            for c in fields if c in prod_df.columns
        )
        completeness = 1.0 - (null_cells / total_cells)
        issue_rate = min(total_issues / (total_prod * max(len(fields), 1)), 1.0)
        quality_score = max(0.0, completeness * (1 - issue_rate)) * 100

        st.divider()
        score_color = (
            CONFIDENCE_COLOR_HIGH if quality_score >= CONFIDENCE_HIGH else
            CONFIDENCE_COLOR_MEDIUM if quality_score >= CONFIDENCE_MEDIUM else
            CONFIDENCE_COLOR_LOW
        )
        st.markdown(
            f"<h2 style='color:{score_color}'>Overall Data Quality Score: {quality_score:.1f}%</h2>",
            unsafe_allow_html=True,
        )
        st.progress(quality_score / 100)

    # ── Per-field null / completeness table
    st.divider()
    st.subheader("Per-Field Completeness")

    field_stats = []
    for col in fields:
        if col not in prod_df.columns:
            continue
        total = len(prod_df)
        null_count = int(prod_df[col].isna().sum())
        null_pct = null_count / total if total > 0 else 0
        unique_count = prod_df[col].nunique()
        field_issues = int((issues_df["Field Name"] == col).sum()) if not issues_df.empty and "Field Name" in issues_df.columns else 0
        field_stats.append({
            "Field": col,
            "Total": total,
            "Nulls": null_count,
            "Null %": f"{null_pct:.1%}",
            "Completeness %": f"{1-null_pct:.1%}",
            "Unique Values": unique_count,
            "Issues": field_issues,
        })

    if field_stats:
        stats_df = pd.DataFrame(field_stats)
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

    # ── Issues by severity
    if not issues_df.empty and "Severity" in issues_df.columns:
        st.divider()
        st.subheader("Issues by Severity")
        sev_counts = issues_df["Severity"].value_counts().reset_index()
        sev_counts.columns = ["Severity", "Count"]

        cols = st.columns(len(sev_counts))
        for i, row in sev_counts.iterrows():
            color = REPORT_SEVERITY_COLORS.get(row["Severity"], "#888")
            cols[i % len(cols)].markdown(
                f"<div style='padding:10px;border-left:5px solid {color};margin:4px'>"
                f"<b style='color:{color}'>{row['Severity']}</b><br>"
                f"<span style='font-size:1.5em'>{row['Count']:,}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Issues by issue type
    if not issues_df.empty and "Issue Type" in issues_df.columns:
        st.divider()
        st.subheader("Issues by Type")
        type_counts = issues_df["Issue Type"].value_counts().reset_index()
        type_counts.columns = ["Issue Type", "Count"]
        st.dataframe(type_counts, use_container_width=True, hide_index=True)

    # ── Issues by field
    if not issues_df.empty and "Field Name" in issues_df.columns:
        st.divider()
        st.subheader("Top Fields by Issue Count")
        field_counts = issues_df["Field Name"].value_counts().head(20).reset_index()
        field_counts.columns = ["Field", "Issues"]
        st.dataframe(field_counts, use_container_width=True, hide_index=True)

    # ── Address validation summary
    addr_cols = [c for c in cleaned_df.columns if c.endswith("_addr_match_status")]
    if addr_cols:
        st.divider()
        st.subheader("Address Validation Summary")
        for ac in addr_cols:
            prefix = ac.replace("_addr_match_status", "")
            st.markdown(f"**Group: {prefix}**")
            status_counts = cleaned_df[ac].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            conf_col = f"{prefix}_addr_confidence"
            if conf_col in cleaned_df.columns:
                avg_conf = cleaned_df[conf_col].mean()
                st.metric(f"{prefix} avg confidence", f"{avg_conf:.1f}%")
            st.dataframe(status_counts, use_container_width=True, hide_index=True)

    # ── Duplicate summary
    dup_cols = [c for c in cleaned_df.columns if c.startswith("flag_duplicate")]
    if dup_cols:
        st.divider()
        st.subheader("Duplicate Summary")
        for dc in dup_cols:
            dup_count = int(cleaned_df[dc].sum())
            st.metric(f"Duplicates ({dc})", f"{dup_count:,}")

    # ── Run log summary
    run_log = st.session_state.get("run_log", [])
    if run_log:
        st.divider()
        st.subheader("Run Log Summary")
        errors = [e for e in run_log if e.get("level") == "ERROR"]
        st.caption(f"Total log entries: {len(run_log)} | Errors: {len(errors)}")
        if errors:
            for e in errors:
                st.error(f"{e.get('timestamp','')}: {e.get('message','')}")
