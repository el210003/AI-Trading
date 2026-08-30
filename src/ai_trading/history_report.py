"""History-availability report (DATA-05): discover the terminal-AVAILABLE
history depth per (symbol, timeframe), detect aligned-timeframe gaps in the
stored bars, and persist both to SQLite so Phase 3 backtest range validation
can consume them WITHOUT any MT5 client.

Pattern of record:
- RESEARCH.md Code Example 3 walk-back note (step date_from backward in 1-year
  chunks; a persistent None + code -4 marks the start of available history or
  the maxbars cap â€” record both).
- RESEARCH.md Code Example 4 history_bounds DDL via meta_store helpers.
- RESEARCH.md Pitfall 2 (terminal_maxbars provenance is MANDATORY in every
  bounds row â€” the "Max. bars in chart" cap silently bounds history).
- RESEARCH.md Pitfall 6 (weekend/holiday gaps are REPORTED for review, never
  raised â€” session-aware classification is a reporting-only heuristic).

Discovery walk shape â€” deviation from the plan's "chunk start to now" sketch,
mandated by live probing of the IC Markets terminal (2026-08-30): a range
request whose span needs more than terminal maxbars bars fails with error -2
"Invalid params" (8y of M15 > 250k maxbars), and pre-history windows do NOT
return None/-4 â€” they clamp to the very first available bar. The walk
therefore uses NARROW non-overlapping 1-year windows stepping backward and
stops on: a persistent None/-4 chunk, a window that adds zero new unique rows
(covers both the clamp and the maxbars cap), or the 15-year safety bound.

The MetaTrader5 import lives ONLY in ai_trading.mt5_client; `client`
parameters accept the mt5_client module by default and any object with the
same function surface (tests inject FakeMT5Client).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from ai_trading import mt5_client
from ai_trading.collector import fetch_range_until_stable, to_server_wall
from ai_trading.config import load_config
from ai_trading.mt5_client import MT5DataError
from ai_trading.normalize import TIMEFRAME_MINUTES, floor_to_timeframe
from ai_trading.stores import bar_store, meta_store

log = logging.getLogger(__name__)

# Safety bound guaranteeing the backward walk terminates (research sketch:
# "bound the walk (e.g. 15 years)"). Raised to 30 after live probing showed
# this broker serves EURUSD H1/H4 back to the 1999 inception era — a 15-year
# bound truncated discovery at 2011 and reported a walk-bound, not the true
# available start.
_MAX_WALK_YEARS = 30

# Gap spans at or above this many hours are candidates for the weekend
# classification (Fri ~21-22h UTC close -> Sun ~21-22h UTC open is ~47-49h).
_WEEKEND_MIN_HOURS = 47


# ---------------------------------------------------------------------------
# DATA-05 discovery: terminal-available history depth
# ---------------------------------------------------------------------------


def discover_history_bounds(cfg, symbol: str, timeframe: str, client=mt5_client) -> dict:
    """Walk backward from now in narrow 1-year windows until the terminal
    stops serving older bars; return the available-depth dict.

    Returns {"first_bar_utc", "last_bar_utc", "bar_count", "terminal_maxbars",
    "fetched_at"} where bar_count is deduplicated on the raw server time across
    windows, first/last are true-UTC ISO stamps (raw time - configured offset),
    and terminal_maxbars carries the mandatory Pitfall-2 provenance from
    client.terminal_info(). When the terminal serves no history at all, the
    dict carries bar_count 0 with None bounds (and still records maxbars).

    Stop conditions per window (see module docstring for the live-probed
    semantics): persistent None + code -4 (not-ready/out-of-range), a window
    adding zero new unique rows (pre-history clamp or maxbars cap), or the
    15-year safety bound. Any other persistent fetch error re-raises.
    """
    tf_enum = client.timeframe_enum(timeframe)
    now_true = datetime.now(UTC).replace(tzinfo=None)
    upper = floor_to_timeframe(now_true, timeframe)

    accumulated: dict[int, object] = {}
    for years_back in range(1, _MAX_WALK_YEARS + 1):
        window_end = upper - timedelta(days=365 * (years_back - 1))
        window_start = upper - timedelta(days=365 * years_back)
        try:
            rates = fetch_range_until_stable(
                symbol,
                tf_enum,
                to_server_wall(window_start, cfg.broker_offset_hours),
                to_server_wall(window_end, cfg.broker_offset_hours),
                client,
                max_rounds=cfg.backfill_max_rounds,
                pause=cfg.backfill_pause_seconds,
            )
        except MT5DataError:
            code, _msg = client.last_error()
            if code == mt5_client.NO_HISTORY:
                break  # start of available history (or maxbars cap) reached
            raise
        new = 0
        for row in rates if rates is not None else []:
            t = int(row["time"])
            if t not in accumulated:
                accumulated[t] = row
                new += 1
        if new == 0:
            # The window returned only already-known bars: the terminal clamps
            # pre-history windows to the first available bar (live-probed) or
            # the maxbars cap binds â€” either way this is the boundary.
            break

    info = client.terminal_info()
    maxbars = int(getattr(info, "maxbars", 0) or 0) if info is not None else None
    fetched_at = datetime.now(UTC).isoformat()
    if not accumulated:
        return {
            "first_bar_utc": None,
            "last_bar_utc": None,
            "bar_count": 0,
            "terminal_maxbars": maxbars,
            "fetched_at": fetched_at,
        }
    epochs = sorted(accumulated)
    shift = pd.Timedelta(hours=cfg.broker_offset_hours)
    return {
        "first_bar_utc": (pd.to_datetime(epochs[0], unit="s") - shift).isoformat(),
        "last_bar_utc": (pd.to_datetime(epochs[-1], unit="s") - shift).isoformat(),
        "bar_count": len(accumulated),
        "terminal_maxbars": maxbars,
        "fetched_at": fetched_at,
    }


# ---------------------------------------------------------------------------
# DATA-05 gap detection + classification (report, never crash â€” Pitfall 6)
# ---------------------------------------------------------------------------


def compute_gaps(df: pd.DataFrame, timeframe: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Aligned-timeframe holes inside the observed range [first_bar, last_bar].

    Builds the expected bar-open grid anchored at min time_utc and stepping
    TIMEFRAME_MINUTES[timeframe]; contiguous missing slots merge into one
    (gap_start_utc, gap_end_utc) pair per hole, where gap_end is the last
    missing slot's open advanced by one step (the next present bar's open).
    Returns pairs sorted ascending. Holes outside the observed range are
    unobservable and therefore not reported.

    The grid is anchored at the OBSERVED minimum (not floor(min) to midnight
    UTC): bars are TF-aligned by construction (normalize boundary guarantee),
    so min lies on the true bar lattice — which for H4 on IC Markets is the
    21:00-UTC server-midnight anchor {1,5,9,13,17,21}-hour UTC grid, not the
    midnight-UTC lattice. A midnight-anchored grid would classify every real
    H4 bar as missing (live-verified correction, 2026-08-30).
    """
    if df.empty:
        return []
    step = TIMEFRAME_MINUTES[timeframe]
    times = pd.DatetimeIndex(df["time_utc"])
    grid = pd.date_range(start=times.min(), end=times.max(), freq=f"{step}min")
    present = set(times)
    step_delta = pd.Timedelta(minutes=step)
    missing = [ts for ts in grid if ts not in present]

    gaps: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    i = 0
    while i < len(missing):
        j = i
        while j + 1 < len(missing) and missing[j + 1] - missing[j] == step_delta:
            j += 1
        gaps.append((missing[i], missing[j] + step_delta))
        i = j + 1
    return gaps


