# utils/session.py — Session state helpers and project persistence
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from config import (
    PROJECTS_DIR,
    CACHE_SUBDIR,
    TEST_SUBDIR,
    PROD_SUBDIR,
    REF_SUBDIR,
    PROJECT_META_FILE,
    FIELD_REGISTRY_FILE,
    CHUNK_MANIFEST_FILE,
    REVIEW_DECISIONS_FILE,
)

# ─────────────────────────────────────────────
# Default session state keys
# ─────────────────────────────────────────────
_DEFAULTS: Dict[str, Any] = {
    # Project
    "project_name": None,
    "project_path": None,
    # Upload / file
    "uploaded_file_name": None,
    "uploaded_file_path": None,
    "raw_df": None,
    "total_rows": 0,
    "total_cols": 0,
    "tier": None,
    "chunk_size": None,
    # Column selection
    "selected_columns": [],
    "previously_processed_columns": [],
    # Field registry — dict keyed by column name
    "field_registry": {},
    # Field config (Tab 1) saved flag
    "tab1_saved": False,
    # Cleaning / validation saved
    "tab2_saved": False,
    "tab3_saved": False,
    "tab4_saved": False,
    # Cleaning rules per field
    "cleaning_rules": {},
    # Validation rules list of dicts
    "validation_rules": [],
    # Test detection config
    "test_detection_config": [],
    # Address validation config
    "address_config": {},
    # Cleaned dataframe
    "cleaned_df": None,
    # Validation results list of dicts
    "validation_results": [],
    # Address validation results
    "address_results": None,
    # Review decisions dict: {(record_id, field, rule): decision}
    "review_decisions": {},
    # Run state
    "run_in_progress": False,
    "run_abort": False,
    "run_complete": False,
    "progress_value": 0.0,
    "progress_label": "",
    "run_log": [],
    # Report history list of paths
    "report_history": [],
    # Staggered session: chunk manifest
    "chunk_manifest": {},
    # Cache resume
    "cache_loaded": False,
    # Reference files: {name: dataframe}
    "reference_files": {},
}


def init_session() -> None:
    """Initialize all st.session_state keys to their defaults (idempotent)."""
    for key, value in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ─────────────────────────────────────────────
# Project path helpers
# ─────────────────────────────────────────────

def get_project_path(project_name: str) -> Path:
    """Return (and create) the project root directory."""
    p = Path(PROJECTS_DIR) / project_name
    p.mkdir(parents=True, exist_ok=True)
    for sub in [CACHE_SUBDIR, TEST_SUBDIR, PROD_SUBDIR, REF_SUBDIR]:
        (p / sub).mkdir(exist_ok=True)
    return p


def get_cache_path(project_name: str) -> Path:
    return get_project_path(project_name) / CACHE_SUBDIR


def get_test_path(project_name: str) -> Path:
    return get_project_path(project_name) / TEST_SUBDIR


def get_prod_path(project_name: str) -> Path:
    return get_project_path(project_name) / PROD_SUBDIR


def get_ref_path(project_name: str) -> Path:
    return get_project_path(project_name) / REF_SUBDIR


# ─────────────────────────────────────────────
# Project meta (project_meta.json)
# ─────────────────────────────────────────────

def save_project_meta(project_name: str, meta: Dict) -> None:
    path = get_project_path(project_name) / PROJECT_META_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)


def load_project_meta(project_name: str) -> Optional[Dict]:
    path = get_project_path(project_name) / PROJECT_META_FILE
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ─────────────────────────────────────────────
# Field registry (field_registry.json)
# ─────────────────────────────────────────────

def save_field_registry(project_name: str, registry: Dict) -> None:
    path = get_project_path(project_name) / FIELD_REGISTRY_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, default=str)


def load_field_registry(project_name: str) -> Dict:
    path = get_project_path(project_name) / FIELD_REGISTRY_FILE
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# Chunk manifest (chunk_manifest.json)
# ─────────────────────────────────────────────

def save_chunk_manifest(project_name: str, manifest: Dict) -> None:
    path = get_cache_path(project_name) / CHUNK_MANIFEST_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)


def load_chunk_manifest(project_name: str) -> Dict:
    path = get_cache_path(project_name) / CHUNK_MANIFEST_FILE
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# DataFrame cache (.pkl)
# ─────────────────────────────────────────────

def save_df_cache(project_name: str, filename: str, df) -> Path:
    """Save a dataframe as pickle to cache dir. Returns path."""
    path = get_cache_path(project_name) / filename
    with open(path, "wb") as f:
        pickle.dump(df, f)
    return path


def load_df_cache(project_name: str, filename: str):
    """Load a dataframe from cache dir. Returns None if not found."""
    path = get_cache_path(project_name) / filename
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


def cache_exists(project_name: str, filename: str) -> bool:
    path = get_cache_path(project_name) / filename
    return path.exists()


# ─────────────────────────────────────────────
# Review decisions persistence
# ─────────────────────────────────────────────

def save_review_decisions(project_name: str, decisions: Dict) -> None:
    path = get_cache_path(project_name) / REVIEW_DECISIONS_FILE
    with open(path, "wb") as f:
        pickle.dump(decisions, f)


