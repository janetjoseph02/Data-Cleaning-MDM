# ui/cleaning_studio.py — Cleaning Studio: 10-Tab Router
from __future__ import annotations

import streamlit as st

from config import BRAND_COLOR

# Import all tab renderers
from ui.tabs import (
    tab_field_config,
    tab_cleaning_rules,
    tab_validation_config,
    tab_test_config,
    tab_run_controls,
    tab_statistics,
    tab_data_preview,
    tab_val_report,
    tab_review,
    tab_report,
)


def render() -> None:
    """Render the 10-tab Cleaning Studio."""

    # Gate check
    if st.session_state.get("raw_df") is None:
        st.warning("⬅️ Upload a file on the **Home** page first.")
        return

    project_name = st.session_state.get("project_name", "—")
    tier = st.session_state.get("tier", "—")
    total_rows = st.session_state.get("total_rows", 0)

    st.markdown(
        f"<div style='background:{BRAND_COLOR};color:white;padding:8px 16px;border-radius:6px;margin-bottom:8px'>"
        f"🔬 <b>{project_name}</b> &nbsp;|&nbsp; {total_rows:,} rows &nbsp;|&nbsp; Tier: {tier.capitalize()}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Tab definitions
    # Tabs 2–10 locked until Tab 1 saved; tabs 5–10 locked until tab 2 or 3 saved
    tab1_saved = st.session_state.get("tab1_saved", False)
    tab2_or_3_saved = st.session_state.get("tab2_saved", False) or st.session_state.get("tab3_saved", False)

    def _label(base: str, locked: bool) -> str:
        return f"{'🔒 ' if locked else ''}{base}"

    tab_labels = [
        "⚙️ Field Config",
        _label("🧹 Cleaning Rules", not tab1_saved),
        _label("✅ Validation", not tab1_saved),
        _label("🧪 Test Config", not tab1_saved),
        _label("▶️ Run", not tab1_saved),
        _label("📊 Statistics", not tab2_or_3_saved),
        _label("🔍 Data Preview", not tab2_or_3_saved),
        _label("📋 Val Report", not tab2_or_3_saved),
        _label("🔎 Review", not tab2_or_3_saved),
        _label("📥 Report", not tab2_or_3_saved),
    ]

    tabs = st.tabs(tab_labels)
    state = dict(st.session_state)

    with tabs[0]:
        tab_field_config.render(state)

    with tabs[1]:
        tab_cleaning_rules.render(state)

    with tabs[2]:
        tab_validation_config.render(state)

    with tabs[3]:
        tab_test_config.render(state)

    with tabs[4]:
        tab_run_controls.render(state)

    with tabs[5]:
        tab_statistics.render(state)

    with tabs[6]:
        tab_data_preview.render(state)

    with tabs[7]:
        tab_val_report.render(state)

    with tabs[8]:
        tab_review.render(state)

    with tabs[9]:
        tab_report.render(state)