def classify_gap(gap_start, gap_end) -> str:
    """Classify a gap for REPORTING only â€” must never raise (Pitfall 6).

    "weekend" when the span is at least ~47 hours AND crosses the
    Saturday-Sunday window; anything else is "review" for a human to eyeball.
    A weekend-sized hole is expected market downtime, never an error.
    """
    try:
        start = pd.Timestamp(gap_start)
        end = pd.Timestamp(gap_end)
        span_hours = (end - start).total_seconds() / 3600.0
        if span_hours < _WEEKEND_MIN_HOURS:
            return "review"
        covered = {
            start.normalize() + pd.Timedelta(days=k)
            for k in range((end.normalize() - start.normalize()).days + 1)
        }
        has_saturday = any(ts.weekday() == 5 for ts in covered)
        has_sunday = any(ts.weekday() == 6 for ts in covered)
        return "weekend" if has_saturday and has_sunday else "review"
    except Exception:  # reporting-only heuristic: never crash on odd input
        return "review"


# ---------------------------------------------------------------------------
# DATA-05 report generation + persistence + queryability
# ---------------------------------------------------------------------------


def generate_report(cfg, conn, client=mt5_client, discover: bool = False) -> dict:
    """Build the per-combo availability report and persist bounds + gaps.

    Per symbol x timeframe:
    (a) STORED view â€” bar_store.read_bars on the Parquet file (empty-file safe)
        gives stored first/last/count; compute_gaps runs on the stored content.
    (b) AVAILABLE depth â€” discover_history_bounds runs when `discover` is True
        (explicit --discover) OR when no history_bounds row is persisted yet
        for the combo (first generation). The persisted row carries
        terminal-AVAILABLE depth â€” the perishable measurement that needs the
        terminal â€” while stored bounds are re-derivable from Parquet on any
        later run (DATA-05: available depth, not just stored depth).
    (c) Upsert policy â€” when discovery ran and found bars, the DISCOVERED
        bounds are upserted; when discovery did not run, any existing row is
        left untouched (never clobber available depth with store bounds); when
        there is no row and discovery yields nothing, store-derived bounds are
        written so the queryable row exists.
    (d) Gaps â€” the previous combo snapshot is replaced and the current gaps
        upserted with detected_at = now (stale rows for closed gaps must not
        linger: the persisted gap set must match the current store's holes).
    (e) The report dict carries BOTH views per combo plus gaps (each with its
        classification) and terminal_maxbars.
    """
    now_iso = datetime.now(UTC).isoformat()
    combos: list[dict] = []
    for symbol in cfg.symbols:
        for timeframe in cfg.timeframes:
            path = bar_store.bar_path(Path(cfg.bars_dir), symbol, timeframe)
            stored_df = bar_store.read_bars(path)
            if stored_df.empty:
                stored = {"first": None, "last": None, "count": 0}
            else:
                stored = {
                    "first": stored_df["time_utc"].min().isoformat(),
                    "last": stored_df["time_utc"].max().isoformat(),
                    "count": int(len(stored_df)),
                }
            gaps = compute_gaps(stored_df, timeframe)

            existing = meta_store.get_history_bounds(conn, symbol, timeframe)
            discovered = None
            if discover or existing is None:
                discovered = discover_history_bounds(cfg, symbol, timeframe, client)

            if discovered is not None and discovered["bar_count"] > 0:
                meta_store.upsert_history_bounds(
                    conn,
                    symbol,
                    timeframe,
                    discovered["first_bar_utc"],
                    discovered["last_bar_utc"],
                    discovered["bar_count"],
                    discovered["terminal_maxbars"],
                    discovered["fetched_at"],
                )
            elif discovered is not None and existing is None:
                # Discovery yielded nothing (terminal served no history): fall
                # back to store-derived bounds so the queryable row exists.
                meta_store.upsert_history_bounds(
                    conn,
                    symbol,
                    timeframe,
                    stored["first"],
                    stored["last"],
                    stored["count"],
                    discovered["terminal_maxbars"],
                    now_iso,
                )

            # Replace this combo's gap snapshot (no stale rows for closed gaps).
            conn.execute(
                "DELETE FROM bar_gaps WHERE symbol = ? AND timeframe = ?",
                (symbol, timeframe),
            )
            meta_store.upsert_gaps(
                conn,
                symbol,
                timeframe,
                [(g_start.isoformat(), g_end.isoformat()) for g_start, g_end in gaps],
                now_iso,
            )

            row = meta_store.get_history_bounds(conn, symbol, timeframe)
            combos.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "stored": stored,
                    "available": row,
                    "gaps": [
                        (g_start.isoformat(), g_end.isoformat(), classify_gap(g_start, g_end))
                        for g_start, g_end in gaps
                    ],
                    "terminal_maxbars": row["terminal_maxbars"] if row else None,
                }
            )
    return {"generated_at": now_iso, "combos": combos}


