# ui/landing.py — Landing Page: Project Management & File Upload
from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    APP_ICON,
    APP_TITLE,
    BRAND_COLOR,
    TIER_SMALL_MAX,
    TIER_MEDIUM_MAX,
)
from core.chunker import Chunker, read_uploaded_file, sniff_row_count
from utils.session import (
    get_project_path,
    list_projects,
    load_project_meta,
    save_df_cache,
    save_project_meta,
    detect_previously_processed_columns,
    get_staggered_base_df,
)


def render() -> bool:
    """
    Render landing page.
    Returns True if a project is active with data loaded (ready to proceed to workbench).
    """
    st.markdown(
        f"<h1 style='color:{BRAND_COLOR}'>{APP_ICON} {APP_TITLE}</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Master Data Management · Data Quality Workbench")
    st.divider()

    col_left, col_right = st.columns([1, 2])

    # ── Left: Project Management
    with col_left:
        st.subheader("📁 Project")

        existing_projects = list_projects()

        mode = st.radio(
            "Action",
            ["Create New Project", "Open Existing Project"],
            key="landing_mode",
            horizontal=True,
        )

        if mode == "Create New Project":
            with st.form("form_new_project"):
                proj_name = st.text_input(
                    "Project Name",
                    placeholder="e.g. customer_master_2024",
                    key="new_proj_name",
                )
                proj_desc = st.text_area(
                    "Description (optional)",
                    height=80,
                    key="new_proj_desc",
                )
                create_btn = st.form_submit_button("➕ Create Project", type="primary")

            if create_btn:
                if not proj_name.strip():
                    st.error("Project name cannot be empty.")
                elif proj_name in existing_projects:
                    st.error(f"Project '{proj_name}' already exists. Open it instead.")
                else:
                    get_project_path(proj_name)
                    save_project_meta(proj_name, {
                        "name": proj_name,
                        "description": proj_desc,
                        "created": datetime.datetime.now().isoformat(),
                    })
                    st.session_state["project_name"] = proj_name
                    st.session_state["project_path"] = str(get_project_path(proj_name))
                    st.success(f"✅ Project '{proj_name}' created.")
                    st.rerun()

        else:  # Open existing
            if not existing_projects:
                st.info("No projects found. Create one first.")
            else:
                with st.form("form_open_project"):
                    selected_proj = st.selectbox(
                        "Select Project",
                        existing_projects,
                        key="open_proj_sel",
                    )
                    open_btn = st.form_submit_button("📂 Open Project", type="primary")

                if open_btn:
                    st.session_state["project_name"] = selected_proj
                    st.session_state["project_path"] = str(get_project_path(selected_proj))

                    # Load project meta
                    meta = load_project_meta(selected_proj)
                    if meta:
                        st.success(f"✅ Opened '{selected_proj}'")
                        if meta.get("description"):
                            st.caption(meta["description"])

                    # Staggered session: detect existing cache
                    cached_df = get_staggered_base_df(selected_proj)
                    if cached_df is not None:
                        st.session_state["cleaned_df"] = cached_df
                        st.session_state["cache_loaded"] = True
                        prev = detect_previously_processed_columns(selected_proj)
                        st.session_state["previously_processed_columns"] = prev
                        st.info(
                            f"🔁 Existing session detected: {len(cached_df):,} rows, "
                            f"{len(prev)} previously processed column(s)."
                        )

                    st.rerun()

        # Active project display
        active = st.session_state.get("project_name")
        if active:
            st.success(f"✅ Active project: **{active}**")
            meta = load_project_meta(active)
            if meta:
                st.caption(f"Created: {meta.get('created','')[:10]}")

    # ── Right: File Upload
    with col_right:
        st.subheader("📤 Upload Data File")

        active_project = st.session_state.get("project_name")
        if not active_project:
            st.info("Create or open a project first.")
            return False

        uploaded = st.file_uploader(
            "Upload CSV, Excel, Parquet, JSON, or TSV",
            type=["csv", "xlsx", "xls", "parquet", "json", "tsv"],
            key="file_uploader",
        )

        # Reference file upload
        st.subheader("📎 Upload Reference Files (optional)")
        ref_upload = st.file_uploader(
            "Upload reference/lookup files (CSV or Excel)",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key="ref_uploader",
        )

        if ref_upload:
            from utils.session import save_reference_file
            for ref_file in ref_upload:
                try:
                    ref_df = read_uploaded_file(ref_file)
                    ref_name = Path(ref_file.name).stem
                    save_reference_file(active_project, ref_name, ref_df)
                    ref_files = st.session_state.get("reference_files", {})
                    ref_files[ref_name] = ref_df
                    st.session_state["reference_files"] = ref_files
                    st.success(f"✅ Reference file '{ref_name}' uploaded ({len(ref_df):,} rows).")
                except Exception as e:
                    st.error(f"Failed to load reference file '{ref_file.name}': {e}")

        if uploaded is not None:
            # Check if same file already loaded
            if st.session_state.get("uploaded_file_name") == uploaded.name and st.session_state.get("raw_df") is not None:
                st.info(f"File '{uploaded.name}' already loaded.")
            else:
                with st.spinner("Reading file…"):
                    try:
                        row_count = sniff_row_count(uploaded)
                        chunker = Chunker(row_count)

                        st.info(
                            f"📊 Detected **{row_count:,} rows** → "
                            f"**{chunker.tier.capitalize()} tier** "
                            f"({chunker.tier_label})"
                        )

                        # Read full file into memory (raw_df always full for Small/Medium)
                        uploaded.seek(0)
                        raw_df = read_uploaded_file(uploaded)

                        # Cache raw
                        save_df_cache(active_project, "raw.pkl", raw_df)

                        st.session_state.update({
                            "raw_df": raw_df,
                            "uploaded_file_name": uploaded.name,
                            "total_rows": len(raw_df),
                            "total_cols": len(raw_df.columns),
                            "tier": chunker.tier,
                            "chunk_size": chunker.chunk_size,
                        })

                        save_project_meta(active_project, {
                            "name": active_project,
                            "file": uploaded.name,
                            "rows": len(raw_df),
                            "cols": len(raw_df.columns),
                            "tier": chunker.tier,
                            "uploaded": datetime.datetime.now().isoformat(),
                        })

                        st.success(
                            f"✅ Loaded **{uploaded.name}** — "
                            f"{len(raw_df):,} rows × {len(raw_df.columns):,} columns"
                        )

                    except Exception as e:
                        st.error(f"Failed to read file: {e}")
                        return False

        # Show file summary if loaded
        raw_df = st.session_state.get("raw_df")
        if raw_df is not None:
            st.divider()
            st.subheader("File Summary")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rows", f"{len(raw_df):,}")
            c2.metric("Columns", f"{len(raw_df.columns):,}")
            c3.metric("Tier", st.session_state.get("tier", "—").capitalize())
            c4.metric("File", st.session_state.get("uploaded_file_name", "—"))

            with st.expander("Column Overview", expanded=False):
                col_info = pd.DataFrame({
                    "Column": raw_df.columns,
                    "Dtype": [str(raw_df[c].dtype) for c in raw_df.columns],
                    "Non-Null": [raw_df[c].notna().sum() for c in raw_df.columns],
                    "Null %": [f"{raw_df[c].isna().mean():.1%}" for c in raw_df.columns],
                    "Unique": [raw_df[c].nunique() for c in raw_df.columns],
                    "Sample": [str(raw_df[c].dropna().iloc[0]) if raw_df[c].notna().any() else "" for c in raw_df.columns],
                })
                st.dataframe(col_info, use_container_width=True, hide_index=True)

            st.caption("✅ File loaded. Proceed to the **Cleaning Studio** tabs above.")
            return True

    return st.session_state.get("raw_df") is not None
