# core/chunker.py — Tier detection and chunked iteration
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import pandas as pd
import numpy as np

from config import (
    TIER_SMALL_MAX,
    TIER_MEDIUM_MAX,
    CHUNK_SIZE_MEDIUM,
    CHUNK_SIZE_LARGE,
)


class Chunker:
    """
    Detects tier from row count and provides chunk-based iteration.

    Tier definitions
    ───────────────
    Small  : <= TIER_SMALL_MAX rows   → in-memory, single pass
    Medium : <= TIER_MEDIUM_MAX rows  → 50K row chunks
    Large  : > TIER_MEDIUM_MAX rows   → 100K streaming chunks
    """

    def __init__(self, total_rows: int):
        self.total_rows = total_rows
        self.tier = self._detect_tier(total_rows)
        self.chunk_size = self._get_chunk_size(self.tier)
        self.num_chunks = self._compute_num_chunks()

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────

    @staticmethod
    def _detect_tier(n: int) -> str:
        if n <= TIER_SMALL_MAX:
            return "small"
        elif n <= TIER_MEDIUM_MAX:
            return "medium"
        else:
            return "large"

    @staticmethod
    def _get_chunk_size(tier: str) -> int:
        if tier == "small":
            return 0  # full in-memory
        elif tier == "medium":
            return CHUNK_SIZE_MEDIUM
        else:
            return CHUNK_SIZE_LARGE

    def _compute_num_chunks(self) -> int:
        if self.tier == "small":
            return 1
        return math.ceil(self.total_rows / self.chunk_size)

    def iter_chunks(self, df: pd.DataFrame) -> Iterator[Tuple[int, pd.DataFrame]]:
        """
        Yields (chunk_index, chunk_df) tuples.
        For small tier yields the whole DataFrame as chunk 0.
        Chunk index is 1-based for display, 0-based internally here.
        """
        if self.tier == "small":
            yield 0, df
            return

        for i in range(self.num_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size, len(df))
            yield i, df.iloc[start:end].copy()

    def iter_chunks_from_file(
        self,
        filepath: str,
        usecols: Optional[List[str]] = None,
        dtype: Optional[dict] = None,
    ) -> Iterator[Tuple[int, pd.DataFrame]]:
        """
        Stream CSV in chunks for Large tier.
        Yields (chunk_index, chunk_df).
        """
        ext = Path(filepath).suffix.lower()
        chunk_idx = 0

        if self.tier == "small":
            df = _read_file(filepath, usecols=usecols, dtype=dtype)
            yield 0, df
            return

        if ext == ".csv":
            reader = pd.read_csv(
                filepath,
                chunksize=self.chunk_size,
                usecols=usecols,
                dtype=dtype,
                low_memory=False,
            )
            for chunk in reader:
                yield chunk_idx, chunk
                chunk_idx += 1
        else:
            # Excel / parquet — load full then split
            df = _read_file(filepath, usecols=usecols, dtype=dtype)
            for i, (_, chunk) in enumerate(self.iter_chunks(df)):
                yield i, chunk

    def actual_chunk_size(self, chunk_index: int) -> int:
        """Return the actual number of rows in a given chunk (fixes config-vs-actual bug)."""
        if self.tier == "small":
            return self.total_rows
        start = chunk_index * self.chunk_size
        end = min(start + self.chunk_size, self.total_rows)
        return max(0, end - start)

    @property
    def tier_label(self) -> str:
        labels = {
            "small": f"Small (<= {TIER_SMALL_MAX:,} rows) — In-Memory",
            "medium": f"Medium (<= {TIER_MEDIUM_MAX:,} rows) — {CHUNK_SIZE_MEDIUM:,} row chunks",
            "large": f"Large (> {TIER_MEDIUM_MAX:,} rows) — {CHUNK_SIZE_LARGE:,} row streaming chunks",
        }
        return labels[self.tier]

    def progress_fraction(self, chunk_index: int) -> float:
        """Fraction of total work done after completing chunk_index (0-based)."""
        return min((chunk_index + 1) / max(self.num_chunks, 1), 1.0)

    def estimate_eta(
        self, chunk_index: int, elapsed_seconds: float
    ) -> float:
        """Estimate remaining seconds based on chunks done and elapsed time."""
        done = chunk_index + 1
        total = max(self.num_chunks, 1)
        if done == 0:
            return 0.0
        rate = elapsed_seconds / done          # seconds per chunk
        remaining = total - done
        return rate * remaining


