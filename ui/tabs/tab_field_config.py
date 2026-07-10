# ui/tabs/tab_field_config.py — Tab 1: Field Configuration
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from config import (
    BRAND_COLOR,
    PATTERNS,
    PATTERN_LABELS,
    SEVERITY_LEVELS,
    ALL_VALIDATION_TYPES,
    VALIDATION_TYPE_LABELS,
    ADDRESS_COMPLETENESS_FIELDS,
    DTYPE_OPTIONS,       # FIX Issue 1: use central dtype list that includes pincode
    DTYPE_LABELS,        # FIX Issue 1: human-readable labels
    DTYPE_PATTERN_MAP,   # FIX Issue 1: auto-associate dtype → pattern
)
from utils.session import (
    detect_previously_processed_columns,
    load_field_registry,
    save_field_registry,
    save_project_meta,
    list_reference_files,
    save_selected_columns,
    save_address_config,
    restore_session_from_disk,
)


def render(state: dict) -> None:
    """Render Tab 1: Field Configuration."""
    st.header("⚙️ Tab 1 — Field Configuration")

    project_name = st.session_state.get("project_name")
    raw_df: Optional[pd.DataFrame] = st.session_state.get("raw_df")
    restore_session_from_disk(project_name)

    if raw_df is None or project_name is None:
        st.info("📂 Please upload a file and create/select a project on the landing page first.")
        return

    all_columns = list(raw_df.columns)

    # ── Detect previously processed columns (staggered session fix)
    prev_processed = detect_previously_processed_columns(project_name)

    st.subheader("1a. Column Selection")
    st.caption(
        f"Total columns available: **{len(all_columns)}**. "
        "Previously processed columns are shown greyed-out below."
    )

    with st.form("form_column_selection"):
        selected = []
        cols_per_row = 3
        col_groups = [all_columns[i:i+cols_per_row] for i in range(0, len(all_columns), cols_per_row)]

        for col_group in col_groups:
            row_cols = st.columns(cols_per_row)
            for j, col_name in enumerate(col_group):
                prev = col_name in prev_processed
                default = col_name in st.session_state.get("selected_columns", [])
                checked = row_cols[j].checkbox(
                    col_name,
                    value=default,
                    help="Previously processed — will be skipped unless re-selected" if prev else "",
                    key=f"col_select_{col_name}",
                )
                if checked:
                    selected.append(col_name)

        save_col = st.form_submit_button("✅ Save Column Selection", type="primary")

    if save_col:
        if not selected:
            st.error("Please select at least one column.")
        else:
            st.session_state["selected_columns"] = selected
            st.session_state["previously_processed_columns"] = prev_processed
            st.session_state["tab1_saved"] = True
            save_selected_columns(project_name, selected)
            st.success(f"✅ {len(selected)} columns selected.")
            st.rerun()

    selected_columns: List[str] = st.session_state.get("selected_columns", [])

    if not selected_columns:
        st.info("Select columns above and save to continue.")
        return

    st.divider()
    st.subheader("1b. Per-Field Configuration")
    st.caption(
        "Configure data type, display name, primary key, and expected pattern for each selected column. "
        "Choosing **Pincode** as data type auto-selects the India 6-digit pincode pattern."
    )

    existing_registry = load_field_registry(project_name)
    registry: Dict = {}

    with st.form("form_field_registry"):
        for col in selected_columns:
            meta = existing_registry.get(col, {})
            with st.expander(f"🔧 **{col}**", expanded=False):
                c1, c2, c3 = st.columns(3)
                with c1:
                    display_name = st.text_input(
                        "Display Name", value=meta.get("display_name", col),
                        key=f"disp_{col}"
                    )
                    is_pk = st.checkbox(
                        "Primary Key", value=meta.get("is_pk", False),
                        key=f"pk_{col}"
                    )
                with c2:
                    # FIX Issue 1: use DTYPE_OPTIONS which now includes pincode / postal_code
                    curr_dtype = meta.get("dtype", "string")
                    dtype_idx = DTYPE_OPTIONS.index(curr_dtype) if curr_dtype in DTYPE_OPTIONS else 0
                    dtype = st.selectbox(
                        "Data Type",
                        DTYPE_OPTIONS,
                        format_func=lambda x: DTYPE_LABELS.get(x, x),
                        index=dtype_idx,
                        key=f"dtype_{col}",
                        help="Select 'Pincode' to enforce 6-digit India pincode format automatically.",
                    )
                    nullable = st.checkbox(
                        "Nullable", value=meta.get("nullable", True),
                        key=f"null_{col}"
                    )
                with c3:
                    # FIX: add "(none)" option so a field can have no pattern
                    pattern_options = ["(none)"] + list(PATTERNS.keys())

                    # FIX Issue 1: auto-suggest pattern when dtype has a natural pattern
                    auto_pattern = DTYPE_PATTERN_MAP.get(dtype, "(none)")
                    curr_pattern = meta.get("expected_pattern", auto_pattern)
                    if curr_pattern in (None, "", "none"):
                        curr_pattern = "(none)"
                    pat_idx = pattern_options.index(curr_pattern) if curr_pattern in pattern_options else 0

                    expected_pattern = st.selectbox(
                        "Expected Pattern",
                        options=pattern_options,
                        format_func=lambda x: PATTERN_LABELS.get(x, x) if x != "(none)" else "(none)",
                        index=pat_idx,
                        key=f"pattern_{col}",
                        help="Select (none) if this field needs no pattern check. Auto-filled based on Data Type.",
                    )

                    # FIX Issue 4: show custom regex input when 'custom' is selected
                    custom_pattern_val = ""
                    if expected_pattern == "custom":
                        custom_pattern_val = st.text_input(
                            "Custom Regex Pattern",
                            value=meta.get("custom_pattern", ""),
                            key=f"custom_pattern_{col}",
                            help="Enter a valid Python regex. E.g. ^[A-Z]{2}\\d{4}$",
                        )

                    severity = st.selectbox(
                        "Default Severity",
                        SEVERITY_LEVELS,
                        index=SEVERITY_LEVELS.index(meta.get("severity", "Medium")),
                        key=f"sev_{col}",
                    )

                notes = st.text_area(
                    "Notes", value=meta.get("notes", ""),
                    height=60, key=f"notes_{col}"
                )

                registry[col] = {
                    "display_name": display_name,
                    "is_pk": is_pk,
                    "dtype": dtype,
                    "nullable": nullable,
                    "expected_pattern": None if expected_pattern == "(none)" else expected_pattern,
                    "custom_pattern": custom_pattern_val,  # FIX Issue 4
                    "severity": severity,
                    "notes": notes,
                    "last_processed": meta.get("last_processed"),
                }

        save_registry = st.form_submit_button("💾 Save Field Registry", type="primary")

    if save_registry:
        save_field_registry(project_name, registry)
        st.session_state["field_registry"] = registry
        st.session_state["tab1_saved"] = True   # FIX Bug A: robustly set on registry save
        st.success("✅ Field registry saved.")
        st.rerun()

    st.divider()

    # ── 1c: Address Group Configuration
    st.subheader("1c. Address Group Configuration")
    st.caption(
        "Define address groups mapping columns to address components for Tier 1/2/3 validation. "
        "**Tier 1** = reference file match. **Tier 2** = pincode→city structural check. "
        "**Tier 3** = Google Maps API geocoding (API key entered in Tab 3)."
    )

    existing_addr = st.session_state.get("address_config", {})
    existing_groups = existing_addr.get("groups", [])

    with st.form("form_address_groups"):
        num_groups = st.number_input(
            "Number of address groups",
            min_value=0, max_value=10,
            value=len(existing_groups),
            step=1,
        )

        groups = []
        col_options = ["(none)"] + selected_columns
        ref_options = ["(none)"] + list_reference_files(project_name)

        for g_idx in range(int(num_groups)):
            existing_g = existing_groups[g_idx] if g_idx < len(existing_groups) else {}
            with st.expander(f"📍 Address Group {g_idx+1}", expanded=g_idx == 0):
                g1, g2 = st.columns(2)
                with g1:
                    group_name = st.text_input(
                        "Group Name", value=existing_g.get("group_name", f"addr{g_idx+1}"),
                        key=f"gname_{g_idx}"
                    )
                    output_prefix = st.text_input(
                        "Output Column Prefix",
                        value=existing_g.get("output_prefix", f"addr{g_idx+1}"),
                        key=f"gprefix_{g_idx}"
                    )
                    street_col = st.selectbox(
                        "Street Column", col_options,
                        index=col_options.index(existing_g.get("street_col", "(none)")) if existing_g.get("street_col", "(none)") in col_options else 0,
                        key=f"gstreet_{g_idx}"
                    )
                    city_col = st.selectbox(
                        "City Column", col_options,
                        index=col_options.index(existing_g.get("city_col", "(none)")) if existing_g.get("city_col", "(none)") in col_options else 0,
                        key=f"gcity_{g_idx}"
                    )
                    state_col = st.selectbox(
                        "State Column", col_options,
                        index=col_options.index(existing_g.get("state_col", "(none)")) if existing_g.get("state_col", "(none)") in col_options else 0,
                        key=f"gstate_{g_idx}"
                    )
                    district_col = st.selectbox(
                        "District Column (optional)", col_options,
                        index=col_options.index(existing_g.get("district_col", "(none)")) if existing_g.get("district_col", "(none)") in col_options else 0,
                        key=f"gdistrict_{g_idx}"
                    )
                    town_col = st.selectbox(
                        "Town / Taluka Column (optional)", col_options,
                        index=col_options.index(existing_g.get("town_col", "(none)")) if existing_g.get("town_col", "(none)") in col_options else 0,
                        key=f"gtown_{g_idx}"
                    )
                with g2:
                    pincode_col = st.selectbox(
                        "Pincode Column", col_options,
                        index=col_options.index(existing_g.get("pincode_col", "(none)")) if existing_g.get("pincode_col", "(none)") in col_options else 0,
                        key=f"gpincode_{g_idx}"
                    )
                    country_col = st.selectbox(
                        "Country Column", col_options,
                        index=col_options.index(existing_g.get("country_col", "(none)")) if existing_g.get("country_col", "(none)") in col_options else 0,
                        key=f"gcountry_{g_idx}"
                    )

                    st.markdown("**Tier 1 — Reference File Match**")
                    tier1_ref = st.selectbox(
                        "Tier 1 Reference File", ref_options,
                        index=ref_options.index(existing_g.get("tier1_ref_name", "(none)")) if existing_g.get("tier1_ref_name") in ref_options else 0,
                        key=f"gt1ref_{g_idx}"
                    )

                    # FIX Issue 2: load reference columns for dropdown
                    t1_ref_cols = _get_ref_columns(tier1_ref)
                    t1_ref_col_opts = ["(none)"] + t1_ref_cols

                    tier1_ref_key_col = st.selectbox(
                        "Tier 1 Key Column (in reference)",
                        t1_ref_col_opts,
                        index=t1_ref_col_opts.index(existing_g.get("tier1_ref_key_col", "(none)")) if existing_g.get("tier1_ref_key_col") in t1_ref_col_opts else 0,
                        key=f"gt1keycol_{g_idx}",
                        help="Column in the reference file to match the pincode/key against.",
                    )
                    tier1_ref_val_col = st.selectbox(
                        "Tier 1 Value Column (in reference)",
                        t1_ref_col_opts,
                        index=t1_ref_col_opts.index(existing_g.get("tier1_ref_val_col", "(none)")) if existing_g.get("tier1_ref_val_col") in t1_ref_col_opts else 0,
                        key=f"gt1valcol_{g_idx}",
                        help="Column in the reference file whose value appears in the report as the suggested address.",
                    )

                    st.markdown("**Tier 2 — Pincode→City Structural Check**")
                    t2_ref = st.selectbox(
                        "Tier 2 Pincode Reference File", ref_options,
                        index=ref_options.index(existing_g.get("tier2_pincode_ref", "(none)")) if existing_g.get("tier2_pincode_ref") in ref_options else 0,
                        key=f"gt2ref_{g_idx}",
                        help="Reference file with (pincode, city, state, district) columns for structural validation.",
                    )
                    t2_ref_cols = _get_ref_columns(t2_ref)
                    t2_ref_col_opts = ["(none)"] + t2_ref_cols

                    t2_pin_col = st.selectbox(
                        "Pincode Column in Reference", t2_ref_col_opts,
                        index=t2_ref_col_opts.index(existing_g.get("tier2_pincode_col", "(none)")) if existing_g.get("tier2_pincode_col") in t2_ref_col_opts else 0,
                        key=f"gt2pcol_{g_idx}",
                    )
                    t2_city_col = st.selectbox(
                        "City Column in Reference", t2_ref_col_opts,
                        index=t2_ref_col_opts.index(existing_g.get("tier2_city_col", "(none)")) if existing_g.get("tier2_city_col") in t2_ref_col_opts else 0,
                        key=f"gt2ccol_{g_idx}",
                    )
                    t2_state_col = st.selectbox(
                        "State Column in Reference (optional)", t2_ref_col_opts,
                        index=t2_ref_col_opts.index(existing_g.get("tier2_state_col", "(none)")) if existing_g.get("tier2_state_col") in t2_ref_col_opts else 0,
                        key=f"gt2scol_{g_idx}",
                    )
                    t2_district_col = st.selectbox(
                        "District Column in Reference (optional)", t2_ref_col_opts,
                        index=t2_ref_col_opts.index(existing_g.get("tier2_district_col", "(none)")) if existing_g.get("tier2_district_col") in t2_ref_col_opts else 0,
                        key=f"gt2dcol_{g_idx}",
                    )

                    pincode_pattern = st.selectbox(
                        "Pincode Regex Pattern",
                        options=list(PATTERNS.keys()),
                        format_func=lambda x: PATTERN_LABELS.get(x, x),
                        index=list(PATTERNS.keys()).index(existing_g.get("pincode_pattern", "pincode_india")),
                        key=f"gpinpat_{g_idx}"
                    )
                    tier3_enabled = st.checkbox(
                        "Enable Tier 3 (Google Maps API)",
                        value=existing_g.get("tier3_enabled", False),
                        key=f"gt3_{g_idx}"
                    )

                def _nc(v):
                    return None if v == "(none)" else v

                groups.append({
                    "group_name": group_name,
                    "output_prefix": output_prefix,
                    "street_col": _nc(street_col),
                    "city_col": _nc(city_col),
                    "state_col": _nc(state_col),
                    "district_col": _nc(district_col),
                    "town_col": _nc(town_col),
                    "pincode_col": _nc(pincode_col),
                    "country_col": _nc(country_col),
                    "tier1_ref_name": _nc(tier1_ref),
                    "tier1_ref_key_col": _nc(tier1_ref_key_col),
                    "tier1_ref_val_col": _nc(tier1_ref_val_col),
                    "tier2_pincode_ref": _nc(t2_ref),
                    "tier2_pincode_col": _nc(t2_pin_col),
                    "tier2_city_col": _nc(t2_city_col),
                    "tier2_state_col": _nc(t2_state_col),
                    "tier2_district_col": _nc(t2_district_col),
                    "pincode_pattern": pincode_pattern,
                    "tier3_enabled": tier3_enabled,
                    "tier3_api_key": existing_g.get("tier3_api_key", ""),
                })

        save_addr = st.form_submit_button("💾 Save Address Groups", type="primary")

    if save_addr:
        addr_config = {"groups": groups}
        st.session_state["address_config"] = addr_config
        st.session_state["tab1_saved"] = True
        save_address_config(project_name, addr_config)
        st.success(f"✅ {len(groups)} address group(s) saved. Tab 1 complete.")
        st.rerun()


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
