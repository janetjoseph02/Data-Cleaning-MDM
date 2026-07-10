# ui/tabs/tab_validation_config.py — Tab 3: Validation Configuration
from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

from config import (
    ALL_VALIDATION_TYPES,
    VALIDATION_TYPE_LABELS,
    VALIDATION_TYPE_HELP,   # FIX Issue 3: per-rule guidance
    PATTERNS,
    PATTERN_LABELS,
    SEVERITY_LEVELS,
    ADDRESS_TIERS,
)
from utils.session import list_reference_files, save_validation_rules, restore_session_from_disk


def render(state: dict) -> None:
    """Render Tab 3: Validation Configuration."""
    st.header("✅ Tab 3 — Validation Configuration")

    if not st.session_state.get("tab1_saved"):
        st.warning("🔒 Complete and save Tab 1 first.")
        return

    project_name = st.session_state.get("project_name", "")
    restore_session_from_disk(project_name)
    selected_columns: List[str] = st.session_state.get("selected_columns", [])
    ref_files = list_reference_files(project_name)
    ref_options = ["(none)"] + ref_files
    col_options = ["(none)"] + selected_columns

    if not selected_columns:
        st.info("No columns selected. Go to Tab 1.")
        return

    existing_rules: List[Dict] = st.session_state.get("validation_rules", [])

    # ── 3a. Validation Rules
    st.subheader("3a. Validation Rules")
    st.caption(
        "Add one rule per validation requirement. Each rule checks a specific data quality condition. "
        "Hover over a rule type in the dropdown to see when to use it."
    )

    # FIX Issue 3e: keep n_rules OUTSIDE form so changing it doesn't wipe fields
    n_rules = st.number_input(
        "Number of validation rules", min_value=0, max_value=100,
        value=len(existing_rules), step=1, key="n_val_rules"
    )

    with st.form("form_validation_rules"):
        new_rules = []
        for r_idx in range(int(n_rules)):
            existing_r = existing_rules[r_idx] if r_idx < len(existing_rules) else {}
            with st.expander(
                f"Rule {r_idx+1} — {VALIDATION_TYPE_LABELS.get(existing_r.get('type', ''), existing_r.get('type', 'new'))}",
                expanded=r_idx == 0
            ):
                rule_type = st.selectbox(
                    "Validation Type",
                    ALL_VALIDATION_TYPES,
                    format_func=lambda x: VALIDATION_TYPE_LABELS.get(x, x),
                    index=ALL_VALIDATION_TYPES.index(existing_r.get("type", ALL_VALIDATION_TYPES[0])),
                    key=f"vtype_{r_idx}",
                )

                # FIX Issue 3c: show help text for the selected rule type
                help_text = VALIDATION_TYPE_HELP.get(rule_type, "")
                if help_text:
                    st.info(f"ℹ️ {help_text}")

                severity = st.selectbox(
                    "Severity", SEVERITY_LEVELS,
                    index=SEVERITY_LEVELS.index(existing_r.get("severity", "Medium")),
                    key=f"vsev_{r_idx}",
                )
                rule_cfg = {"type": rule_type, "severity": severity}
                rule_cfg.update(
                    _render_val_params(r_idx, rule_type, existing_r, col_options, ref_options, selected_columns)
                )
                new_rules.append(rule_cfg)

        save_val = st.form_submit_button("💾 Save Validation Rules", type="primary")

    if save_val:
        st.session_state["validation_rules"] = new_rules
        st.session_state["tab3_saved"] = True
        save_validation_rules(project_name, new_rules)
        st.success(f"✅ {len(new_rules)} validation rule(s) saved.")
        st.rerun()

    # ── 3b. Address Validation — Tier 3 API key only
    st.divider()
    st.subheader("3b. Address Validation — Tier 3 Google Maps API Key")
    st.caption(
        "Enter your Google Maps API key here to enable Tier 3 geocoding. "
        "Reference file mappings (Tier 1 / Tier 2) are configured in **Tab 1c**. "
        "The API key is stored per address group and used only during the pipeline run."
    )

    addr_config = st.session_state.get("address_config", {"groups": []})
    groups = addr_config.get("groups", [])

    if not groups:
        st.info(
            "No address groups configured yet. "
            "Go to Tab 1 → Section 1c to define address groups and reference files first."
        )
    else:
        with st.form("form_addr_api"):
            for g_idx, group in enumerate(groups):
                with st.expander(f"📍 {group.get('group_name', f'Group {g_idx+1}')}", expanded=False):
                    api_key = st.text_input(
                        "Google Maps API Key",
                        value=group.get("tier3_api_key", ""),
                        type="password",
                        key=f"gmapi_{g_idx}",
                        help="Required only if Tier 3 geocoding is enabled for this group.",
                    )
                    tier3_on = st.checkbox(
                        "Enable Tier 3 geocoding for this group",
                        value=group.get("tier3_enabled", False),
                        key=f"t3on_{g_idx}",
                    )

                    # Show summary of what's already configured in Tab 1c (read-only)
                    st.markdown("**Currently configured in Tab 1c:**")
                    info_cols = st.columns(2)
                    info_cols[0].markdown(
                        f"- Tier 1 ref: `{group.get('tier1_ref_name') or '—'}`\n"
                        f"- Tier 2 ref: `{group.get('tier2_pincode_ref') or '—'}`"
                    )
                    info_cols[1].markdown(
                        f"- Pincode col: `{group.get('pincode_col') or '—'}`\n"
                        f"- City col: `{group.get('city_col') or '—'}`"
                    )

                    groups[g_idx] = {
                        **group,
                        "tier3_api_key": api_key,
                        "tier3_enabled": tier3_on,
                    }

            save_addr_api = st.form_submit_button("💾 Save API Keys", type="primary")

        if save_addr_api:
            addr_config["groups"] = groups
            st.session_state["address_config"] = addr_config
            st.session_state["tab3_saved"] = True
            st.success("✅ API key(s) saved.")
            st.rerun()