# ─────────────────────────────────────────────
# Column normalization — fixes the float ".0" problem
# ─────────────────────────────────────────────

def normalize_integer_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    When pandas reads an Excel/CSV column that contains integers mixed with
    blank cells, it upcasts the whole column to float64, turning 421306 into
    421306.0. This corrupts codes, pincodes, IDs, mobile numbers, etc. — and
    breaks reference matching against an integer master.

    This function scans every float column and, if *all* non-null values are
    whole numbers, converts them to clean strings without the trailing '.0'
    (blanks stay as None). Genuine decimals (amounts, percentages) are left
    untouched.
    """
    if df is None or df.empty:
        return df

    for col in df.columns:
        s = df[col]
        # Only consider float-typed columns
        if not pd.api.types.is_float_dtype(s):
            continue

        non_null = s.dropna()
        if non_null.empty:
            continue

        # Are all non-null values whole numbers? (e.g. 421306.0, not 421306.5)
        try:
            is_whole = np.isclose(non_null, np.round(non_null)).all()
        except (TypeError, ValueError):
            continue

        if not is_whole:
            continue  # genuine decimals — leave as float

        # Convert to clean integer-strings, preserving blanks as None
        def _to_clean_str(v):
            if pd.isna(v):
                return None
            return str(int(round(v)))

        df[col] = s.map(_to_clean_str).astype("object")

    return df


# ─────────────────────────────────────────────
# File-reading helper
# ─────────────────────────────────────────────

def _read_file(
    filepath: str,
    usecols=None,
    dtype=None,
) -> pd.DataFrame:
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, usecols=usecols, dtype=dtype, low_memory=False)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, usecols=usecols, dtype=dtype)
    elif ext == ".parquet":
        df = pd.read_parquet(filepath, columns=usecols)
    elif ext == ".json":
        df = pd.read_json(filepath)
        if usecols:
            df = df[usecols]
    elif ext == ".tsv":
        df = pd.read_csv(filepath, sep="\t", usecols=usecols, dtype=dtype)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    # Fix the float ".0" problem unless caller forced explicit dtypes
    if dtype is None:
        df = normalize_integer_columns(df)
    return df


def read_uploaded_file(
    uploaded_file,
    usecols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Read a Streamlit UploadedFile object into a DataFrame."""
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, usecols=usecols, low_memory=False)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file, usecols=usecols)
    elif name.endswith(".parquet"):
        df = pd.read_parquet(uploaded_file)
        if usecols:
            df = df[usecols]
    elif name.endswith(".json"):
        df = pd.read_json(uploaded_file)
        if usecols:
            df = df[usecols]
    elif name.endswith(".tsv"):
        df = pd.read_csv(uploaded_file, sep="\t", usecols=usecols)
    else:
        raise ValueError(f"Unsupported upload type: {uploaded_file.name}")
    # Fix the float ".0" problem on every uploaded file (main + reference)
    df = normalize_integer_columns(df)
    return df


def sniff_row_count(uploaded_file) -> int:
    """
    Fast row count for CSV using line counting, or len(df) for others.
    """
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".csv") or name.endswith(".tsv"):
        count = sum(1 for _ in uploaded_file) - 1  # subtract header
        uploaded_file.seek(0)
        return max(count, 0)
    else:
        df = read_uploaded_file(uploaded_file)
        uploaded_file.seek(0)
        return len(df)
