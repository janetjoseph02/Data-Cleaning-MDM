# ui/tabs/tab_cleaning_rules.py — Tab 2: Cleaning Rules Configuration
from __future__ import annotations

from typing import Dict, List

import streamlit as st

from config import (
    ALL_CLEANING_RULES,
    CLEANING_RULE_LABELS,
    FUZZY_DEFAULT_THRESHOLD,
    PATTERNS,
    PATTERN_LABELS,
)
from utils.session import list_reference_files, save_cleaning_rules, restore_session_from_disk


def render(state: dict) -> None:
    """Render Tab 2: Cleaning Rules."""
    st.header("🧹 Tab 2 — Cleaning Rules")

    if not st.session_state.get("tab1_saved"):
        st.warning("🔒 Complete and save Tab 1 (Field Configuration) first.")
        return

    project_name = st.session_state.get("project_name", "")
    restore_session_from_disk(project_name)
    selected_columns: List[str] = st.session_state.get("selected_columns", [])
    ref_files = list_reference_files(project_name)
    ref_options = ["(none)"] + ref_files

    if not selected_columns:
        st.info("No columns selected. Go to Tab 1.")
        return

    existing_rules: Dict = st.session_state.get("cleaning_rules", {})
    new_rules: Dict = {}

    st.caption("Configure one or more cleaning rules per column. Rules are applied in order.")

    # FIX Bug B: use a single form wrapping everything so n_rules changes
    # don't cause stray reruns and partial widget loss
    with st.form("form_save_cleaning_rules"):
        for col in selected_columns:
            col_rules = existing_rules.get(col, [])

            with st.expander(f"🔧 **{col}**", expanded=False):
                # n_rules INSIDE the form — safe here because the whole column
                # is wrapped together; submit button controls the rerun
                n_rules = st.number_input(
                    f"Number of rules for `{col}`",
                    min_value=0, max_value=10,
                    value=len(col_rules),
                    step=1,
                    key=f"nrules_{col}",
                )

                col_new_rules = []
                for r_idx in range(int(n_rules)):
                    existing_r = col_rules[r_idx] if r_idx < len(col_rules) else {}
                    st.markdown(f"**Rule {r_idx+1}**")
                    with st.container():
                        rule_name = st.selectbox(
                            "Rule",
                            ALL_CLEANING_RULES,
                            format_func=lambda x: CLEANING_RULE_LABELS.get(x, x),
                            index=ALL_CLEANING_RULES.index(existing_r.get("rule", ALL_CLEANING_RULES[0])),
                            key=f"rule_{col}_{r_idx}",
                        )
                        rule_cfg = {"rule": rule_name}
                        rule_cfg.update(
                            _render_rule_params(col, r_idx, rule_name, existing_r, ref_options, selected_columns)
                        )
                        col_new_rules.append(rule_cfg)
                    st.divider()

                new_rules[col] = col_new_rules

        st.write("Click Save to persist all cleaning rules.")
        save_btn = st.form_submit_button("💾 Save Cleaning Rules", type="primary")

    if save_btn:
        st.session_state["cleaning_rules"] = new_rules
        st.session_state["tab2_saved"] = True
        save_cleaning_rules(project_name, new_rules)
        st.success("✅ Cleaning rules saved.")
        st.rerun()


# ─────────────────────────────────────────────
# Per-rule parameter rendering
# ─────────────────────────────────────────────

