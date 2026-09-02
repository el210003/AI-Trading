"""Backtest runner CLI (plan 03-03) — the executable end of Phase 3.

Wires the complete MT5-free pipeline per symbol (M15 execution only, D-06):

    D-21 history gate -> offset-uniformity guard (Pitfall 10) -> range
    resolution -> M15 + HTF warmup lead-in load (A8) -> BT-01 detector chain
    -> replay with walk_barriers (the 03-01 resolver seam closes here) ->
    canonical stats -> walk-forward windows -> artifacts.

MT5-FREE BY DESIGN: no MetaTrader5 import anywhere in backtest/ — the
runner reads stored Parquet bars via bar_store.read_bars only.

EXIT-CODE CONTRACT (pinned by tests):
- 2  config errors: load_config ValueError, --min-history-days <= 0,
     --symbols not a subset of cfg.symbols.
- 1  runtime refusals: D-21 history gate, mixed broker offsets (Pitfall 10),
     invalid --range, replay/label invariant errors. The D-21 refusal
     message carries the remedy (extend collection via Phase 1 purge +
     backfill, or pass --min-history-days) — never a silent 0-trade report.
- 0  success — INCLUDING zero-candidate runs: an empty label set after a
     gate-passing run is a valid outcome (the gate already ran), logged as
     INFO with schema-correct empty artifacts written; it never escapes the
     {0, 1, 2} exit-code contract.

RANGE FORMATS (--range):
- "YYYY-MM-DD:YYYY-MM-DD"  inclusive start day to end day, clamped to the
  stored frame bounds.
- "last-ND"                the last N days of stored bars.
- omitted                  the full stored range.

FROZEN-CONFIG OVERRIDE: --min-history-days rebuilds the config via
dataclasses.replace(cfg, ...) after load_config validation — the Config
contract is never mutated (no setattr) and no extra parameter threads
through run_backtest/check_history_gate; the override is validated > 0 at
parse time before replace.

ARTIFACT LAYOUT (aligned with plan 03-02; INFO-side consistency): label-
derived artifacts (labels parquet, canonical_stats.json, run_manifest.json)
under data/labels/; window/report artifacts (walkforward.parquet,
walkforward_manifest.json) under data/reports/. Both roots derive from
cfg.bars_dir.parent (the data/ root) and must resolve under it (ASVS V4 /
threat T-03-04) — no new config keys.

DETERMINISM: data artifacts are byte-identical across same-input re-runs;
run_id/created_at live only in the manifests.

CLI: `uv run python -m ai_trading.backtest --config config.toml --range
last-ND --write` (module entry via backtest/__main__.py).
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from ai_trading.backtest.barriers import walk_barriers
from ai_trading.backtest.chain import run_chain
from ai_trading.backtest.replay import (
    _empty_labels_frame,
    assert_offset_uniform,
    check_history_gate,
    replay_symbol,
)
from ai_trading.backtest.reports import (
    config_hash,
    write_canonical_stats,
    write_labels,
    write_run_manifest,
    write_walkforward,
    write_window_manifest,
)
from ai_trading.backtest.stats import stats_by_symbol_timeframe
from ai_trading.backtest.walkforward import (
    build_windows,
    label_window_assignment,
    window_aggregate,
    window_stats_table,
)
from ai_trading.config import load_config
from ai_trading.stores.bar_store import bar_path, read_bars

log = logging.getLogger(__name__)

_RANGE_FORMATS = (
    "accepted --range formats: 'YYYY-MM-DD:YYYY-MM-DD' (inclusive day bounds, "
    "clamped to stored bars) or 'last-ND' (last N days of stored bars); omit "
    "for the full stored range"
)


def resolve_range(range_arg: str | None, bars: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Resolve the requested range against the stored M15 frame bounds.

    Returns the inclusive (start, end) replay window: "YYYY-MM-DD:YYYY-MM-DD"
    spans the whole start day through the whole end day (clamped to the
    stored bounds), "last-ND" spans the last N days of stored bars, None
    spans (min time_utc, max time_utc). Invalid or non-intersecting ranges
    raise ValueError with the accepted formats listed.
    """
    if bars.empty:
        raise ValueError("resolve_range invariant violated: bars frame is empty")
    stored_min = pd.Timestamp(bars["time_utc"].min())
    stored_max = pd.Timestamp(bars["time_utc"].max())
    if range_arg is None:
        return stored_min, stored_max

    text = str(range_arg).strip()
    match = re.fullmatch(r"last-(\d+)", text)
    if match:
        days = int(match.group(1))
        if days <= 0:
            raise ValueError(f"invalid --range {range_arg!r}: N must be positive; {_RANGE_FORMATS}")
        return max(stored_max - pd.Timedelta(days=days), stored_min), stored_max

    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid --range {range_arg!r}: {_RANGE_FORMATS}")
    try:
        day_start = pd.Timestamp(parts[0].strip())
        day_end = pd.Timestamp(parts[1].strip())
    except ValueError as exc:
        raise ValueError(f"invalid --range {range_arg!r}: {_RANGE_FORMATS}") from exc
    if pd.isna(day_start) or pd.isna(day_end):
        raise ValueError(f"invalid --range {range_arg!r}: {_RANGE_FORMATS}")
    if day_end < day_start:
        raise ValueError(
            f"invalid --range {range_arg!r}: start day is after end day; {_RANGE_FORMATS}"
        )
    start = max(day_start.normalize(), stored_min)
    # inclusive end day: whole-day span minus one microsecond (us-precision stamps)
    end = min(day_end.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1), stored_max)
    if start > end:
        raise ValueError(
            f"invalid --range {range_arg!r}: requested range does not intersect the "
            f"stored bars ({stored_min} .. {stored_max}); {_RANGE_FORMATS}"
        )
    return start, end


