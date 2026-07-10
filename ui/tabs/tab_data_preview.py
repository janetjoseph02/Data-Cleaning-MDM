# ui/tabs/tab_data_preview.py — Tab 7: Data Preview
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import MAX_PREVIEW_ROWS


def render(state: dict) -> None:
    """Render Tab 7: Data Preview."""
    st.header("🔍 Tab 7 — Data Preview")

    if not st.session_state.get("run_complete"):
        st.info("Run the pipeline (Tab 5) first to preview data.")
        return

    raw_df: pd.DataFrame = st.session_state.get("raw_df")
    cleaned_df: pd.DataFrame = st.session_state.get("cleaned_df")

    if cleaned_df is None:
        st.warning("No cleaned data available.")
        return

    # ── Controls row
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 2, 2, 2])

    with ctrl1:
        view_mode = st.radio(
            "View Mode",
            ["Original", "Cleaned", "Side-by-Side"],
            index=1,
            key="preview_mode",
            horizontal=True,
        )

    with ctrl2:
        n_rows = st.number_input(
            "Rows to display",
            min_value=10, max_value=MAX_PREVIEW_ROWS,
            value=100, step=10,
            key="preview_n_rows",
        )

    with ctrl3:
        show_flags = st.checkbox("Show flag_ columns", value=True, key="preview_flags")

    with ctrl4:
        search_val = st.text_input("🔎 Filter rows (any column contains)", value="", key="preview_search")

    st.divider()

    # ── Column filter
    all_cols = list(cleaned_df.columns)
    non_flag_cols = [c for c in all_cols if not c.startswith("flag_")]
    flag_cols = [c for c in all_cols if c.startswith("flag_")]

    display_cols = non_flag_cols + (flag_cols if show_flags else [])

    selected_cols = st.multiselect(
        "Columns to display (leave empty for all)",
        options=display_cols,
        default=[],
        key="preview_col_filter",
    )
    if not selected_cols:
        selected_cols = display_cols

    # ── Apply search filter
    def _filter_df(df: pd.DataFrame, search: str) -> pd.DataFrame:
        if not search:
            return df
        mask = df.astype(str).apply(
            lambda col: col.str.contains(search, case=False, na=False)
        ).any(axis=1)
        return df[mask]

    # ── Render based on view mode
    if view_mode == "Original":
        if raw_df is None:
            st.warning("Original data not available.")
        else:
            display_df = _filter_df(raw_df[[c for c in selected_cols if c in raw_df.columns]], search_val)
            st.caption(f"Showing {min(n_rows, len(display_df)):,} of {len(display_df):,} rows (original)")
            st.dataframe(display_df.head(n_rows), use_container_width=True, hide_index=False)

    elif view_mode == "Cleaned":
        display_df = _filter_df(cleaned_df[[c for c in selected_cols if c in cleaned_df.columns]], search_val)
        st.caption(f"Showing {min(n_rows, len(display_df)):,} of {len(display_df):,} rows (cleaned)")
        _render_cleaned_df(display_df.head(n_rows))

    elif view_mode == "Side-by-Side":
        if raw_df is None:
            st.warning("Original data not available for side-by-side comparison.")
        else:
            common_cols = [c for c in selected_cols if c in raw_df.columns and c in cleaned_df.columns]
            if not common_cols:
                common_cols = non_flag_cols[:5]

            raw_filt = _filter_df(raw_df[[c for c in common_cols if c in raw_df.columns]], search_val).head(n_rows)
            clean_filt = cleaned_df[[c for c in common_cols if c in cleaned_df.columns]].iloc[raw_filt.index]

            left, right = st.columns(2)
            with left:
                st.markdown("**📄 Original**")
                st.dataframe(raw_filt, use_container_width=True, hide_index=False)
            with right:
                st.markdown("**✨ Cleaned**")
                st.dataframe(clean_filt, use_container_width=True, hide_index=False)

    # ── Change summary
    if view_mode != "Original" and raw_df is not None:
        st.divider()
        st.subheader("Change Summary")
        selected_for_summary = st.session_state.get("selected_columns", non_flag_cols[:10])
        changed_counts = []
        for col in selected_for_summary:
            if col not in raw_df.columns or col not in cleaned_df.columns:
                continue
            raw_s = raw_df[col].astype(str).fillna("").head(len(cleaned_df))
            clean_s = cleaned_df[col].astype(str).fillna("")
            changed = int((raw_s.values != clean_s.values).sum())
            if changed > 0:
                changed_counts.append({"Field": col, "Cells Changed": changed})

        if changed_counts:
            ch_df = pd.DataFrame(changed_counts).sort_values("Cells Changed", ascending=False)
            st.dataframe(ch_df, use_container_width=True, hide_index=True)
        else:
            st.success("No changes detected between original and cleaned data.")


def _render_cleaned_df(df: pd.DataFrame) -> None:
    """Render cleaned dataframe with flag column highlighting."""
    flag_cols = [c for c in df.columns if c.startswith("flag_")]

    if not flag_cols:
        st.dataframe(df, use_container_width=True, hide_index=False)
        return

    # Style: highlight rows where any flag == 1
    def highlight_flags(row):
        has_flag = any(
            row.get(fc, 0) == 1
            for fc in flag_cols
            if fc in row.index
        )
        return ["background-color: #FFF3CD" if has_flag else "" for _ in row]

    try:
        styled = df.style.apply(highlight_flags, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=False)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=False)