def load_review_decisions(project_name: str) -> Dict:
    path = get_cache_path(project_name) / REVIEW_DECISIONS_FILE
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return {}


# ─────────────────────────────────────────────
# Reference file helpers
# ─────────────────────────────────────────────

def save_reference_file(project_name: str, ref_name: str, df) -> Path:
    path = get_ref_path(project_name) / f"{ref_name}.pkl"
    with open(path, "wb") as f:
        pickle.dump(df, f)
    return path


def load_reference_file(project_name: str, ref_name: str):
    path = get_ref_path(project_name) / f"{ref_name}.pkl"
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


def list_reference_files(project_name: str):
    ref_path = get_ref_path(project_name)
    return [f.stem for f in ref_path.glob("*.pkl")]


# ─────────────────────────────────────────────
# Detect if a column was previously processed
# ─────────────────────────────────────────────

def detect_previously_processed_columns(project_name: str) -> list:
    """
    Reads field_registry to find columns that have been through a full run.
    Returns list of column names.
    """
    registry = load_field_registry(project_name)
    processed = []
    for col, meta in registry.items():
        if meta.get("last_processed") is not None:
            processed.append(col)
    return processed


# ─────────────────────────────────────────────
# Staggered session: merge cached cleaned DF as starting point
# ─────────────────────────────────────────────

def get_staggered_base_df(project_name: str):
    """
    Returns the most recent cleaned.pkl as the starting point for a new session,
    or None if no cache exists. This is the fix for staggered session detection bug.
    """
    cached = load_df_cache(project_name, "cleaned.pkl")
    if cached is not None:
        return cached
    # Fall back to raw cache
    return load_df_cache(project_name, "raw.pkl")


# ─────────────────────────────────────────────
# Run log helpers
# ─────────────────────────────────────────────

def append_run_log(message: str, level: str = "INFO") -> None:
    import datetime
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "level": level,
        "message": message,
    }
    if "run_log" not in st.session_state:
        st.session_state["run_log"] = []
    st.session_state["run_log"].append(entry)


def clear_run_log() -> None:
    st.session_state["run_log"] = []


# ─────────────────────────────────────────────
# Project listing
# ─────────────────────────────────────────────

def list_projects() -> list:
    root = Path(PROJECTS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return sorted([d.name for d in root.iterdir() if d.is_dir()])


# ─────────────────────────────────────────────
# Cleaning rules persistence
# ─────────────────────────────────────────────

def save_cleaning_rules(project_name: str, rules: Dict) -> None:
    path = get_project_path(project_name) / "cleaning_rules.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, default=str)


def load_cleaning_rules(project_name: str) -> Dict:
    path = get_project_path(project_name) / "cleaning_rules.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# Validation rules persistence
# ─────────────────────────────────────────────

def save_validation_rules(project_name: str, rules: list) -> None:
    path = get_project_path(project_name) / "validation_rules.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, default=str)


def load_validation_rules(project_name: str) -> list:
    path = get_project_path(project_name) / "validation_rules.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ─────────────────────────────────────────────
# Address config persistence
# ─────────────────────────────────────────────

def save_address_config(project_name: str, config: Dict) -> None:
    path = get_project_path(project_name) / "address_config.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, default=str)


def load_address_config(project_name: str) -> Dict:
    path = get_project_path(project_name) / "address_config.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# Selected columns persistence
# ─────────────────────────────────────────────

def save_selected_columns(project_name: str, columns: list) -> None:
    path = get_project_path(project_name) / "selected_columns.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(columns, f, indent=2)


def load_selected_columns(project_name: str) -> list:
    path = get_project_path(project_name) / "selected_columns.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ─────────────────────────────────────────────
# Restore full session from disk after restart
# Call this at the top of any tab that needs saved state
# ─────────────────────────────────────────────

def restore_session_from_disk(project_name: str) -> None:
    """
    Reloads all persisted config from disk into session_state.
    Safe to call on every render — only restores what's missing.
    """
    if not project_name:
        return

    if not st.session_state.get("selected_columns"):
        cols = load_selected_columns(project_name)
        if cols:
            st.session_state["selected_columns"] = cols
            st.session_state["tab1_saved"] = True

    if not st.session_state.get("field_registry"):
        reg = load_field_registry(project_name)
        if reg:
            st.session_state["field_registry"] = reg
            st.session_state["tab1_saved"] = True

    if not st.session_state.get("address_config"):
        addr = load_address_config(project_name)
        if addr:
            st.session_state["address_config"] = addr

    if not st.session_state.get("cleaning_rules"):
        cr = load_cleaning_rules(project_name)
        if cr:
            st.session_state["cleaning_rules"] = cr
            st.session_state["tab2_saved"] = True

    if not st.session_state.get("validation_rules"):
        vr = load_validation_rules(project_name)
        if vr:
            st.session_state["validation_rules"] = vr
            st.session_state["tab3_saved"] = True

    # Reload reference files from disk into session_state
    if not st.session_state.get("reference_files"):
        ref_files = {}
        for ref_name in list_reference_files(project_name):
            df = load_reference_file(project_name, ref_name)
            if df is not None:
                ref_files[ref_name] = df
        if ref_files:
            st.session_state["reference_files"] = ref_files
