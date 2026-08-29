"""Parquet bar persistence: one file per (symbol, timeframe), idempotent
merge, atomic whole-file rewrite, closed-bars-only (DATA-04).

Pattern of record: RESEARCH.md Pattern 3 (concat + drop_duplicates on the RAW
bar-open `time`, keep="last" so a refetched bar overwrites) + "Don't Hand-Roll"
(temp file + os.replace, never delete-then-write, never per-row appends) +
Pitfall 4 forming-bar guard via normalize.assert_closed_bars (reused, not
duplicated). This is the single Parquet write path for the project — plans
01-02/01-03 call merge_and_write and never write bar files themselves.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ai_trading.normalize import COLUMNS, assert_closed_bars


def bar_path(bars_dir: Path, symbol: str, timeframe: str) -> Path:
    """Canonical layout: data/bars/{SYMBOL}_{TF}.parquet (RESEARCH structure)."""
    return Path(bars_dir) / f"{symbol}_{timeframe}.parquet"


def read_bars(path: Path) -> pd.DataFrame:
    """Read a bar file; missing file -> empty frame with the canonical columns."""
    path = Path(path)
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=COLUMNS)


def merge_and_write(
    new: pd.DataFrame,
    path: Path,
    timeframe: str,
    now_utc: datetime | None = None,
) -> int:
    """Idempotently merge `new` bars into the Parquet at `path`; return final row count.

    Order of operations (Pattern 3 + Pitfall 4/5):
    1. forming-bar guard on the incoming frame (defaults to true-UTC now)
    2. concat existing + new, dedup on RAW bar-open `time` keep="last"
    3. sort ascending by time, reset index
    4. write to a .tmp file in the SAME directory, os.replace() atomically
    5. never leave a .tmp behind, even when the write fails
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)
    assert_closed_bars(new, timeframe, now_utc)

    path = Path(path)
    frames: list[pd.DataFrame] = []
    if path.exists():
        frames.append(pd.read_parquet(path))
    frames.append(new)
    df = pd.concat(frames, ignore_index=True)
    df = (
        df.drop_duplicates(subset=["time"], keep="last")
        .sort_values("time")
        .reset_index(drop=True)
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
        os.replace(tmp, path)  # atomic on the same NTFS volume (Windows included)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return len(df)