def _slice_range(bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if bars.empty:
        return bars
    t = bars["time_utc"]
    return bars[(t >= start) & (t <= end)].reset_index(drop=True)


def _output_dirs(cfg) -> tuple[Path, Path]:
    """(labels_dir, reports_dir) derived from the data/ root, guarded (ASVS
    V4): both must resolve under cfg.bars_dir.parent — no traversal."""
    data_root = Path(cfg.bars_dir).parent
    labels_dir = data_root / "labels"
    reports_dir = data_root / "reports"
    root_resolved = data_root.resolve()
    for directory in (labels_dir, reports_dir):
        resolved = directory.resolve()
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise ValueError(
                f"output directory {resolved} must resolve under the data root "
                f"{root_resolved} (path traversal refused)"
            )
    return labels_dir, reports_dir


def run_backtest(cfg, symbols, range_arg: str | None, write: bool) -> dict:
    """Run the full MT5-free pipeline over ``symbols`` and return
    {labels: dict[symbol -> df], canonical, windows, window_stats,
    window_aggregate, range_start, range_end}.

    Per symbol: D-21 gate on the STORED M15 depth (refusal raises
    RuntimeError before any artifact is written), offset-uniformity guard,
    range resolution, M15 slice [start, end], HTF lead-in [start -
    cfg.htf_warmup_days, end] (A8) so confirmed legs exist before the first
    decision bar, BT-01 chain, replay with walk_barriers (resolver seam),
    optional per-symbol label write.

    Walk-forward windows derive over the COMBINED label domain so window
    boundaries are shared across symbols and the D-22 per-window aggregate
    across symbols is well-defined (identical to per-symbol derivation for
    single-symbol runs). ZERO-CANDIDATE PATH: an empty label set is
    SUPPORTED — build_windows returns [], assignment/stats return
    schema-correct empty frames, the loop continues, and per-symbol
    canonical + empty walk-forward artifacts are written normally (no
    raise, no special exit code).
    """
    labels_by_symbol: dict[str, pd.DataFrame] = {}
    range_starts: list[pd.Timestamp] = []
    range_ends: list[pd.Timestamp] = []

    for symbol in symbols:
        m15_full = read_bars(bar_path(cfg.bars_dir, symbol, "M15"))
        if m15_full.empty:
            stored_days = 0
        else:
            stored_days = int(
                (m15_full["time_utc"].max() - m15_full["time_utc"].min()).days
            )
        # D-21 gate on the STORED depth — refusal propagates to exit 1 with
        # the actionable message; never an empty 0-trade report.
        check_history_gate(stored_days, cfg.min_history_days, symbol, "M15")
        assert_offset_uniform(m15_full)  # Pitfall 10

        start, end = resolve_range(range_arg, m15_full)
        range_starts.append(start)
        range_ends.append(end)

        h1_full = read_bars(bar_path(cfg.bars_dir, symbol, "H1"))
        h4_full = read_bars(bar_path(cfg.bars_dir, symbol, "H4"))
        assert_offset_uniform(h1_full)
        assert_offset_uniform(h4_full)

        htf_start = start - pd.Timedelta(days=cfg.htf_warmup_days)  # A8 lead-in
        m15 = _slice_range(m15_full, start, end)
        h1 = _slice_range(h1_full, htf_start, end)
        h4 = _slice_range(h4_full, htf_start, end)

        chain = run_chain(m15, h1, h4)  # BT-01: the SAME detector exports
        labels = replay_symbol(m15, chain, cfg, walk_barriers)  # resolver seam

        if labels.empty:
            log.info(
                "0 candidates for %s in %s: schema-correct empty artifacts written",
                symbol,
                range_arg if range_arg else "full stored range",
            )
        if write:
            labels_dir, _ = _output_dirs(cfg)
            write_labels(labels, labels_dir, symbol, "M15")
        labels_by_symbol[symbol] = labels

    combined = (
        pd.concat(list(labels_by_symbol.values()), ignore_index=True)
        if labels_by_symbol
        else _empty_labels_frame()  # defensive: schema-correct empty (symbols never empty)
    )
    # Per-(symbol, timeframe) canonical stats, computed once over the
    # combined frame — stats_by_symbol_timeframe groups strictly by
    # (symbol, timeframe), so this equals per-symbol calls (03-02 contract).
    canonical = stats_by_symbol_timeframe(combined)
    windows = build_windows(combined["entry_time"], cfg.wf_test_days, cfg.wf_train_days)
    labels_w = label_window_assignment(combined, windows)
    window_stats = window_stats_table(labels_w)
    window_agg = window_aggregate(labels_w)

    return {
        "labels": labels_by_symbol,
        "canonical": canonical,
        "windows": windows,
        "window_stats": window_stats,
        "window_aggregate": window_agg,
        "range_start": min(range_starts) if range_starts else pd.NaT,
        "range_end": max(range_ends) if range_ends else pd.NaT,
    }


def _fmt(value: object) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else str(value)


def _summary_block(result: dict, symbols, cfg, written: list[Path]) -> str:
    lines = [
        "backtest summary",
        f"  symbols: {', '.join(symbols)}",
        f"  range: {result['range_start']} -> {result['range_end']}",
    ]
    canonical = result["canonical"]
    if canonical.empty:
        lines.append("  trades: 0 (no candidates in range)")
    else:
        for row in canonical.to_dict("records"):
            lines.append(
                f"  {row['symbol']} {row['timeframe']}: trades={row['trades']} "
                f"wins={row['wins']} losses={row['losses']} timeouts={row['timeouts']} "
                f"win_rate={_fmt(row['net_win_rate'])} "
                f"PF={_fmt(row['net_profit_factor'])} "
                f"expectancy raw/net={_fmt(row['raw_expectancy'])}/{_fmt(row['net_expectancy'])}"
            )
    lines.append(
        f"  walk-forward: {len(result['windows'])} windows "
        f"(test_days={cfg.wf_test_days}, train_days={cfg.wf_train_days}), "
        f"{len(result['window_stats'])} per-(window, symbol) stat rows, "
        f"{len(result['window_aggregate'])} aggregate rows"
    )
    if written:
        lines.append("  artifacts written:")
        lines.extend(f"    {path}" for path in written)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Backtest CLI: `uv run python -m ai_trading.backtest [options]`.

    Exit codes: 2 config error, 1 runtime refusal (gate / offset / range /
    replay), 0 success (including zero-candidate runs). See the module
    docstring for the full contract.
    """
    parser = argparse.ArgumentParser(
        prog="ai_trading.backtest",
        description=(
            "MT5-free backtest runner: gate -> chain -> replay -> barriers -> "
            "stats -> walk-forward -> artifacts (BT-05)."
        ),
    )
    parser.add_argument(
        "--config", default="config.toml", help="path to config.toml (default: %(default)s)"
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="comma-separated subset of the configured symbols (default: all)",
    )
    parser.add_argument(
        "--range",
        dest="range_arg",
        default=None,
        help="'YYYY-MM-DD:YYYY-MM-DD' inclusive, 'last-ND', or omitted for the full store",
    )
    parser.add_argument(
        "--min-history-days",
        type=int,
        default=None,
        help="override cfg.min_history_days for this run (D-21 gate); must be > 0",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write artifacts under data/labels/ and data/reports/ (dry-run summary when absent)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        cfg = load_config(Path(args.config))
    except ValueError as exc:
        log.error("invalid configuration: %s", exc)
        return 2

    if args.min_history_days is not None:
        if args.min_history_days <= 0:
            log.error(
                "--min-history-days must be a positive integer, got %s", args.min_history_days
            )
            return 2
        # Frozen Config — rebuild via replace (never setattr, no signature
        # threading); fail-fast validation already ran at load_config.
        cfg = dataclasses.replace(cfg, min_history_days=args.min_history_days)

    if args.symbols is not None:
        requested = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
        invalid = [s for s in requested if s not in cfg.symbols]
        if not requested or invalid:
            log.error(
                "--symbols must be a non-empty comma-separated subset of the configured "
                "symbols %s; rejected: %s",
                list(cfg.symbols),
                invalid if invalid else "<empty>",
            )
            return 2
        symbols = requested
    else:
        symbols = tuple(cfg.symbols)

    try:
        result = run_backtest(cfg, symbols, args.range_arg, write=args.write)
    except (RuntimeError, ValueError) as exc:
        # D-21 gate, mixed offsets, range validation, replay/label errors —
        # all refusals land on exit 1 with the actionable message.
        log.error("%s", exc)
        return 1

    written: list[Path] = []
    if args.write:
        labels_dir, reports_dir = _output_dirs(cfg)
        written.append(write_canonical_stats(result["canonical"], labels_dir))
        now_iso = datetime.now(UTC).isoformat()
        run_meta = {
            "run_id": uuid4().hex,
            "config_hash": config_hash(cfg),
            "range_start": str(result["range_start"]),
            "range_end": str(result["range_end"]),
            "min_history_days": cfg.min_history_days,
            "time_barrier_bars": cfg.time_barrier_bars,
            "wf_train_days": cfg.wf_train_days,
            "wf_test_days": cfg.wf_test_days,
            "created_at": now_iso,
        }
        written.append(write_run_manifest(run_meta, labels_dir))
        written.append(write_walkforward(result["window_stats"], reports_dir))
        windows_meta = {
            "windows": [
                {
                    "window_id": w.window_id,
                    "test_start": w.test_start,
                    "test_end": w.test_end,
                    "train_days": cfg.wf_train_days,
                    "test_days": cfg.wf_test_days,
                }
                for w in result["windows"]
            ],
            "config_hash": config_hash(cfg),
            "range_start": str(result["range_start"]),
            "range_end": str(result["range_end"]),
            "min_history_days": cfg.min_history_days,
            "created_at": now_iso,
        }
        written.append(write_window_manifest(windows_meta, reports_dir))

    print(_summary_block(result, symbols, cfg, written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