def get_report(cfg, conn) -> dict:
    """Reconstruct the report purely from persisted state â€” SQLite rows plus
    the Parquet files â€” with NO MT5 client anywhere (DATA-05 queryability
    deliverable; Phase 3 backtest range validation consumes this)."""
    combos: list[dict] = []
    for symbol in cfg.symbols:
        for timeframe in cfg.timeframes:
            path = bar_store.bar_path(Path(cfg.bars_dir), symbol, timeframe)
            stored_df = bar_store.read_bars(path)
            if stored_df.empty:
                stored = {"first": None, "last": None, "count": 0}
            else:
                stored = {
                    "first": stored_df["time_utc"].min().isoformat(),
                    "last": stored_df["time_utc"].max().isoformat(),
                    "count": int(len(stored_df)),
                }
            row = meta_store.get_history_bounds(conn, symbol, timeframe)
            gaps = [
                (g_start, g_end, classify_gap(g_start, g_end))
                for g_start, g_end in meta_store.get_gaps(conn, symbol, timeframe)
            ]
            combos.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "stored": stored,
                    "available": row,
                    "gaps": gaps,
                    "terminal_maxbars": row["terminal_maxbars"] if row else None,
                }
            )
    return {"generated_at": datetime.now(UTC).isoformat(), "combos": combos}