# ─────────────────────────────────────────────
# Per-validation-type parameter rendering
# ─────────────────────────────────────────────

def _render_val_params(
    r_idx: int,
    rule_type: str,
    existing: dict,
    col_options: List[str],
    ref_options: List[str],
    all_cols: List[str],
) -> dict:
    k = str(r_idx)
    cfg = {}

    single_col_types = {
        "mandatory_null", "data_type", "pattern_format",
        "allowed_values", "range", "pk_uniqueness",
        "string_length", "trim_validation", "completeness_score",
    }

    if rule_type in single_col_types:
        cfg["column"] = st.selectbox(
            "Column", col_options,
            index=col_options.index(existing.get("column", col_options[0])) if existing.get("column") in col_options else 0,
            key=f"vcol_{k}",
        )

    if rule_type == "data_type":
        from config import DTYPE_OPTIONS, DTYPE_LABELS
        curr_dt = existing.get("data_type", "string")
        dt_idx = DTYPE_OPTIONS.index(curr_dt) if curr_dt in DTYPE_OPTIONS else 0
        cfg["data_type"] = st.selectbox(
            "Expected Type", DTYPE_OPTIONS,
            format_func=lambda x: DTYPE_LABELS.get(x, x),
            index=dt_idx,
            key=f"vdt_{k}",
        )

    elif rule_type == "pattern_format":
        pat_keys = list(PATTERNS.keys())
        cfg["pattern_key"] = st.selectbox(
            "Pattern", pat_keys,
            format_func=lambda x: PATTERN_LABELS.get(x, x),
            index=pat_keys.index(existing.get("pattern_key", "custom")) if existing.get("pattern_key", "custom") in pat_keys else pat_keys.index("custom"),
            key=f"vpk_{k}",
        )
        # FIX Issue 4: always show custom input when custom is selected
        if cfg["pattern_key"] == "custom":
            cfg["custom_pattern"] = st.text_input(
                "Custom Regex Pattern",
                value=existing.get("custom_pattern", ""),
                key=f"vcp_{k}",
                help="Enter a valid Python regex. Example: ^[A-Z]{2}\\d{4}$ matches AB1234",
            )

    elif rule_type == "allowed_values":
        vals_str = ", ".join(existing.get("values", []))
        raw = st.text_input(
            "Allowed Values (comma-separated)", value=vals_str,
            key=f"vav_{k}",
        )
        cfg["values"] = [v.strip() for v in raw.split(",") if v.strip()]
        cfg["case_sensitive"] = st.checkbox(
            "Case Sensitive", value=existing.get("case_sensitive", False), key=f"vavcs_{k}"
        )

    elif rule_type == "range":
        c1, c2 = st.columns(2)
        cfg["min"] = c1.number_input("Min", value=float(existing.get("min", 0)), key=f"vmin_{k}")
        cfg["max"] = c2.number_input("Max", value=float(existing.get("max", 100)), key=f"vmax_{k}")

    elif rule_type == "string_length":
        c1, c2 = st.columns(2)
        cfg["min_length"] = c1.number_input(
            "Min Length", value=int(existing.get("min_length", 0)), min_value=0, key=f"vmil_{k}"
        )
        cfg["max_length"] = c2.number_input(
            "Max Length", value=int(existing.get("max_length", 255)), min_value=1, key=f"vmal_{k}"
        )

    elif rule_type == "pk_uniqueness":
        pass  # column already selected above

    elif rule_type == "completeness_score":
        cfg["columns"] = st.multiselect(
            "Columns to check", all_cols, default=existing.get("columns", all_cols[:5]),
            key=f"vcs_{k}",
        )
        cfg["threshold"] = st.slider(
            "Min Completeness (%)", 0, 100,
            value=int(existing.get("threshold", 0.8) * 100),
            key=f"vcst_{k}",
        ) / 100.0

    elif rule_type in ("cardinality_1_to_1", "cardinality_1_to_n"):
        c1, c2 = st.columns(2)
        col_a_key = "column_a" if rule_type == "cardinality_1_to_1" else "column_one"
        col_b_key = "column_b" if rule_type == "cardinality_1_to_1" else "column_many"
        label_a = "Column A (1-side)" if rule_type == "cardinality_1_to_1" else "Column (1-side, e.g. Dept)"
        label_b = "Column B (other 1-side)" if rule_type == "cardinality_1_to_1" else "Column (N-side, e.g. Employee)"
        cfg[col_a_key] = c1.selectbox(
            label_a, col_options,
            index=col_options.index(existing.get(col_a_key, col_options[0])) if existing.get(col_a_key) in col_options else 0,
            key=f"vca_{k}",
        )
        cfg[col_b_key] = c2.selectbox(
            label_b, col_options,
            index=col_options.index(existing.get(col_b_key, col_options[0])) if existing.get(col_b_key) in col_options else 0,
            key=f"vcb_{k}",
        )

        # Direction option for 1:1 cardinality
        if rule_type == "cardinality_1_to_1":
            dir_opts = ["both", "a_to_b", "b_to_a"]
            dir_labels = {
                "both": "Both directions (A↔B must be unique each way)",
                "a_to_b": "A → B only (each Column A maps to exactly 1 Column B)",
                "b_to_a": "B → A only (each Column B maps to exactly 1 Column A)",
            }
            cfg["direction"] = st.selectbox(
                "Direction",
                dir_opts,
                format_func=lambda x: dir_labels.get(x, x),
                index=dir_opts.index(existing.get("direction", "both")),
                key=f"vcdir_{k}",
                help="For 'one Site Code maps to one STP Code', select 'A → B only' with A=Site Code, B=STP Code.",
            )

    elif rule_type == "reference_existence":
        # FIX Bug F: use distinct key prefix "vref_" to avoid collision with single_col_types block
        cfg["column"] = st.selectbox(
            "Column to validate", col_options,
            index=col_options.index(existing.get("column", col_options[0])) if existing.get("column") in col_options else 0,
            key=f"vref_col_{k}",
        )
        cfg["reference_file"] = st.selectbox(
            "Reference File", ref_options,
            index=ref_options.index(existing.get("reference_file", "(none)")) if existing.get("reference_file") in ref_options else 0,
            key=f"vref_file_{k}",
        )
        # FIX Issue 2: dropdown instead of text input for reference column
        ref_cols = _get_ref_columns(cfg["reference_file"])
        ref_col_opts = ["(none)"] + ref_cols
        curr_ref_col = existing.get("reference_column", "(none)")
        cfg["reference_column"] = st.selectbox(
            "Reference Column (values to match against)",
            ref_col_opts,
            index=ref_col_opts.index(curr_ref_col) if curr_ref_col in ref_col_opts else 0,
            key=f"vref_rcol_{k}",
            help="Column in the reference file that contains the valid values.",
        )
        # FIX Issue 5 / 7: key column so engine can look up expected values in report
        cfg["key_column_in_data"] = st.selectbox(
            "Key Column in Data (optional — for expected value lookup in report)",
            col_options,
            index=col_options.index(existing.get("key_column_in_data", col_options[0])) if existing.get("key_column_in_data") in col_options else 0,
            key=f"vref_keycol_{k}",
            help="If set, the report's Expected column shows all reference values mapped to this key. "
                 "E.g. select 'pincode' here so the report shows which city names are valid for that pincode.",
        )
        cfg["key_column_in_ref"] = st.selectbox(
            "Corresponding Key Column in Reference (optional)",
            ref_col_opts,
            index=ref_col_opts.index(existing.get("key_column_in_ref", "(none)")) if existing.get("key_column_in_ref") in ref_col_opts else 0,
            key=f"vref_refkeycol_{k}",
        )

    elif rule_type == "cross_field_tuple":
        st.markdown(
            "**Usage for pincode validation:** Select `[pincode_col, city_col]` as columns and "
            "`[pincode, city]` as reference columns. For 1:N (one pincode → many valid cities), "
            "all valid cities for a failing pincode will appear in the report's Expected column."
        )
        cfg["columns"] = st.multiselect(
            "Data Columns (tuple — must be in same order as reference columns)",
            all_cols,
            default=existing.get("columns", all_cols[:2]),
            key=f"vcft_{k}",
        )
        cfg["reference_file"] = st.selectbox(
            "Reference File", ref_options,
            index=ref_options.index(existing.get("reference_file", "(none)")) if existing.get("reference_file") in ref_options else 0,
            key=f"vcft_ref_{k}",
        )
        # FIX Issue 2: dropdown for reference columns
        ref_cols = _get_ref_columns(cfg["reference_file"])
        if ref_cols:
            cfg["reference_columns"] = st.multiselect(
                "Reference Columns (same order as Data Columns above)",
                ref_cols,
                default=[c for c in existing.get("reference_columns", []) if c in ref_cols],
                key=f"vcft_rcols_{k}",
                help="Select the columns from the reference file in the SAME ORDER as the data columns above.",
            )
        else:
            # FIX Bug D: fallback text input with strip on split
            raw_rcols = st.text_input(
                "Reference Columns (comma-separated, same order — load a reference file to get a dropdown)",
                value=", ".join(existing.get("reference_columns", [])),
                key=f"vcft_rcols_text_{k}",
            )
            # FIX Bug D: strip whitespace after split
            cfg["reference_columns"] = [c.strip() for c in raw_rcols.split(",") if c.strip()]

        # Match mode dropdown
        mode_opts = ["exact", "fuzzy", "code_only"]
        mode_labels = {
            "exact": "Exact match (default — full tuple must match exactly)",
            "fuzzy": "Fuzzy match (key exact, dependent value by similarity — good for dealer names)",
            "code_only": "Code only (validate only the first/key column exists in reference)",
        }
        cfg["match_mode"] = st.selectbox(
            "Match Mode",
            mode_opts,
            format_func=lambda x: mode_labels.get(x, x),
            index=mode_opts.index(existing.get("match_mode", "exact")),
            key=f"vcft_mode_{k}",
            help="Exact for codes (pincode+city). Fuzzy for names (dealer code + dealer name). Code-only to just check the key exists.",
        )
        if cfg["match_mode"] == "fuzzy":
            cfg["fuzzy_threshold"] = st.slider(
                "Fuzzy Match Threshold (%)",
                0, 100,
                value=int(existing.get("fuzzy_threshold", 80)),
                key=f"vcft_fth_{k}",
                help="Dependent values below this similarity to any valid reference value are flagged.",
            )

    elif rule_type == "conditional_rule":
        c1, c2 = st.columns(2)
        cfg["column_a"] = c1.selectbox(
            "If Column", col_options,
            index=col_options.index(existing.get("column_a", col_options[0])) if existing.get("column_a") in col_options else 0,
            key=f"vcra_{k}",
        )
        cfg["condition_value"] = c1.text_input(
            "Equals Value", value=existing.get("condition_value", ""), key=f"vcrv_{k}"
        )
        cfg["column_b"] = c2.selectbox(
            "Then Column", col_options,
            index=col_options.index(existing.get("column_b", col_options[0])) if existing.get("column_b") in col_options else 0,
            key=f"vcrb_{k}",
        )
        cfg["expected_value"] = c2.text_input(
            "Must Equal", value=existing.get("expected_value", ""), key=f"vcrev_{k}"
        )
        cfg["bidirectional"] = st.checkbox(
            "Bidirectional", value=existing.get("bidirectional", False), key=f"vcrbi_{k}"
        )

    elif rule_type == "mutual_exclusivity":
        cfg["columns"] = st.multiselect(
            "Mutually Exclusive Columns", all_cols,
            default=existing.get("columns", all_cols[:2]),
            key=f"vme_{k}",
        )
        cfg["direction"] = st.selectbox(
            "Direction", ["at_most_one", "exactly_one", "none_or_one"],
            index=["at_most_one", "exactly_one", "none_or_one"].index(
                existing.get("direction", "at_most_one")
            ),
            key=f"vmed_{k}",
            help="at_most_one: max 1 filled. exactly_one: exactly 1 filled. none_or_one: 0 or 1 filled.",
        )

    elif rule_type == "co_occurrence":
        c1, c2 = st.columns(2)
        cfg["column_a"] = c1.selectbox(
            "Column A", col_options,
            index=col_options.index(existing.get("column_a", col_options[0])) if existing.get("column_a") in col_options else 0,
            key=f"vcoa_{k}",
        )
        cfg["column_b"] = c2.selectbox(
            "Column B", col_options,
            index=col_options.index(existing.get("column_b", col_options[0])) if existing.get("column_b") in col_options else 0,
            key=f"vcob_{k}",
        )
        cfg["mode"] = st.selectbox(
            "Mode", ["both_required", "both_empty"],
            index=["both_required", "both_empty"].index(existing.get("mode", "both_required")),
            key=f"vcom_{k}",
        )

    elif rule_type == "value_dependency":
        c1, c2 = st.columns(2)
        cfg["column_a"] = c1.selectbox(
            "Column A", col_options,
            index=col_options.index(existing.get("column_a", col_options[0])) if existing.get("column_a") in col_options else 0,
            key=f"vvda_{k}",
        )
        cfg["column_b"] = c2.selectbox(
            "Column B", col_options,
            index=col_options.index(existing.get("column_b", col_options[0])) if existing.get("column_b") in col_options else 0,
            key=f"vvdb_{k}",
        )
        cfg["bidirectional"] = st.checkbox(
            "Bidirectional", value=existing.get("bidirectional", True), key=f"vvdbi_{k}"
        )

    elif rule_type == "arithmetic_consistency":
        cfg["operands"] = st.multiselect(
            "Operand Columns", all_cols, default=existing.get("operands", all_cols[:2]),
            key=f"vac_op_{k}",
        )
        cfg["operator"] = st.selectbox(
            "Operator", ["+", "-", "*", "/"],
            index=["+", "-", "*", "/"].index(existing.get("operator", "+")),
            key=f"vac_oper_{k}",
        )
        cfg["column_result"] = st.selectbox(
            "Result Column", col_options,
            index=col_options.index(existing.get("column_result", col_options[0])) if existing.get("column_result") in col_options else 0,
            key=f"vac_res_{k}",
        )
        cfg["tolerance"] = st.number_input(
            "Tolerance", value=float(existing.get("tolerance", 0.01)), min_value=0.0,
            key=f"vac_tol_{k}",
        )

    elif rule_type == "date_sequence":
        c1, c2 = st.columns(2)
        cfg["column_start"] = c1.selectbox(
            "Start Date Column", col_options,
            index=col_options.index(existing.get("column_start", col_options[0])) if existing.get("column_start") in col_options else 0,
            key=f"vds_s_{k}",
        )
        cfg["column_end"] = c2.selectbox(
            "End Date Column", col_options,
            index=col_options.index(existing.get("column_end", col_options[0])) if existing.get("column_end") in col_options else 0,
            key=f"vds_e_{k}",
        )
        cfg["strict"] = st.checkbox(
            "Strict (start < end, not <=)", value=existing.get("strict", False), key=f"vds_st_{k}"
        )

    elif rule_type == "date_year_range":
        cfg["column"] = st.selectbox(
            "Column", col_options,
            index=col_options.index(existing.get("column", col_options[0])) if existing.get("column") in col_options else 0,
            key=f"vyr_col_{k}",
        )
        c1, c2 = st.columns(2)
        cfg["min_year"] = c1.number_input(
            "Min Year", min_value=1900, max_value=2200,
            value=int(existing.get("min_year", 2020)), step=1, key=f"vyr_min_{k}",
        )
        cfg["max_year"] = c2.number_input(
            "Max Year", min_value=1900, max_value=2200,
            value=int(existing.get("max_year", 2030)), step=1, key=f"vyr_max_{k}",
        )

    elif rule_type == "grouped_fuzzy_duplicate":
        st.markdown(
            "**Usage:** Group rows by one or more columns, then find duplicate / "
            "near-duplicate values in a compare column within each group. "
            "Example: group by `Depot, Sales Group, Employee Name`, compare `Prospect Name`."
        )
        cfg["group_by_columns"] = st.multiselect(
            "Group By Columns",
            all_cols,
            default=existing.get("group_by_columns", []),
            key=f"vgfd_grp_{k}",
            help="Rows are grouped where ALL these columns match (e.g. same Depot + Sales Group + Employee).",
        )
        cfg["compare_column"] = st.selectbox(
            "Compare Column (find duplicates in this)",
            col_options,
            index=col_options.index(existing.get("compare_column", col_options[0])) if existing.get("compare_column") in col_options else 0,
            key=f"vgfd_cmp_{k}",
            help="The column checked for exact + fuzzy duplicates within each group (e.g. Prospect Name).",
        )
        cfg["threshold"] = st.slider(
            "Similarity Threshold (%)",
            0, 100,
            value=int(existing.get("threshold", 80)),
            key=f"vgfd_th_{k}",
            help="Pairs at or above this similarity are flagged as duplicates. 80 recommended — catches typos, avoids merging different people. Lower to 70 to catch more.",
        )

    elif rule_type == "mapping_cardinality":
        st.markdown(
            "**Usage:** Show how one column maps to another and flag anomalies. "
            "Example: `Sales Group` → `Sales Office` (expected 1:many). "
            "Produces dedicated **SG-SO Mapping**, **Anomalies**, and **Full Pairs** sheets in the report."
        )
        cfg["group_column"] = st.selectbox(
            "Group Column (the '1' side, e.g. Sales Group)",
            col_options,
            index=col_options.index(existing.get("group_column", col_options[0])) if existing.get("group_column") in col_options else 0,
            key=f"vmc_grp_{k}",
        )
        cfg["list_column"] = st.selectbox(
            "List Column (the 'many' side, e.g. Sales Office)",
            col_options,
            index=col_options.index(existing.get("list_column", col_options[0])) if existing.get("list_column") in col_options else 0,
            key=f"vmc_list_{k}",
        )
        cfg["max_display_values"] = st.number_input(
            "Max values shown per group (summary sheet)",
            min_value=1, max_value=200,
            value=int(existing.get("max_display_values", 15)), step=1,
            key=f"vmc_max_{k}",
            help="Long lists are capped in the summary with '(+N more)'. The Full Pairs sheet always lists every pair.",
        )

    elif rule_type == "cross_file_cardinality":
        st.markdown(
            "**Usage:** Compare a shared value (e.g. Sales Group) between TWO reference files. "
            "Upload both files as reference files first (e.g. dealer file + employee file). "
            "Classifies 1:1 / 1:many / many:1 / many:many and flags **REASSIGN** "
            "(in File A but not B) and **CHECK** (in File B but not A)."
        )
        cfg["file_a"] = st.selectbox(
            "File A (e.g. Dealer file)",
            ref_options,
            index=ref_options.index(existing.get("file_a", "(none)")) if existing.get("file_a") in ref_options else 0,
            key=f"vcfc_fa_{k}",
        )
        a_cols = ["(none)"] + _get_ref_columns(cfg["file_a"])
        cfg["sg_column_a"] = st.selectbox(
            "Sales Group Column in File A",
            a_cols,
            index=a_cols.index(existing.get("sg_column_a", "(none)")) if existing.get("sg_column_a") in a_cols else 0,
            key=f"vcfc_sga_{k}",
        )
        cfg["key_column_a"] = st.selectbox(
            "Key Column in File A (e.g. Customer / dealer code)",
            a_cols,
            index=a_cols.index(existing.get("key_column_a", "(none)")) if existing.get("key_column_a") in a_cols else 0,
            key=f"vcfc_ka_{k}",
        )
        cfg["label_a"] = st.text_input(
            "Label for File A entities", value=existing.get("label_a", "Dealer"),
            key=f"vcfc_la_{k}",
        )
        st.markdown("---")
        cfg["file_b"] = st.selectbox(
            "File B (e.g. Employee file)",
            ref_options,
            index=ref_options.index(existing.get("file_b", "(none)")) if existing.get("file_b") in ref_options else 0,
            key=f"vcfc_fb_{k}",
        )
        b_cols = ["(none)"] + _get_ref_columns(cfg["file_b"])
        cfg["sg_column_b"] = st.selectbox(
            "Sales Group Column in File B",
            b_cols,
            index=b_cols.index(existing.get("sg_column_b", "(none)")) if existing.get("sg_column_b") in b_cols else 0,
            key=f"vcfc_sgb_{k}",
        )
        cfg["key_column_b"] = st.selectbox(
            "Key Column in File B (e.g. Employee ID)",
            b_cols,
            index=b_cols.index(existing.get("key_column_b", "(none)")) if existing.get("key_column_b") in b_cols else 0,
            key=f"vcfc_kb_{k}",
        )
        cfg["label_b"] = st.text_input(
            "Label for File B entities", value=existing.get("label_b", "Employee"),
            key=f"vcfc_lb_{k}",
        )
        cfg["max_display_values"] = st.number_input(
            "Max values shown per Sales Group",
            min_value=1, max_value=200,
            value=int(existing.get("max_display_values", 15)), step=1,
            key=f"vcfc_max_{k}",
        )

    elif rule_type == "suspicious_number":
        st.markdown(
            "**Usage:** Detect fake / placeholder numbers (e.g. mobile numbers). "
            "Turn on the checks you want. Nulls are skipped."
        )
        cfg["column"] = st.selectbox(
            "Column", col_options,
            index=col_options.index(existing.get("column", col_options[0])) if existing.get("column") in col_options else 0,
            key=f"vsn_col_{k}",
        )

        c1, c2 = st.columns(2)
        cfg["check_length"] = c1.checkbox(
            "Check exact length", value=existing.get("check_length", True), key=f"vsn_cl_{k}",
        )
        cfg["expected_length"] = c2.number_input(
            "Expected length (digits)", min_value=1, max_value=20,
            value=int(existing.get("expected_length", 10)), step=1, key=f"vsn_len_{k}",
        )

        cfg["check_all_same"] = st.checkbox(
            "Flag all-same-digit (e.g. 1111111111, 9999999999)",
            value=existing.get("check_all_same", True), key=f"vsn_same_{k}",
        )

        cfg["check_repeating_block"] = st.checkbox(
            "Flag repeating blocks (e.g. 1212121212, 123123123123)",
            value=existing.get("check_repeating_block", True), key=f"vsn_rep_{k}",
        )
        if cfg["check_repeating_block"]:
            cfg["repeat_max_block"] = st.number_input(
                "Repeating block max length",
                min_value=1, max_value=5,
                value=int(existing.get("repeat_max_block", 3)), step=1,
                key=f"vsn_repmax_{k}",
                help="Detects a block of 1..N digits repeated to fill the number. 3 catches blocks like '12' or '123'.",
            )

        cfg["check_low_variety"] = st.checkbox(
            "Flag low digit variety (e.g. 1212212121 uses only 2 distinct digits)",
            value=existing.get("check_low_variety", True), key=f"vsn_var_{k}",
        )
        if cfg["check_low_variety"]:
            cfg["min_distinct_digits"] = st.number_input(
                "Minimum distinct digits required",
                min_value=1, max_value=10,
                value=int(existing.get("min_distinct_digits", 3)), step=1,
                key=f"vsn_mind_{k}",
                help="Numbers using fewer than this many unique digits are flagged. 3 flags numbers with only 1-2 distinct digits.",
            )

        cfg["check_sequential"] = st.checkbox(
            "Flag sequential (e.g. 1234567890, 9876543210)",
            value=existing.get("check_sequential", False), key=f"vsn_seq_{k}",
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