def _render_rule_params(
    col: str, r_idx: int, rule_name: str, existing: dict,
    ref_options: List[str], all_cols: List[str],
) -> dict:
    k = f"{col}_{r_idx}"
    cfg = {}

    if rule_name == "case_normalize":
        cfg["mode"] = st.selectbox(
            "Case Mode", ["upper", "lower", "title", "sentence"],
            index=["upper", "lower", "title", "sentence"].index(existing.get("mode", "upper")),
            key=f"case_{k}",
        )

    elif rule_name == "null_handling":
        action = st.selectbox(
            "Action", ["fill", "flag"],
            index=["fill", "flag"].index(existing.get("action", "flag")),
            key=f"null_action_{k}",
        )
        cfg["action"] = action
        if action == "fill":
            cfg["fill_value"] = st.text_input(
                "Fill Value", value=existing.get("fill_value", ""),
                key=f"fill_val_{k}",
            )

    elif rule_name in ("pattern_replace", "custom_regex_replace"):
        cfg["pattern"] = st.text_input(
            "Regex Pattern", value=existing.get("pattern", ""), key=f"pat_{k}",
        )
        cfg["replacement"] = st.text_input(
            "Replacement", value=existing.get("replacement", ""), key=f"rep_{k}",
        )
        if rule_name == "custom_regex_replace":
            cfg["flags"] = st.text_input(
                "Flags (e.g. IGNORECASE)", value=existing.get("flags", ""), key=f"flags_{k}",
            )

    elif rule_name == "remove_special_chars":
        cfg["keep_spaces"] = st.checkbox(
            "Keep Spaces", value=existing.get("keep_spaces", True), key=f"ks_{k}"
        )
        cfg["extra_keep"] = st.text_input(
            "Extra chars to keep", value=existing.get("extra_keep", ""), key=f"ek_{k}"
        )

    elif rule_name == "prefix_remap":
        raw_map = existing.get("mapping", {})
        map_str = "\n".join(f"{k}={v}" for k, v in raw_map.items())
        map_input = st.text_area(
            "Prefix Mapping (old=new, one per line)", value=map_str, height=80, key=f"pmap_{k}"
        )
        mapping = {}
        for line in map_input.strip().splitlines():
            if "=" in line:
                parts = line.split("=", 1)
                mapping[parts[0].strip()] = parts[1].strip()
        cfg["mapping"] = mapping

    elif rule_name == "pad_leading_zeros":
        cfg["width"] = st.number_input(
            "Target Width", min_value=1, max_value=20,
            value=existing.get("width", 6), step=1, key=f"padw_{k}",
        )

    elif rule_name == "fuzzy_match":
        cfg["threshold"] = st.slider(
            "Match Threshold", 0, 100,
            value=existing.get("threshold", FUZZY_DEFAULT_THRESHOLD),
            key=f"fth_{k}",
        )
        cfg["reference_file"] = st.selectbox(
            "Reference File", ref_options,
            index=ref_options.index(existing.get("reference_file", "(none)")) if existing.get("reference_file") in ref_options else 0,
            key=f"fref_{k}",
        )
        # FIX Issue 2: dropdown for reference column
        ref_cols = _get_ref_columns(cfg["reference_file"])
        ref_col_opts = ["(none)"] + ref_cols
        cfg["reference_column"] = st.selectbox(
            "Reference Column",
            ref_col_opts,
            index=ref_col_opts.index(existing.get("reference_column", "(none)")) if existing.get("reference_column") in ref_col_opts else 0,
            key=f"fcol_{k}",
            help="Column in the reference file containing canonical values to match against.",
        )
        cfg["first_char_block"] = st.checkbox(
            "First-char blocking", value=existing.get("first_char_block", True), key=f"fcb_{k}",
        )

    elif rule_name == "reference_lookup_replace":
        cfg["reference_file"] = st.selectbox(
            "Reference File", ref_options,
            index=ref_options.index(existing.get("reference_file", "(none)")) if existing.get("reference_file") in ref_options else 0,
            key=f"rlr_ref_{k}",
        )
        # FIX Issue 2: dropdowns for key and value columns
        ref_cols = _get_ref_columns(cfg["reference_file"])
        ref_col_opts = ["(none)"] + ref_cols
        cfg["key_column"] = st.selectbox(
            "Key Column in Reference (lookup key)",
            ref_col_opts,
            index=ref_col_opts.index(existing.get("key_column", "(none)")) if existing.get("key_column") in ref_col_opts else 0,
            key=f"rlr_key_{k}",
            help="Column whose values match the data column values.",
        )
        cfg["value_column"] = st.selectbox(
            "Value Column in Reference (replacement value)",
            ref_col_opts,
            index=ref_col_opts.index(existing.get("value_column", "(none)")) if existing.get("value_column") in ref_col_opts else 0,
            key=f"rlr_val_{k}",
            help="Column whose value replaces the matched data value.",
        )
        cfg["unmatched_action"] = st.selectbox(
            "Unmatched Action", ["keep", "blank", "flag"],
            index=["keep", "blank", "flag"].index(existing.get("unmatched_action", "keep")),
            key=f"rlr_um_{k}",
        )

    elif rule_name == "date_standardize":
        cfg["output_format"] = st.text_input(
            "Output Format (strftime)", value=existing.get("output_format", "%Y-%m-%d"),
            key=f"datefmt_{k}",
        )

    elif rule_name == "phone_standardize":
        cfg["output_format"] = st.selectbox(
            "Output Format", ["e164", "national", "local"],
            index=["e164", "national", "local"].index(existing.get("output_format", "e164")),
            key=f"phonefmt_{k}",
        )
        cfg["country_code"] = st.text_input(
            "Country Code", value=existing.get("country_code", "+91"), key=f"cc_{k}",
        )

    elif rule_name == "boolean_norm":
        cfg["true_output"] = st.text_input(
            "True Output", value=existing.get("true_output", "True"), key=f"bt_{k}"
        )
        cfg["false_output"] = st.text_input(
            "False Output", value=existing.get("false_output", "False"), key=f"bf_{k}"
        )

    elif rule_name == "currency_norm":
        cfg["strip_symbols"] = st.checkbox(
            "Strip Currency Symbols", value=existing.get("strip_symbols", True), key=f"cs_{k}"
        )
        cfg["strip_commas"] = st.checkbox(
            "Strip Commas", value=existing.get("strip_commas", True), key=f"cc2_{k}"
        )
        cfg["decimal_places"] = st.number_input(
            "Decimal Places", min_value=0, max_value=6,
            value=existing.get("decimal_places", 2), step=1, key=f"dp_{k}",
        )
        cfg["target_symbol"] = st.text_input(
            "Target Symbol (optional)", value=existing.get("target_symbol", ""), key=f"ts_{k}"
        )

    elif rule_name == "extract_substring":
        method = st.selectbox(
            "Method", ["regex", "position"],
            index=["regex", "position"].index(existing.get("method", "regex")),
            key=f"esm_{k}",
        )
        cfg["method"] = method
        cfg["new_column"] = st.text_input(
            "New Column Name", value=existing.get("new_column", f"{col}_extracted"),
            key=f"esncol_{k}",
        )
        if method == "regex":
            cfg["pattern"] = st.text_input(
                "Pattern", value=existing.get("pattern", ""), key=f"espan_{k}"
            )
        else:
            c1, c2 = st.columns(2)
            cfg["start"] = c1.number_input("Start", value=existing.get("start", 0), key=f"esst_{k}")
            cfg["end"] = c2.number_input("End (-1=end)", value=existing.get("end", -1), key=f"esen_{k}")

    elif rule_name == "concatenate_fields":
        sel_fields = st.multiselect(
            "Fields to Concatenate", all_cols,
            default=existing.get("fields", [col]),
            key=f"catf_{k}",
        )
        cfg["fields"] = sel_fields
        cfg["separator"] = st.text_input(
            "Separator", value=existing.get("separator", " "), key=f"cats_{k}"
        )
        cfg["new_column"] = st.text_input(
            "New Column", value=existing.get("new_column", "concat_field"), key=f"catn_{k}"
        )
        cfg["skip_null"] = st.checkbox(
            "Skip Null Fields", value=existing.get("skip_null", True), key=f"catsn_{k}"
        )

    elif rule_name == "split_field":
        cfg["delimiter"] = st.text_input(
            "Delimiter", value=existing.get("delimiter", ","), key=f"spd_{k}"
        )
        cfg["new_col_prefix"] = st.text_input(
            "New Column Prefix", value=existing.get("new_col_prefix", f"{col}_part"),
            key=f"spp_{k}",
        )

    elif rule_name == "deduplicate_multivalue":
        cfg["delimiter"] = st.text_input(
            "Delimiter", value=existing.get("delimiter", ","), key=f"dmvd_{k}"
        )
        cfg["case_insensitive"] = st.checkbox(
            "Case Insensitive", value=existing.get("case_insensitive", True), key=f"dmvci_{k}"
        )
        cfg["sort"] = st.checkbox(
            "Sort Values", value=existing.get("sort", False), key=f"dmvs_{k}"
        )

    elif rule_name == "flag_duplicate_records":
        subset = st.multiselect(
            "Subset Columns", all_cols,
            default=existing.get("subset", [col]),
            key=f"fdr_{k}",
        )
        cfg["subset"] = subset
        cfg["keep"] = st.selectbox(
            "Keep", ["first", "last", "none"],
            index=["first", "last", "none"].index(existing.get("keep", "first")),
            key=f"fdrkp_{k}",
        )
        cfg["flag_column"] = st.text_input(
            "Flag Column Name", value=existing.get("flag_column", "flag_duplicate_record"),
            key=f"fdrflag_{k}",
        )

    elif rule_name == "custom_python_expression":
        cfg["expression"] = st.text_area(
            "Python Expression (use `value` for cell, `row` for row dict)",
            value=existing.get("expression", "value.strip().upper()"),
            height=80, key=f"cpe_{k}",
        )
        cfg["new_column"] = st.text_input(
            "Output Column (blank = same column)", value=existing.get("new_column", col),
            key=f"cpen_{k}",
        )
        if cfg.get("expression"):
            st.caption("ℹ️ Expression runs sandboxed. Preview will appear during run (5-row gate).")

    elif rule_name == "custom_lookup_transform":
        cfg["ref_name"] = st.selectbox(
            "Reference File", ref_options,
            index=ref_options.index(existing.get("ref_name", "(none)")) if existing.get("ref_name") in ref_options else 0,
            key=f"clt_ref_{k}",
        )
        # FIX Issue 2: dropdowns for key and value columns in custom_lookup_transform
        ref_cols = _get_ref_columns(cfg["ref_name"])
        ref_col_opts = ["(none)"] + ref_cols
        if ref_cols:
            cfg["ref_key_fields"] = st.multiselect(
                "Reference Key Columns",
                ref_cols,
                default=[c for c in existing.get("ref_key_fields", []) if c in ref_cols],
                key=f"clt_rk_{k}",
                help="Columns in the reference file used as the lookup key (can be multi-column).",
            )
            cfg["ref_value_field"] = st.selectbox(
                "Reference Value Column",
                ref_col_opts,
                index=ref_col_opts.index(existing.get("ref_value_field", "(none)")) if existing.get("ref_value_field") in ref_col_opts else 0,
                key=f"clt_rv_{k}",
            )
        else:
            # Fallback text inputs when reference isn't loaded yet
            raw_keys = st.text_input(
                "Reference Key Columns (comma-sep)",
                value=",".join(existing.get("ref_key_fields", [])),
                key=f"clt_rk_{k}",
            )
            cfg["ref_key_fields"] = [c.strip() for c in raw_keys.split(",") if c.strip()]
            cfg["ref_value_field"] = st.text_input(
                "Reference Value Column", value=existing.get("ref_value_field", ""),
                key=f"clt_rv_{k}",
            )
        cfg["output_column"] = st.text_input(
            "Output Column", value=existing.get("output_column", col), key=f"clt_oc_{k}",
        )
        cfg["unmatched_action"] = st.selectbox(
            "Unmatched Action", ["keep", "blank", "flag"],
            index=["keep", "blank", "flag"].index(existing.get("unmatched_action", "keep")),
            key=f"clt_ua_{k}",
        )

    return cfg


# ─────────────────────────────────────────────
# Helper: load reference file columns from session
# ─────────────────────────────────────────────

def _get_ref_columns(ref_name: str) -> list:
    """Return column names of a loaded reference file, or [] if not found."""
    if not ref_name or ref_name == "(none)":
        return []
    ref_files: dict = st.session_state.get("reference_files", {})
    df = ref_files.get(ref_name)
    if df is None:
        return []
    return list(df.columns)
