"""Atomic narrative-record writer (AI-06 / AI-07 persistence) — copies the
backtest ``reports.py`` ``_atomic_parquet`` + ``write_run_manifest``
invariant-validation discipline (PATTERNS Shared Pattern 5).

``write_narratives(df, path)`` persists a narrative-record frame to ``path``
(default target ``data/reports/llm_narratives.parquet``, consumed by Phase 6)
through a ``.tmp`` sibling then ``os.replace`` (atomic on the same volume,
Windows included); the tmp file is unlinked even when the write fails — a
partial/corrupt/duplicate artifact is impossible (T-05-09 tampering).

Before writing it validates that every required column is present AND rejects
unknown columns, naming them (mirror ``write_run_manifest`` — refuse, never
silent). Records are indexed by the setup/candidate key and carry the full
provenance + narrative record; the ML-only fallback record still persists every
provenance column (``narrative_status`` is a labeled observable state, never
silence — T-05-08).

Pure persistence: no MetaTrader5 import, inputs never mutated.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

#: Required + allowed columns for a narrative-record frame. Records are indexed
#: by the setup/candidate key; the provenance columns are always persisted even
#: on the ML-only fallback (a labeled observable state, never silence).
NARRATIVE_COLUMNS = (
    # setup / candidate key
    "symbol",
    "timeframe",
    "direction",
    "zone_id",
    "event_id",
    "pool_id",
    "entry_time",
    # provenance + narrative record
    "p_win",
    "score_source",
    "verdict",
    "confidence",
    "reasoning",
    "citations",
    "citation_status",
    "agreement",
    "agreement_confidence",
    "narrative_status",
    "reason",
    "artifact_version",
    "created_at",
)


def _validate_columns(df: pd.DataFrame) -> None:
    """Refuse-to-write when a required column is missing or an unknown column
    is present — naming them (mirror of ``write_run_manifest``)."""
    missing = [col for col in NARRATIVE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"write_narratives invariant violated: missing required columns {missing}"
        )
    unknown = [col for col in df.columns if col not in NARRATIVE_COLUMNS]
    if unknown:
        raise ValueError(
            f"write_narratives invariant violated: unknown columns {unknown} "
            f"(allowed columns: {list(NARRATIVE_COLUMNS)})"
        )


def write_narratives(df: pd.DataFrame, path) -> Path:
    """Validate then persist ``df`` as Parquet atomically (tmp + os.replace).

    Raises without leaving a partial artifact when the frame fails schema
    validation or the write/``os.replace`` fails (``.tmp`` unlinked on failure).
    Returns the written ``Path``.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"write_narratives invariant violated: df must be a DataFrame, "
            f"got {type(df).__name__}"
        )
    _validate_columns(df)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
        os.replace(tmp, path)  # atomic on the same volume (Windows included)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return path
