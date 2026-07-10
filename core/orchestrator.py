# core/orchestrator.py — Full Pipeline Orchestrator
from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from config import (
    CHUNK_MANIFEST_FILE,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    TEST_ENV_ROWS,
)
from core.chunker import Chunker, read_uploaded_file
from core.cleaning import CleaningEngine
from core.validation import ValidationEngine
from core.test_detection import TestDetectionEngine
from core.address_validator import AddressValidator
from utils.session import (
    append_run_log,
    clear_run_log,
    get_staggered_base_df,
    load_chunk_manifest,
    save_chunk_manifest,
    save_df_cache,
    load_df_cache,
    save_review_decisions,
    detect_previously_processed_columns,
)


class Orchestrator:
    """
    Sequences the full MDM pipeline:
      Upload → Parse → Tier → Cache → Column Select →
      Field Config → Test Detection → Clean → Validate →
      Address Validate → Review → Report

    Provides a realistic progress bar with ETA via pre-calculated work units.
    Supports per-field and per-chunk error handling.
    Supports chunk resume on interruption.
    """

    STAGE_WEIGHTS = {
        "init": 0.02,
        "test_detection": 0.05,
        "cleaning": 0.40,
        "validation": 0.35,
        "address_validation": 0.15,
        "finalize": 0.03,
    }

    def __init__(
        self,
        project_name: str,
        raw_df: pd.DataFrame,
        selected_columns: List[str],
        cleaning_rules: Dict[str, List[Dict]],
        validation_rules: List[Dict],
        test_detection_config: List[Dict],
        address_config: Dict,
        reference_files: Dict[str, pd.DataFrame],
        field_registry: Dict,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        abort_flag_fn: Optional[Callable[[], bool]] = None,
        run_mode: str = "fresh_run",
        all_selected_columns: Optional[List[str]] = None,
    ):
        self.project_name = project_name
        self.raw_df = raw_df
        self.selected_columns = selected_columns
        self.cleaning_rules = cleaning_rules
        self.validation_rules = validation_rules
        self.test_detection_config = test_detection_config
        self.address_config = address_config
        self.reference_files = reference_files
        self.field_registry = field_registry
        self._progress_cb = progress_callback or (lambda v, l: None)
        self._abort_fn = abort_flag_fn or (lambda: False)
        self.run_mode = run_mode
        self.all_selected_columns = all_selected_columns or selected_columns

        self.chunker = Chunker(len(raw_df))
        self.pk_seen: Set = set()
        self._run_log: List[Dict] = []
        self._validation_issues: List[Dict] = []
        self._cleaning_log: List[Dict] = []
        self._start_time: float = 0.0
        self._total_units = self._calculate_work_units()

    # ─────────────────────────────────────────
    # Work unit pre-calculation
    # ─────────────────────────────────────────

    def _calculate_work_units(self) -> int:
        n_chunks = max(self.chunker.num_chunks, 1)
        n_clean_rules = sum(len(v) for v in self.cleaning_rules.values())
        n_val_rules = len(self.validation_rules)
        has_addr = bool(self.address_config.get("groups"))

        units = (
            n_chunks * max(n_clean_rules, 1) +
            n_chunks * max(n_val_rules, 1) +
            (n_chunks * 2 if has_addr else 0) +
            2
        )
        return max(units, 1)

    # ─────────────────────────────────────────
    # Main run
    # ─────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        self._start_time = time.time()
        clear_run_log()
        self._units_done = 0
        result = {
            "success": False,
            "cleaned_df": None,
            "validation_issues": [],
            "analysis_tables": {},
            "cleaning_log": [],
            "run_log": [],
            "test_summary": {},
            "error": None,
        }

        try:
            # ── Stage 0: Init
            self._update_progress(0.0, "🔄 Initializing pipeline…")
            self._log("INFO", f"Starting run for project '{self.project_name}'")
            self._log("INFO", f"Tier: {self.chunker.tier_label}")
            self._log("INFO", f"Total rows: {len(self.raw_df):,}")
            self._log("INFO", f"Chunks: {self.chunker.num_chunks}")
            self._tick(2)

            # ── Staggered session: mode-aware base selection
            if self.run_mode == "fresh_run":
                working_df = self.raw_df.copy()
                self._log("INFO", "Fresh run: starting from raw data.")
            else:
                base_df = get_staggered_base_df(self.project_name)
                if base_df is not None:
                    self._log("INFO", f"Staggered run ({self.run_mode}): using existing cleaned cache as base.")
                    working_df = base_df.copy()
                    extra_cols = [
                        c for c in self.all_selected_columns
                        if c not in self.selected_columns and c in base_df.columns
                    ]
                    if extra_cols:
                        self._log("INFO", f"Preserving {len(extra_cols)} previously-cleaned column(s): {extra_cols}")
                else:
                    self._log("INFO", "No cached cleaned data found — falling back to raw data.")
                    working_df = self.raw_df.copy()

            # ── Load chunk manifest for resume support.
            # On a fresh run, START EMPTY so we never skip chunks that were
            # completed in a PREVIOUS run (otherwise validation/cleaning are
            # skipped and the report comes out blank).
            if self.run_mode == "fresh_run":
                manifest = {}
                save_chunk_manifest(self.project_name, manifest)
            else:
                manifest = load_chunk_manifest(self.project_name)
            completed_chunks = set(manifest.get("completed_cleaning_chunks", []))

            if self._check_abort():
                result["error"] = "Aborted"
                return result

            # ── Stage 1: Test Detection
            self._update_progress(None, "🔍 Running test detection…")
            test_engine = TestDetectionEngine(self.test_detection_config)
            working_df = test_engine.detect(working_df)
            test_summary = TestDetectionEngine.test_record_summary(working_df)
            result["test_summary"] = test_summary
            self._log("INFO", f"Test records flagged: {test_summary['test']}")
            self._tick(1)

            if self._check_abort():
                result["error"] = "Aborted"
                return result

            # ── Stage 2: Cleaning (chunked)
            self._update_progress(None, "🧹 Cleaning data…")
            cleaning_engine = CleaningEngine(
                {col: rules for col, rules in self.cleaning_rules.items()
                 if col in self.selected_columns},
                reference_files=self.reference_files,
            )

            cleaned_chunks: List[pd.DataFrame] = []
            for chunk_idx, chunk_df in self.chunker.iter_chunks(working_df):
                if self._check_abort():
                    result["error"] = "Aborted during cleaning"
                    return result

                if chunk_idx in completed_chunks:
                    cached_chunk = load_df_cache(
                        self.project_name, f"chunk_{chunk_idx}.pkl"
                    )
                    if cached_chunk is not None:
                        cleaned_chunks.append(cached_chunk)
                        self._tick(len(self.cleaning_rules))
                        continue

                try:
                    cleaned_chunk = cleaning_engine.apply(chunk_df, chunk_index=chunk_idx)
                except Exception as e:
                    self._log("ERROR", f"Cleaning failed on chunk {chunk_idx}: {e}")
                    cleaned_chunk = chunk_df

                save_df_cache(self.project_name, f"chunk_{chunk_idx}.pkl", cleaned_chunk)
                completed_chunks.add(chunk_idx)
                manifest["completed_cleaning_chunks"] = list(completed_chunks)
                save_chunk_manifest(self.project_name, manifest)

                cleaned_chunks.append(cleaned_chunk)
                self._tick(max(len(self.cleaning_rules), 1))

                elapsed = time.time() - self._start_time
                eta = self.chunker.estimate_eta(chunk_idx, elapsed)
                label = (
                    f"🧹 Cleaning chunk {chunk_idx+1}/{self.chunker.num_chunks}"
                    f" — ETA {_fmt_eta(eta)}"
                )
                self._update_progress(None, label)

            self._cleaning_log.extend(cleaning_engine.get_log())

            if cleaned_chunks:
                cleaned_df = pd.concat(cleaned_chunks, ignore_index=True)
            else:
                cleaned_df = working_df.copy()

            save_df_cache(self.project_name, "cleaned.pkl", cleaned_df)
            self._log("INFO", "Cleaning complete. Cleaned DF cached.")

            if self._check_abort():
                result["error"] = "Aborted after cleaning"
                return result

            # ── Stage 3: Validation (chunked, test records excluded)
            self._update_progress(None, "✅ Running validation…")
            validation_engine = ValidationEngine(
                self.validation_rules,
                reference_files=self.reference_files,
                pk_seen=self.pk_seen,
            )

            # Validation always re-runs on the current data. We only honour
            # the resume list for staggered runs (mid-run interruption recovery).
            if self.run_mode == "fresh_run":
                completed_val_chunks = set()
                manifest["completed_validation_chunks"] = []
            else:
                completed_val_chunks = set(manifest.get("completed_validation_chunks", []))
            all_issues: List[Dict] = []

            for chunk_idx, chunk_df in self.chunker.iter_chunks(cleaned_df):
                if self._check_abort():
                    result["error"] = "Aborted during validation"
                    break

                if chunk_idx in completed_val_chunks:
                    self._tick(max(len(self.validation_rules), 1))
                    continue

                try:
                    chunk_issues = validation_engine.validate(
                        chunk_df,
                        chunk_index=chunk_idx,
                        exclude_test_records=True,
                    )
                    all_issues.extend(chunk_issues)
                except Exception as e:
                    self._log("ERROR", f"Validation failed on chunk {chunk_idx}: {e}")

                completed_val_chunks.add(chunk_idx)
                manifest["completed_validation_chunks"] = list(completed_val_chunks)
                save_chunk_manifest(self.project_name, manifest)

                self._tick(max(len(self.validation_rules), 1))
                elapsed = time.time() - self._start_time
                eta = self.chunker.estimate_eta(chunk_idx, elapsed)
                self._update_progress(
                    None,
                    f"✅ Validating chunk {chunk_idx+1}/{self.chunker.num_chunks}"
                    f" — ETA {_fmt_eta(eta)} — {len(all_issues)} issues so far"
                )

            self._validation_issues = all_issues
            # Collect rich analysis tables (mapping / cross-file cardinality)
            self._analysis_tables = validation_engine.get_analysis_tables()
            self._log("INFO", f"Validation complete. Issues found: {len(all_issues)}")

            # ── Stage 4: Address validation
            if self.address_config.get("groups"):
                self._update_progress(None, "📍 Running address validation…")
                addr_validator = AddressValidator(
                    self.address_config,
                    reference_files=self.reference_files,
                )
                addr_chunks: List[pd.DataFrame] = []
                for chunk_idx, chunk_df in self.chunker.iter_chunks(cleaned_df):
                    if self._check_abort():
                        break
                    try:
                        validated_chunk = addr_validator.validate(chunk_df, chunk_index=chunk_idx)
                    except Exception as e:
                        self._log("ERROR", f"Address validation failed on chunk {chunk_idx}: {e}")
                        validated_chunk = chunk_df
                    addr_chunks.append(validated_chunk)
                    self._tick(2)

                if addr_chunks:
                    cleaned_df = pd.concat(addr_chunks, ignore_index=True)
                save_df_cache(self.project_name, "cleaned.pkl", cleaned_df)
                self._log("INFO", "Address validation complete.")

            # ── Stage 5: Finalize
            self._update_progress(None, "📦 Finalizing…")
            ts = datetime.datetime.now().isoformat()
            for col in self.selected_columns:
                if col not in self.field_registry:
                    self.field_registry[col] = {}
                self.field_registry[col]["last_processed"] = ts

            self._tick(2)
            self._update_progress(1.0, "✅ Run complete!")
            self._log("INFO", "Pipeline run complete.")

            result.update({
                "success": True,
                "cleaned_df": cleaned_df,
                "validation_issues": self._validation_issues,
                "analysis_tables": getattr(self, "_analysis_tables", {}),
                "cleaning_log": self._cleaning_log,
                "run_log": self._run_log,
            })

        except Exception as exc:
            self._log("ERROR", f"Fatal orchestrator error: {exc}")
            result["error"] = str(exc)
            self._update_progress(None, f"❌ Error: {exc}")

        return result

    # ─────────────────────────────────────────
    # Progress helpers
    # ─────────────────────────────────────────

    def _tick(self, units: int = 1) -> None:
        self._units_done = getattr(self, "_units_done", 0) + units
        fraction = min(self._units_done / self._total_units, 0.99)
        self._progress_cb(fraction, "")

    def _update_progress(self, value: Optional[float], label: str) -> None:
        if value is not None:
            self._progress_cb(value, label)
        else:
            fraction = min(
                getattr(self, "_units_done", 0) / self._total_units, 0.99
            )
            self._progress_cb(fraction, label)

    def _check_abort(self) -> bool:
        return bool(self._abort_fn())

    # ─────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────

    def _log(self, level: str, message: str) -> None:
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "level": level,
            "message": message,
        }
        self._run_log.append(entry)
        append_run_log(message, level)


# ─────────────────────────────────────────────
# ETA formatter
# ─────────────────────────────────────────────

def _fmt_eta(seconds: float) -> str:
    if seconds <= 0:
        return "< 1s"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    else:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m}m"
