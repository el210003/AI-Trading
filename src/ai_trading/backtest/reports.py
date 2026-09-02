"""Label + canonical-stat artifact writers (BT-03/BT-04 persistence).

Pattern of record: stores/bar_store.py ``merge_and_write`` — every write goes
to a ``.tmp`` sibling in the SAME directory, then ``os.replace`` atomically;
the tmp file is unlinked even when the write fails; never delete-then-write
(Pitfall 11 / threat T-03-03).

DETERMINISM CONTRACT: label and canonical-stat bytes NEVER contain
timestamps or run ids — same-input re-runs produce byte-identical artifacts
so Phase 4 can cache by content hash. Run metadata (run id, config hash,
range, knob snapshot, created_at) lives ONLY in run_manifest.json, written
separately by write_run_manifest; regenerating the manifest never touches
label bytes. Labels are keyed by (symbol, entry_time) — dedup keep="last"
makes re-runs idempotent overwrites.

Path safety (ASVS V4 partial / threat T-03-05): every writer receives an
explicit caller-supplied directory under the data root (canonical layout:
data/labels/{SYMBOL}_{TF}.parquet, data/labels/canonical_stats.json,
data/labels/run_manifest.json, data/reports/walkforward.parquet,
data/reports/walkforward_manifest.json) and builds fixed config-driven
filenames — no user-supplied filenames; paths resolve under the data/ root
only.

Walk-forward persistence (plan 03-03): per-window artifacts must stay
BYTE-IDENTICAL across same-input re-runs for Phase 4 content-versioning —
walkforward.parquet has a deterministic filename (no timestamp/run-id,
Pitfall 11) and a stable (window_id, symbol, timeframe) sort, while all run
metadata (window boundaries, config hash, range, min_history_days,
created_at) lives ONLY in walkforward_manifest.json; regenerating the
manifest never perturbs the parquet bytes.

Pure persistence: no MetaTrader5 import, no detector calls, inputs never
mutated.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd

from ai_trading.backtest.replay import LABEL_COLUMNS
from ai_trading.backtest.walkforward import WINDOW_STATS_COLUMNS

#: Exact run-manifest key set — run metadata ONLY, never merged into label
#: or canonical-stat bytes (determinism contract above).
MANIFEST_KEYS = (
    "run_id",
    "config_hash",
    "range_start",
    "range_end",
    "min_history_days",
    "time_barrier_bars",
    "wf_train_days",
    "wf_test_days",
    "created_at",
)


def _atomic_json(obj, path: Path) -> None:
    """Write ``obj`` as JSON through tmp + os.replace (bar_store discipline)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)  # atomic on the same NTFS volume (Windows included)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _atomic_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` as Parquet through tmp + os.replace (bar_store discipline)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _json_safe(value):
    """JSON-safe scalar: NaN/inf -> None (strict JSON), numpy/pd scalars ->
    python natives; anything exotic falls back to str."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return value
    if hasattr(value, "item"):  # numpy scalars
        return _json_safe(value.item())
    return str(value)


def write_labels(labels: pd.DataFrame, labels_dir: Path, symbol: str, timeframe: str) -> Path:
    """Persist one (symbol, timeframe) label frame to
    ``labels_dir/{symbol}_{timeframe}.parquet``.

    Validates the LABEL_COLUMNS schema, dedups on ("symbol", "entry_time")
    keep="last" (idempotent overwrite on re-run; a revised row with the same
    key keeps the LAST value), sorts by entry_time, and writes atomically.
    """
    missing = [col for col in LABEL_COLUMNS if col not in labels.columns]
    if missing:
        raise ValueError(
            f"write_labels invariant violated: labels is missing required columns {missing}"
        )
    frame = labels.drop_duplicates(subset=["symbol", "entry_time"], keep="last")
    frame = frame.sort_values("entry_time").reset_index(drop=True)
    path = Path(labels_dir) / f"{symbol}_{timeframe}.parquet"
    _atomic_parquet(frame, path)
    return path


def write_canonical_stats(stats_by_sym_tf: pd.DataFrame, reports_dir: Path) -> Path:
    """Persist the per-(symbol, timeframe) canonical stats to
    ``reports_dir/canonical_stats.json``.

    Records are keyed symbol -> timeframe and include the raw_/net_ variant
    columns plus cost_delta_expectancy (D-16). No timestamp or run id is
    ever embedded — the file is byte-identical across same-input re-runs;
    non-finite floats (nan/inf guards) serialize as null.
    """
    records: dict[str, dict[str, dict]] = {}
    for row in stats_by_sym_tf.to_dict("records"):
        symbol = str(row["symbol"])
        timeframe = str(row["timeframe"])
        payload = {col: _json_safe(value) for col, value in row.items()}
        records.setdefault(symbol, {})[timeframe] = payload
    path = Path(reports_dir) / "canonical_stats.json"
    _atomic_json({"records": records}, path)
    return path


def write_run_manifest(meta: dict, reports_dir: Path) -> Path:
    """Persist run metadata ONLY to ``reports_dir/run_manifest.json``.

    ``meta`` must carry exactly MANIFEST_KEYS (run_id, config_hash, range
    start/end, min_history_days, time_barrier_bars, wf_train_days,
    wf_test_days, created_at). Keeping this separate from label/canonical
    files is what keeps label bytes identical across re-runs — created_at
    and run_id live here and nowhere else.
    """
    missing = [key for key in MANIFEST_KEYS if key not in meta]
    if missing:
        raise ValueError(
            f"write_run_manifest invariant violated: meta is missing required keys {missing}"
        )
    unknown = [key for key in meta if key not in MANIFEST_KEYS]
    if unknown:
        raise ValueError(
            f"write_run_manifest invariant violated: unknown meta keys {unknown} "
            f"(run metadata ONLY: {MANIFEST_KEYS})"
        )
    path = Path(reports_dir) / "run_manifest.json"
    _atomic_json({key: _json_safe(meta[key]) for key in MANIFEST_KEYS}, path)
    return path


def config_hash(cfg) -> str:
    """sha256 over the Config dataclass fields, repr-safe and order-stable:
    Paths as strings, tuples sorted, dict keys sorted (json sort_keys pins
    the rest). Stable across equal Config instances; changes when any knob
    changes. Used by the run manifest and later by Phase 4 content
    versioning."""
    fields: dict = {}
    for f in dataclasses.fields(cfg):
        value = getattr(cfg, f.name)
        if isinstance(value, Path):
            value = str(value)
        elif isinstance(value, tuple):
            value = sorted(value)
        elif isinstance(value, dict):
            value = {str(k): value[k] for k in sorted(value, key=str)}
        fields[f.name] = value
    payload = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Walk-forward artifact writers (plan 03-03) — same atomic helpers, same
# determinism contract: data bytes carry no run metadata, ever.
# ---------------------------------------------------------------------------

#: Exact walkforward-manifest key set — window/run metadata ONLY, never
#: merged into walkforward.parquet bytes (same separation discipline as
#: MANIFEST_KEYS above).
WINDOW_MANIFEST_KEYS = (
    "windows",
    "config_hash",
    "range_start",
    "range_end",
    "min_history_days",
    "created_at",
)

_WINDOW_ENTRY_KEYS = ("window_id", "test_start", "test_end", "train_days", "test_days")


def _json_safe_ts(value):
    """JSON-safe timestamp: pd.Timestamp -> ISO string; rest via _json_safe."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return _json_safe(value)


