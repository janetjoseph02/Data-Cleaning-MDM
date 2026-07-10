# ui/tabs/tab_run_controls.py — Tab 5: Run Controls
from __future__ import annotations

import datetime
import time
from typing import Dict, List

import streamlit as st

from config import BRAND_COLOR, CONFIDENCE_HIGH, CONFIDENCE_MEDIUM
from utils.session import (
    load_review_decisions,
    save_df_cache,
    append_run_log,
    detect_previously_processed_columns,
    restore_session_from_disk,
)


def render(state: dict) -> None:
    """Render Tab 5: Run Controls with live progress bar, ETA, abort, and staggered options."""
    st.header("▶️ Tab 5 — Run Controls")

    project_name = st.session_state.get("project_name")
    raw_df = st.session_state.get("raw_df")

    # Restore all saved config from disk after restart
    restore_session_from_disk(project_name)

    if not (st.session_state.get("tab2_saved") or st.session_state.get("tab3_saved")):
        st.warning("🔒 Save at least Tab 2 (Cleaning Rules) or Tab 3 (Validation Config) before running.")
        return

    if raw_df is None or project_name is None:
        st.error("No data loaded. Please upload a file on the landing page.")
        return

    from core.chunker import Chunker
    chunker = Chunker(len(raw_df))

    # ── Run summary
    st.subheader("Run Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Rows", f"{len(raw_df):,}")
    c2.metric("Tier", chunker.tier.capitalize())
    c3.metric("Chunks", f"{chunker.num_chunks:,}")
    c4.metric("Selected Columns", len(st.session_state.get("selected_columns", [])))

    col1, col2 = st.columns(2)
    col1.metric("Cleaning Rules", sum(len(v) for v in st.session_state.get("cleaning_rules", {}).values()))
    col2.metric("Validation Rules", len(st.session_state.get("validation_rules", [])))

    st.caption(
        f"Chunk size: **{chunker.chunk_size:,} rows** "
        f"({'in-memory' if chunker.tier == 'small' else 'chunked processing'}). "
        "Final chunk may be smaller."
    )

    st.divider()

    # ── FIX Issue 9: Staggered Run Options (inside a form to avoid page refresh)
    st.subheader("Staggered Run Options")
    st.caption(
        "Use staggered mode to add new columns to an already-cleaned dataset, "
        "or to re-clean only specific columns without starting from scratch."
    )

    all_columns: List[str] = st.session_state.get("selected_columns", [])
    prev_processed: List[str] = detect_previously_processed_columns(project_name)
    new_columns = [c for c in all_columns if c not in prev_processed]
    already_done = [c for c in all_columns if c in prev_processed]

    with st.form("form_staggered_options"):
        run_mode = st.radio(
            "Run Mode",
            options=["fresh_run", "add_new_columns", "reprocess_selected"],
            format_func=lambda x: {
                "fresh_run": "🔄 Fresh Run — reprocess all selected columns from raw data",
                "add_new_columns": f"➕ Add New Columns — process only new columns ({len(new_columns)} detected)",
                "reprocess_selected": "🔁 Reprocess Selected Columns — choose which columns to redo",
            }.get(x, x),
            key="_staggered_run_mode_widget",
            help=(
                "Fresh Run starts from raw data each time. "
                "Add New Columns uses the existing cleaned.pkl as a base and only processes new columns. "
                "Reprocess Selected lets you pick specific columns to re-run."
            ),
        )

        columns_to_run = all_columns  # default

        if run_mode == "add_new_columns":
            if new_columns:
                st.success(f"✅ {len(new_columns)} new column(s) will be processed: {', '.join(new_columns)}")
                if already_done:
                    st.info(f"ℹ️ {len(already_done)} previously processed column(s) will be preserved as-is.")
                columns_to_run = new_columns
            else:
                st.warning("No new columns detected. All selected columns have been processed before. Use 'Reprocess Selected' to redo them.")
                columns_to_run = []

        elif run_mode == "reprocess_selected":
            if not already_done:
                st.info("No previously processed columns found. Run a fresh run first.")
                columns_to_run = all_columns
            else:
                columns_to_run = st.multiselect(
                    "Select columns to reprocess",
                    options=all_columns,
                    default=already_done,
                    key="staggered_reprocess_cols",
                    help="Only the selected columns will be re-cleaned. Others keep their existing cleaned values.",
                )

        # Summary table
        if all_columns:
            import pandas as pd
            summary_data = []
            for c in all_columns:
                from utils.session import load_field_registry
                reg = load_field_registry(project_name)
                last_proc = reg.get(c, {}).get("last_processed")
                will_run = c in columns_to_run
                summary_data.append({
                    "Column": c,
                    "Last Processed": last_proc or "Never",
                    "Will Run This Session": "✅ Yes" if will_run else "⏭️ Skip",
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

        apply_staggered = st.form_submit_button("✅ Apply Run Options", type="secondary")

    if apply_staggered:
        st.session_state["_staggered_run_mode"] = run_mode
        st.session_state["staggered_columns_to_run"] = columns_to_run
        st.success(f"Run options saved: mode='{run_mode}', columns={len(columns_to_run)}")

    st.divider()

    # ── Abort / Run buttons
    if st.session_state.get("run_in_progress"):
        if st.button("🛑 Abort Run", type="secondary", key="abort_btn"):
            st.session_state["run_abort"] = True
            st.warning("Abort requested — will stop after the current chunk completes.")

    if not st.session_state.get("run_in_progress"):
        col_run, col_clear = st.columns([3, 1])
        with col_run:
            run_clicked = st.button("▶️ Start Run", type="primary", use_container_width=True)
        with col_clear:
            if st.button("🗑️ Clear Cache", use_container_width=True):
                _clear_cache(project_name)
                st.success("Cache cleared.")
    else:
        run_clicked = False

    if run_clicked:
        # FIX Issue 9 / Bug E: pass staggered options to the orchestrator
        effective_columns = st.session_state.get("staggered_columns_to_run", all_columns)
        effective_mode = st.session_state.get("_staggered_run_mode", "fresh_run")
        _execute_run(project_name, raw_df, chunker, effective_columns, effective_mode)


def _execute_run(
    project_name: str,
    raw_df,
    chunker,
    columns_to_run: list,
    run_mode: str,
) -> None:
    """Execute the full orchestrator pipeline with live progress UI."""
    from core.orchestrator import Orchestrator

    st.session_state["run_in_progress"] = True
    st.session_state["run_abort"] = False
    st.session_state["run_complete"] = False

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    eta_text = st.empty()
    log_container = st.expander("📋 Live Log", expanded=False)
    log_placeholder = log_container.empty()

    start_time = time.time()

    def progress_callback(value: float, label: str) -> None:
        if value is not None:
            progress_bar.progress(min(float(value), 1.0))
        if label:
            status_text.markdown(f"**{label}**")
        elapsed = time.time() - start_time
        if value and value > 0.01:
            total_est = elapsed / value
            remaining = max(total_est - elapsed, 0)
            eta_text.caption(
                f"⏱ Elapsed: {_fmt_dur(elapsed)}  |  "
                f"ETA: {_fmt_dur(remaining)}  |  "
                f"{value*100:.1f}% complete"
            )

    def abort_flag() -> bool:
        return bool(st.session_state.get("run_abort", False))

    # FIX Bug E: filter cleaning rules to only the columns being run this session
    all_cleaning_rules: dict = st.session_state.get("cleaning_rules", {})
    if run_mode in ("add_new_columns", "reprocess_selected"):
        effective_cleaning_rules = {
            col: rules for col, rules in all_cleaning_rules.items()
            if col in columns_to_run
        }
    else:
        effective_cleaning_rules = all_cleaning_rules

    # FIX Issue 9: pass run_mode so orchestrator can decide whether to use staggered base
    orchestrator = Orchestrator(
        project_name=project_name,
        raw_df=raw_df,
        selected_columns=columns_to_run,
        cleaning_rules=effective_cleaning_rules,
        validation_rules=st.session_state.get("validation_rules", []),
        test_detection_config=st.session_state.get("test_detection_config", []),
        address_config=st.session_state.get("address_config", {"groups": []}),
        reference_files=st.session_state.get("reference_files", {}),
        field_registry=st.session_state.get("field_registry", {}),
        progress_callback=progress_callback,
        abort_flag_fn=abort_flag,
        run_mode=run_mode,                  # FIX Issue 9: pass mode
        all_selected_columns=st.session_state.get("selected_columns", []),  # for staggered merge
    )

    # FIX Issue J: pre-flight check for missing reference files
    missing_refs = _preflight_reference_check(
        st.session_state.get("cleaning_rules", {}),
        st.session_state.get("validation_rules", []),
        st.session_state.get("reference_files", {}),
    )
    if missing_refs:
        st.warning(
            f"⚠️ Pre-flight warning: the following reference files are referenced in rules "
            f"but not loaded: **{', '.join(missing_refs)}**. "
            "Rules using these files will be silently skipped."
        )

    result = orchestrator.run()

    if result.get("cleaned_df") is not None:
        st.session_state["cleaned_df"] = result["cleaned_df"]
    st.session_state["validation_results"] = result.get("validation_issues", [])
    st.session_state["analysis_tables"] = result.get("analysis_tables", {})
    st.session_state["run_log"] = result.get("run_log", [])

    existing_decisions = load_review_decisions(project_name)
    st.session_state["review_decisions"] = existing_decisions

    st.session_state["run_in_progress"] = False
    st.session_state["run_complete"] = True

    if result.get("success"):
        progress_bar.progress(1.0)
        status_text.markdown("✅ **Run complete!**")
        elapsed = time.time() - start_time
        eta_text.caption(f"⏱ Total time: {_fmt_dur(elapsed)}")

        test_summary = result.get("test_summary", {})
        c1, c2, c3 = st.columns(3)
        c1.metric("Rows Processed", f"{len(result['cleaned_df']):,}")
        c2.metric("🧪 Test Records", f"{test_summary.get('test', 0):,}")
        c3.metric("⚠️ Issues Found", f"{len(result.get('validation_issues', [])):,}")

        log_lines = [
            f"[{e.get('level','INFO')}] {e.get('timestamp','')} — {e.get('message','')}"
            for e in result.get("run_log", [])
        ]
        log_placeholder.code("\n".join(log_lines[-50:]), language=None)
        st.success("✅ Run complete. Navigate to Tab 6+ to review results.")

    elif result.get("error") == "Aborted":
        status_text.markdown("🛑 **Run aborted by user.**")
        st.warning("Run was aborted. Partial results may be available.")
    else:
        status_text.markdown(f"❌ **Run failed:** {result.get('error')}")
        st.error(f"Error: {result.get('error')}")


def _preflight_reference_check(
    cleaning_rules: dict, validation_rules: list, loaded_refs: dict
) -> list:
    """FIX Issue J: return list of referenced-but-not-loaded reference file names."""
    referenced = set()
    for col_rules in cleaning_rules.values():
        for rule in col_rules:
            for key in ("reference_file", "ref_name"):
                v = rule.get(key)
                if v and v != "(none)":
                    referenced.add(v)
    for rule in validation_rules:
        v = rule.get("reference_file")
        if v and v != "(none)":
            referenced.add(v)
    return sorted(r for r in referenced if r not in loaded_refs)


def _clear_cache(project_name: str) -> None:
    from utils.session import get_cache_path
    cache_dir = get_cache_path(project_name)
    for f in cache_dir.glob("*.pkl"):
        try:
            f.unlink()
        except Exception:
            pass
    for f in cache_dir.glob("*.json"):
        try:
            f.unlink()
        except Exception:
            pass
    st.session_state["cleaned_df"] = None
    st.session_state["validation_results"] = []
    st.session_state["run_complete"] = False
    st.session_state["cache_loaded"] = False
    st.session_state["_staggered_run_mode"] = "fresh_run"
    st.session_state["staggered_columns_to_run"] = []


def _fmt_dur(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    elif s < 3600:
        m, sec = divmod(s, 60)
        return f"{m}m {sec}s"
    else:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}h {m}m {sec}s"
