"""Setup persistence store — the Parquet surface the Phase 6 engine writes and
the dashboard reads (SETUP-01/02; RESEARCH Pattern 1 + "Don't Hand-Roll" store
row). MT5-free, no MetaTrader5 import anywhere.

Design (mirrors ``backtest.runner._output_dirs`` / ``bar_store.merge_and_write``
store discipline):

- One dedup-on-``setup_id`` Parquet file at ``data/setups/setups.parquet``,
  under a resolve-under-data-root guard (ASVS V4 / threat T-06-01): every
  derived setup path must resolve beneath ``cfg.bars_dir.parent`` (the data
  root) — traversal raises instead of writing outside.
- Atomic whole-file rewrite: write to ``setups.parquet.tmp`` in the SAME
  directory then ``os.replace`` (never delete-then-write, never per-row
  appends); a failed write removes the .tmp and never leaves it behind.
- ``read_setups`` returns a frame with exactly ``SETUP_COLUMNS``; a missing or
  empty file returns the schema-correct empty frame (never raises) so the
  dashboard renders the Empty state (threat T-06-03).

Dtype discipline: string columns pinned to ``pd.StringDtype()``, timestamp
columns to ``datetime64[us]`` (mirror the ``LABEL_COLUMNS`` discipline); the
three bar-position columns (``entry_bar_idx`` / ``trigger_bar_idx`` /
``exit_idx``) are float64 so a still-pending setup's unset trigger/exit index
serializes cleanly as NaN.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

_STR_DTYPE = pd.StringDtype()

#: Ordered setup-record schema (the canonical column order for the store and
#: for the record dicts ``build_setup_record`` returns).
SETUP_COLUMNS = (
    "setup_id",
    "symbol",
    "timeframe",
    "direction",
    "entry",
    "sl_price",
    "tp_price",
    "rr_at_decision",
    "entry_bar_idx",
    "created_at",
    "zone_id",
    "event_id",
    "pool_id",
    "zone_range_high",
    "zone_range_low",
    "zone_state",
    "bias_h1",
    "bias_h4",
    "p_win",
    "score_source",
    "artifact_version",
    "evidence_json",
    "narrative_status",
    "narrative_reason",
    "narrative_verdict",
    "narrative_confidence",
    "narrative_reasoning",
    "narrative_citations",
    "agreement",
    "agreement_confidence",
    "status",
    "outcome",
    "trigger_time",
    "trigger_bar_idx",
    "closed_at",
    "exit_price",
    "exit_time",
    "exit_idx",
    "r_gross",
    "r_raw",
    "r_net",
)

#: String-typed columns.
_STR_COLS = (
    "setup_id",
    "symbol",
    "timeframe",
    "direction",
    "zone_id",
    "event_id",
    "pool_id",
    "zone_state",
    "bias_h1",
    "bias_h4",
    "score_source",
    "evidence_json",
    "narrative_status",
    "narrative_reason",
    "narrative_verdict",
    "narrative_reasoning",
    "narrative_citations",
    "agreement",
    "status",
    "outcome",
)

#: Timestamp-typed columns (datetime64[us]).
_TS_COLS = ("created_at", "trigger_time", "closed_at", "exit_time")

#: Bar-position columns (float64 so an unset trigger/exit index can be NaN).
_INT_AS_FLOAT_COLS = ("entry_bar_idx", "trigger_bar_idx", "exit_idx")


def _empty_setup_frame() -> pd.DataFrame:
    """Empty frame with exactly ``SETUP_COLUMNS`` and pinned dtypes."""
    data = {}
    for col in SETUP_COLUMNS:
        if col in _STR_COLS:
            data[col] = pd.Series(dtype=_STR_DTYPE)
        elif col in _TS_COLS:
            data[col] = pd.Series(dtype="datetime64[us]")
        elif col in _INT_AS_FLOAT_COLS:
            data[col] = pd.Series(dtype="float64")
        else:
            data[col] = pd.Series(dtype="float64")
    return pd.DataFrame(data)[list(SETUP_COLUMNS)]


def _coerce(frame: pd.DataFrame) -> pd.DataFrame:
    """Return ``frame`` reindexed to exactly ``SETUP_COLUMNS`` with the pinned
    dtypes (missing columns become empty, extra columns dropped). Input never
    mutated."""
    out = frame.reindex(columns=list(SETUP_COLUMNS))
    for col in _STR_COLS:
        out[col] = out[col].astype(_STR_DTYPE)
    for col in _TS_COLS:
        out[col] = pd.to_datetime(out[col], utc=False, errors="coerce").astype("datetime64[us]")
    for col in _INT_AS_FLOAT_COLS:
        out[col] = out[col].astype("float64")
    for col in SETUP_COLUMNS:
        if col not in _STR_COLS and col not in _TS_COLS and col not in _INT_AS_FLOAT_COLS:
            out[col] = out[col].astype("float64")
    return out


def setup_store_root(cfg) -> Path:
    """Path to ``data/setups`` derived from the data root, guarded (ASVS V4 /
    threat T-06-01): the resolved directory must resolve under
    ``cfg.bars_dir.parent`` — no traversal.

    Mirrors ``backtest.runner._output_dirs`` exactly.
    """
    data_root = Path(cfg.bars_dir).parent
    setups_dir = data_root / "setups"
    root_resolved = data_root.resolve()
    resolved = setups_dir.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(
            f"setup store directory {resolved} must resolve under the data root "
            f"{root_resolved} (path traversal refused)"
        )
    return setups_dir


def setup_store_path(cfg) -> Path:
    """Path to the setups Parquet file ``data/setups/setups.parquet``."""
    return setup_store_root(cfg) / "setups.parquet"


def read_setups(cfg) -> pd.DataFrame:
    """Read the setups frame; a missing/empty file returns the schema-correct
    empty frame (never raises) so the dashboard renders the Empty state."""
    path = setup_store_path(cfg)
    if path.exists():
        frame = pd.read_parquet(path)
    else:
        frame = pd.DataFrame(columns=list(SETUP_COLUMNS))
    return _coerce(frame)


def upsert_setups(cfg, new_frame: pd.DataFrame) -> int:
    """Merge ``new_frame`` into the setups store, dedup on ``setup_id``
    keep="last", sort deterministically (``created_at`` then ``setup_id``),
    and atomically rewrite via tmp + ``os.replace``. Returns the final row
    count; never leaves a ``.tmp`` behind (mirrors bar_store.merge_and_write).
    """
    path = setup_store_path(cfg)
    frames: list[pd.DataFrame] = []
    if path.exists():
        frames.append(pd.read_parquet(path))
    frames.append(new_frame)
    df = _coerce(pd.concat(frames, ignore_index=True))
    df = (
        df.drop_duplicates(subset=["setup_id"], keep="last")
        .sort_values(["created_at", "setup_id"])
        .reset_index(drop=True)
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
        os.replace(tmp, path)  # atomic on the same volume (Windows included)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return len(df)
