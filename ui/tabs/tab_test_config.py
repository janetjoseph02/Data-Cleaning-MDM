# ui/tabs/tab_test_config.py — Tab 4: Test Detection Configuration
from __future__ import annotations

from typing import Dict, List

import streamlit as st

from config import TEST_DETECTION_METHODS, TEST_DETECTION_LABELS, TEST_ENV_ROWS


def render(state: dict) -> None:
    """Render Tab 4: Test Detection Configuration."""
    st.header("🧪 Tab 4 — Test Detection Configuration")

    if not st.session_state.get("tab1_saved"):
        st.warning("🔒 Complete and save Tab 1 first.")
        return

    selected_columns: List[str] = st.session_state.get("selected_columns", [])
    col_options = ["(none)"] + selected_columns

    st.info(
        f"Test detection applies to the **first {TEST_ENV_ROWS:,} rows** only. "
        "Matched records are flagged `flag_test_record=True` and excluded from quality metrics."
    )

    existing_config: List[Dict] = st.session_state.get("test_detection_config", [])

    with st.form("form_test_detection"):
        n_rules = st.number_input(
            "Number of test detection rules",
            min_value=0, max_value=20,
            value=len(existing_config), step=1,
            key="n_test_rules",
        )

        new_config = []
        for r_idx in range(int(n_rules)):
            existing_r = existing_config[r_idx] if r_idx < len(existing_config) else {}
            with st.expander(f"Rule {r_idx+1} — {existing_r.get('method', 'new')}", expanded=r_idx == 0):
                method = st.selectbox(
                    "Detection Method",
                    TEST_DETECTION_METHODS,
                    format_func=lambda x: TEST_DETECTION_LABELS.get(x, x),
                    index=TEST_DETECTION_METHODS.index(existing_r.get("method", TEST_DETECTION_METHODS[0])),
                    key=f"tdmethod_{r_idx}",
                )
                rule_cfg = {"method": method}
                rule_cfg.update(_render_method_params(r_idx, method, existing_r, col_options))
                new_config.append(rule_cfg)

        save_btn = st.form_submit_button("💾 Save Test Detection Config", type="primary")

    if save_btn:
        st.session_state["test_detection_config"] = new_config
        st.session_state["tab4_saved"] = True
        st.success(f"✅ {len(new_config)} test detection rule(s) saved.")
        st.rerun()

    # Preview
    if st.session_state.get("raw_df") is not None and existing_config:
        st.divider()
        st.subheader("Preview — Test Record Detection")
        from core.test_detection import TestDetectionEngine
        raw_df = st.session_state["raw_df"]
        engine = TestDetectionEngine(existing_config)
        preview_df = engine.detect(raw_df.head(min(TEST_ENV_ROWS, len(raw_df))))
        summary = TestDetectionEngine.test_record_summary(preview_df)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Rows Scanned", f"{summary['total']:,}")
        c2.metric("🧪 Test Records", f"{summary['test']:,}")
        c3.metric("🏭 Production Records", f"{summary['production']:,}")

        if summary["test"] > 0:
            st.dataframe(
                preview_df[preview_df["flag_test_record"] == True].head(50),
                use_container_width=True,
            )


def _render_method_params(r_idx: int, method: str, existing: dict, col_options: List[str]) -> dict:
    k = str(r_idx)
    cfg = {}

    if method in ("field_value_match", "prefix_suffix_pattern", "regex_pattern", "value_in_list", "null_pk"):
        cfg["column"] = st.selectbox(
            "Column to Check", col_options,
            index=col_options.index(existing.get("column", col_options[0])) if existing.get("column") in col_options else 0,
            key=f"tdcol_{k}",
        )

    if method == "field_value_match":
        cfg["value"] = st.text_input("Match Value", value=existing.get("value", ""), key=f"tdval_{k}")
        cfg["case_sensitive"] = st.checkbox("Case Sensitive", value=existing.get("case_sensitive", False), key=f"tdcs_{k}")

    elif method == "prefix_suffix_pattern":
        c1, c2 = st.columns(2)
        cfg["prefix"] = c1.text_input("Prefix", value=existing.get("prefix", ""), key=f"tdpfx_{k}")
        cfg["suffix"] = c2.text_input("Suffix", value=existing.get("suffix", ""), key=f"tdsfx_{k}")
        cfg["case_sensitive"] = st.checkbox("Case Sensitive", value=existing.get("case_sensitive", False), key=f"tdpscs_{k}")

    elif method == "regex_pattern":
        cfg["pattern"] = st.text_input("Regex Pattern", value=existing.get("pattern", ""), key=f"tdrp_{k}")
        cfg["flags"] = st.text_input("Flags (e.g. i for IGNORECASE)", value=existing.get("flags", "i"), key=f"tdrpf_{k}")

    elif method == "value_in_list":
        raw = st.text_input(
            "Values (comma-separated)", value=", ".join(existing.get("values", [])),
            key=f"tdvil_{k}",
        )
        cfg["values"] = [v.strip() for v in raw.split(",") if v.strip()]
        cfg["case_sensitive"] = st.checkbox("Case Sensitive", value=existing.get("case_sensitive", False), key=f"tdvilcs_{k}")

    # null_pk needs only the column (already set above)
    return cfg
