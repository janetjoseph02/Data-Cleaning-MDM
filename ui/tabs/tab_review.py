# ui/tabs/tab_review.py — Tab 9: Review Decisions
from __future__ import annotations

import datetime
from typing import Dict, List

import pandas as pd
import streamlit as st

# FIX Bug H: all imports at top of file, not inside loops
from config import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_COLOR_HIGH,
    CONFIDENCE_COLOR_MEDIUM,
    CONFIDENCE_COLOR_LOW,
    SEVERITY_LEVELS,
    ISSUE_TYPES,
    REPORT_SEVERITY_COLORS,   # FIX Bug H: was imported inside loop
)
from utils.session import save_review_decisions, load_review_decisions


def render(state: dict) -> None:
    """Render Tab 9: Review Decisions."""
    st.header("🔎 Tab 9 — Review Decisions (Optional)")

    if not st.session_state.get("run_complete"):
        st.info("Run the pipeline (Tab 5) first.")
        return

    project_name = st.session_state.get("project_name")
    validation_results: List[Dict] = st.session_state.get("validation_results", [])
    cleaned_df: pd.DataFrame = st.session_state.get("cleaned_df")

    if not validation_results:
        st.success("✅ No validation issues to review.")
        return

    issues_df = pd.DataFrame(validation_results)

    decisions: Dict = load_review_decisions(project_name)
    if not decisions:
        decisions = st.session_state.get("review_decisions", {})

    st.caption(
        f"Review **{len(issues_df):,}** validation issues. "
        "Decisions are persisted to cache immediately on save."
    )

    # ── Bulk actions
    st.subheader("Bulk Actions")
    b1, b2, b3, b4 = st.columns(4)

    with b1:
        if st.button("✅ Accept All", key="bulk_accept_all"):
            decisions = _bulk_action(issues_df, decisions, "accept")
            _persist(project_name, decisions)
            st.success("All issues accepted.")
            st.rerun()

    with b2:
        if st.button("❌ Reject All", key="bulk_reject_all"):
            decisions = _bulk_action(issues_df, decisions, "reject")
            _persist(project_name, decisions)
            st.success("All issues rejected.")
            st.rerun()

    with b3:
        bulk_sev = st.selectbox(
            "Severity", ["(select)"] + SEVERITY_LEVELS,
            key="bulk_sev_sel", label_visibility="collapsed"
        )
        if st.button("Accept by Severity", key="bulk_accept_sev") and bulk_sev != "(select)":
            sev_issues = issues_df[issues_df["Severity"] == bulk_sev]
            decisions = _bulk_action(sev_issues, decisions, "accept")
            _persist(project_name, decisions)
            st.success(f"Accepted all {bulk_sev} issues.")
            st.rerun()

    with b4:
        bulk_threshold = st.slider("Min Confidence %", 0, 100, 80, key="bulk_conf_thresh")
        if st.button("Accept by Confidence", key="bulk_accept_conf"):
            if cleaned_df is not None:
                addr_conf_cols = [
                    c for c in cleaned_df.columns if c.endswith("_addr_confidence")
                ]
            else:
                addr_conf_cols = []

            if addr_conf_cols:
                # FIX Issue 10f: actually filter by threshold — build set of record IDs
                # whose address confidence meets the threshold
                qualifying_ids = set()
                for acc in addr_conf_cols:
                    qualifying = cleaned_df[cleaned_df[acc] >= bulk_threshold]
                    qualifying_ids.update(qualifying.index.astype(str))

                addr_issues = issues_df[
                    (issues_df["Issue Type"] == "ADDRESS_VALIDATION_FAIL") &
                    (issues_df["Record ID"].isin(qualifying_ids))
                ]
                if len(addr_issues) > 0:
                    decisions = _bulk_action(addr_issues, decisions, "accept")
                    _persist(project_name, decisions)
                    st.success(
                        f"Accepted {len(addr_issues)} address issue(s) "
                        f"where confidence >= {bulk_threshold}%."
                    )
                else:
                    st.info(f"No address issues found with confidence >= {bulk_threshold}%.")
            else:
                st.info("No address confidence columns found in cleaned data.")
            st.rerun()

    st.divider()

    # ── Filters
    st.subheader("Issue Filters")
    f1, f2, f3 = st.columns(3)
    with f1:
        sev_f = st.multiselect("Severity", SEVERITY_LEVELS, default=SEVERITY_LEVELS, key="rev_sev")
    with f2:
        type_f = st.multiselect("Issue Type", ISSUE_TYPES, default=ISSUE_TYPES, key="rev_type")
    with f3:
        status_f = st.selectbox(
            "Decision Status",
            ["All", "Undecided", "Accepted", "Rejected", "Edited"],
            key="rev_status",
        )

    filtered = issues_df.copy()
    if sev_f:
        filtered = filtered[filtered["Severity"].isin(sev_f)]
    if type_f:
        filtered = filtered[filtered["Issue Type"].isin(type_f)]

    def _get_decision(row):
        key = _make_key(row)
        d = decisions.get(key)
        if d is None:
            return "Undecided"
        return d.get("action", "Undecided").capitalize()

    filtered["Decision"] = filtered.apply(_get_decision, axis=1)

    if status_f != "All":
        filtered = filtered[filtered["Decision"] == status_f]

    st.caption(f"Showing {len(filtered):,} issues | Decided: {sum(1 for k in decisions):,}")

    # ── Per-record review
    st.subheader("Per-Issue Review")
    PAGE_SIZE = 50
    total_pages = max(1, (len(filtered) - 1) // PAGE_SIZE + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key="rev_page")
    start_i = (page - 1) * PAGE_SIZE
    page_df = filtered.iloc[start_i : start_i + PAGE_SIZE].copy()

    changed = False
    for _, row in page_df.iterrows():
        key = _make_key(row)
        existing_decision = decisions.get(key, {})

        # FIX Bug H: REPORT_SEVERITY_COLORS already imported at top
        sev_color = REPORT_SEVERITY_COLORS.get(row.get("Severity", ""), "#888")

        with st.expander(
            f"{row.get('Severity','')} | {row.get('Issue Type','')} | "
            f"Record {row.get('Record ID','')} — {row.get('Field Name','')}",
            expanded=False,
        ):
            st.markdown(
                f"<span style='border-left:4px solid {sev_color};padding-left:8px'>"
                f"**Rule:** {row.get('Rule Description','')}<br>"
                f"**Expected:** `{row.get('Expected','')}` | **Actual:** `{row.get('Actual','')}`"
                f"</span>",
                unsafe_allow_html=True,
            )

            col_a, col_b, col_c = st.columns(3)
            accept = col_a.button("✅ Accept", key=f"acc_{key}")
            reject = col_b.button("❌ Reject", key=f"rej_{key}")

            edit_val = col_c.text_input(
                "Edit Value",
                value=existing_decision.get("edited_value", ""),
                key=f"edit_{key}",
                label_visibility="collapsed",
            )
            edit_save = col_c.button("💾 Save Edit", key=f"esave_{key}")

            note = st.text_input(
                "Note", value=existing_decision.get("note", ""),
                key=f"note_{key}",
            )

            ts_now = datetime.datetime.now().isoformat()
            if accept:
                decisions[key] = {"action": "accept", "note": note, "timestamp": ts_now}
                changed = True
            elif reject:
                decisions[key] = {"action": "reject", "note": note, "timestamp": ts_now}
                changed = True
            elif edit_save and edit_val:
                decisions[key] = {
                    "action": "edited", "edited_value": edit_val,
                    "note": note, "timestamp": ts_now,
                }
                changed = True

    if changed:
        _persist(project_name, decisions)
        st.success("✅ Decisions saved.")
        st.rerun()

    # ── Decision summary
    st.divider()
    st.subheader("Decision Summary")
    summary = {"Accepted": 0, "Rejected": 0, "Edited": 0, "Undecided": 0}
    for _, row in issues_df.iterrows():
        k = _make_key(row)
        d = decisions.get(k)
        if d is None:
            summary["Undecided"] += 1
        else:
            action = d.get("action", "undecided").capitalize()
            summary[action] = summary.get(action, 0) + 1

    cols = st.columns(4)
    for i, (k, v) in enumerate(summary.items()):
        cols[i].metric(k, f"{v:,}")


def _make_key(row) -> tuple:
    return (
        str(row.get("Record ID", "")),
        str(row.get("Field Name", "")),
        str(row.get("Rule Description", "")),
    )


def _bulk_action(issues_df: pd.DataFrame, decisions: Dict, action: str) -> Dict:
    ts = datetime.datetime.now().isoformat()
    for _, row in issues_df.iterrows():
        key = _make_key(row)
        decisions[key] = {"action": action, "timestamp": ts}
    return decisions


def _persist(project_name: str, decisions: Dict) -> None:
    st.session_state["review_decisions"] = decisions
    save_review_decisions(project_name, decisions)
