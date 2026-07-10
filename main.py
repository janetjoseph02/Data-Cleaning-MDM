# main.py — DataCraft MDM Quality Workbench Entry Point
from __future__ import annotations

import streamlit as st

from config import APP_ICON, APP_TITLE, BRAND_COLOR
from utils.session import init_session
from ui.landing import render as render_landing
from ui.cleaning_studio import render as render_studio


def main() -> None:
    # ── Page config (must be first Streamlit call)
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Custom CSS
    st.markdown(
        f"""
        <style>
        :root {{
            --brand: {BRAND_COLOR};
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px;
        }}
        .stTabs [data-baseweb="tab"] {{
            padding: 6px 14px;
            font-size: 0.85rem;
        }}
        .stMetric {{
            background: #F8F9FA;
            border-radius: 8px;
            padding: 10px;
        }}
        div[data-testid="stExpander"] {{
            border: 1px solid #E0E0E0;
            border-radius: 6px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Initialize all session state keys
    init_session()

    # ── Sidebar navigation
    with st.sidebar:
        st.markdown(
            f"<h3 style='color:{BRAND_COLOR}'>{APP_ICON} DataCraft MDM</h3>",
            unsafe_allow_html=True,
        )
        st.divider()

        page = st.radio(
            "Navigation",
            ["🏠 Home", "🔬 Cleaning Studio"],
            key="nav_page",
        )

        st.divider()

        # Project info
        proj = st.session_state.get("project_name")
        if proj:
            st.caption(f"**Project:** {proj}")
        tier = st.session_state.get("tier")
        if tier:
            st.caption(f"**Tier:** {tier.capitalize()}")
        rows = st.session_state.get("total_rows", 0)
        if rows:
            st.caption(f"**Rows:** {rows:,}")

        run_done = st.session_state.get("run_complete", False)
        if run_done:
            n_issues = len(st.session_state.get("validation_results", []))
            st.caption(f"**Last run:** ✅ {n_issues:,} issues")

        st.divider()

        # Quick status indicators
        status_items = [
            ("Tab 1 Saved", st.session_state.get("tab1_saved", False)),
            ("Tab 2 Saved", st.session_state.get("tab2_saved", False)),
            ("Tab 3 Saved", st.session_state.get("tab3_saved", False)),
            ("Tab 4 Saved", st.session_state.get("tab4_saved", False)),
            ("Run Complete", st.session_state.get("run_complete", False)),
        ]
        for label, done in status_items:
            icon = "✅" if done else "⬜"
            st.caption(f"{icon} {label}")

        st.divider()
        st.caption("v1.0.0 | DataCraft MDM")

    # ── Page routing
    if page == "🏠 Home":
        render_landing()
    else:
        render_studio()


if __name__ == "__main__":
    main()