def print_report(report: dict) -> str:
    """Render the report as an aligned table (one row per combo) plus a gap
    detail section listing every gap with its classification."""
    headers = [
        "symbol", "timeframe", "stored_first", "stored_last", "stored_count",
        "available_first", "available_last", "available_count",
        "terminal_maxbars", "gaps",
    ]
    rows: list[list[str]] = []
    for c in report["combos"]:
        avail = c["available"] or {}
        by_class: dict[str, int] = {}
        for _s, _e, cls in c["gaps"]:
            by_class[cls] = by_class.get(cls, 0) + 1
        gap_cell = f"{len(c['gaps'])} gap(s)"
        if by_class:
            gap_cell += " (" + ", ".join(f"{k}: {v}" for k, v in sorted(by_class.items())) + ")"
        rows.append(
            [
                str(c["symbol"]),
                str(c["timeframe"]),
                str(c["stored"]["first"] or "-"),
                str(c["stored"]["last"] or "-"),
                str(c["stored"]["count"]),
                str(avail.get("first_bar_utc") or "-"),
                str(avail.get("last_bar_utc") or "-"),
                str(avail.get("bar_count") if avail else "-"),
                str(c["terminal_maxbars"] if c["terminal_maxbars"] is not None else "-"),
                gap_cell,
            ]
        )

    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    lines = [
        f"MT5 history availability report â€” generated {report['generated_at']}",
        "",
        "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)),
        "  ".join("-" * w for w in widths),
    ]
    lines.extend("  ".join(cell.ljust(w) for cell, w in zip(r, widths, strict=True)) for r in rows)

    detailed = [
        (c, s, e, cls)
        for c in report["combos"]
        for (s, e, cls) in c["gaps"]
    ]
    if detailed:
        lines.append("")
        lines.append("Gap detail (start -> end [classification]):")
        for c, s, e, cls in detailed:
            lines.append(f"  {c['symbol']} {c['timeframe']}: {s} -> {e} [{cls}]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Report CLI: `uv run python -m ai_trading.history_report [--config PATH] [--discover]`.

    --discover forces a fresh terminal walk-back per combo; first generation
    (no persisted history_bounds row) discovers automatically even without the
    flag. When every combo already has a persisted row and --discover is not
    passed, the report is generated WITHOUT the terminal (queryability).
    """
    parser = argparse.ArgumentParser(
        prog="ai_trading.history_report",
        description="Persisted MT5 history-availability report (DATA-05).",
    )
    parser.add_argument(
        "--config", default="config.toml", help="path to config.toml (default: %(default)s)"
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help=(
            "force a fresh terminal walk-back per combo "
            "(first generation discovers automatically)"
        ),
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

    conn = meta_store.connect(Path(cfg.meta_db))
    try:
        needs_terminal = args.discover or any(
            meta_store.get_history_bounds(conn, symbol, timeframe) is None
            for symbol in cfg.symbols
            for timeframe in cfg.timeframes
        )
        if needs_terminal:
            if not mt5_client.initialize(path=cfg.terminal_path, timeout_ms=cfg.init_timeout_ms):
                code, msg = mt5_client.last_error()
                log.error(
                    "MT5 initialize failed [%s: %s] â€” discovery needs the running terminal; "
                    "start and log in to retry, or re-run later (persisted rows remain "
                    "queryable without it).",
                    code,
                    msg,
                )
                return 1
        try:
            report = generate_report(cfg, conn, mt5_client, discover=args.discover)
        except MT5DataError as exc:
            log.error("%s", exc)
            return 1
        print(print_report(report))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