def write_walkforward(window_stats: pd.DataFrame, reports_dir: Path) -> Path:
    """Persist the per-(window_id, symbol, timeframe) stats table to
    ``reports_dir/walkforward.parquet`` atomically.

    The FILENAME is deterministic — no timestamp or run id (Pitfall 11) —
    and rows are sorted by (window_id, symbol, timeframe) inside the writer,
    so same-input re-runs are byte-identical for Phase 4 content-versioning
    regardless of the caller's row order. Missing schema columns fail fast.
    """
    missing = [col for col in WINDOW_STATS_COLUMNS if col not in window_stats.columns]
    if missing:
        raise ValueError(
            f"write_walkforward invariant violated: window_stats is missing "
            f"required columns {missing}"
        )
    frame = window_stats.sort_values(["window_id", "symbol", "timeframe"]).reset_index(
        drop=True
    )
    path = Path(reports_dir) / "walkforward.parquet"
    _atomic_parquet(frame, path)
    return path


def write_window_manifest(windows_meta: dict, reports_dir: Path) -> Path:
    """Persist window/run metadata ONLY to
    ``reports_dir/walkforward_manifest.json`` atomically.

    ``windows_meta`` must carry exactly WINDOW_MANIFEST_KEYS: ``windows`` (a
    list of {window_id, test_start, test_end, train_days, test_days} entries;
    pd.Timestamp bounds serialize as ISO strings), plus config_hash, range
    start/end, min_history_days and created_at. Keeping this separate from
    walkforward.parquet is what keeps the data bytes identical across
    re-runs — created_at lives here and nowhere else.
    """
    missing = [key for key in WINDOW_MANIFEST_KEYS if key not in windows_meta]
    if missing:
        raise ValueError(
            f"write_window_manifest invariant violated: meta is missing required "
            f"keys {missing}"
        )
    unknown = [key for key in windows_meta if key not in WINDOW_MANIFEST_KEYS]
    if unknown:
        raise ValueError(
            f"write_window_manifest invariant violated: unknown meta keys {unknown} "
            f"(window metadata ONLY: {WINDOW_MANIFEST_KEYS})"
        )
    windows_out: list[dict] = []
    for entry in windows_meta["windows"]:
        entry_missing = [key for key in _WINDOW_ENTRY_KEYS if key not in entry]
        if entry_missing:
            raise ValueError(
                f"write_window_manifest invariant violated: window entry is "
                f"missing keys {entry_missing}"
            )
        windows_out.append({key: _json_safe_ts(entry[key]) for key in _WINDOW_ENTRY_KEYS})
    payload = {
        key: (windows_out if key == "windows" else _json_safe(windows_meta[key]))
        for key in WINDOW_MANIFEST_KEYS
    }
    path = Path(reports_dir) / "walkforward_manifest.json"
    _atomic_json(payload, path)
    return path
