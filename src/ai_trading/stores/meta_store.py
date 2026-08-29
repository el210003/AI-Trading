"""SQLite WAL meta store: collection checkpoints, history bounds, and gap
records — the only restart/report state for the collector and report
(plans 01-02/01-03 consume these tables). DATA-04.

Pattern of record: RESEARCH.md Code Example 4 (DDL + single UPSERT
transaction), Pattern 5 (checkpoint is the ONLY restart state), Shared
Pattern "parameterized SQL only". Keys are (symbol, timeframe) throughout.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS collection_state (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  last_bar_time TEXT NOT NULL, last_success_at TEXT NOT NULL,
  PRIMARY KEY (symbol, timeframe));
CREATE TABLE IF NOT EXISTS history_bounds (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  first_bar_utc TEXT, last_bar_utc TEXT, bar_count INTEGER,
  terminal_maxbars INTEGER, fetched_at TEXT NOT NULL,
  PRIMARY KEY (symbol, timeframe));
CREATE TABLE IF NOT EXISTS bar_gaps (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  gap_start_utc TEXT NOT NULL, gap_end_utc TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  PRIMARY KEY (symbol, timeframe, gap_start_utc));
"""


def connect(meta_db: Path) -> sqlite3.Connection:
    """Create parents, open, enable WAL journal mode, apply DDL."""
    meta_db = Path(meta_db)
    meta_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(meta_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(DDL)
    return conn


def update_checkpoint(
    conn: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    last_bar_iso: str,
    now_iso: str,
) -> None:
    """Single UPSERT transaction per successful bar write (Code Example 4)."""
    conn.execute(
        """INSERT INTO collection_state (symbol, timeframe, last_bar_time, last_success_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(symbol, timeframe) DO UPDATE
             SET last_bar_time=excluded.last_bar_time,
                 last_success_at=excluded.last_success_at""",
        (symbol, timeframe, last_bar_iso, now_iso),
    )
    conn.commit()


def get_checkpoint(conn: sqlite3.Connection, symbol: str, timeframe: str) -> str | None:
    """Return last_bar_time (ISO string) for (symbol, timeframe) or None."""
    row = conn.execute(
        "SELECT last_bar_time FROM collection_state WHERE symbol = ? AND timeframe = ?",
        (symbol, timeframe),
    ).fetchone()
    return row[0] if row is not None else None


def upsert_history_bounds(
    conn: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    first_bar_utc: str,
    last_bar_utc: str,
    bar_count: int,
    terminal_maxbars: int,
    fetched_at: str,
) -> None:
    """One row per (symbol, timeframe); latest discovery wins."""
    conn.execute(
        """INSERT INTO history_bounds
             (symbol, timeframe, first_bar_utc, last_bar_utc,
              bar_count, terminal_maxbars, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(symbol, timeframe) DO UPDATE SET
             first_bar_utc=excluded.first_bar_utc,
             last_bar_utc=excluded.last_bar_utc,
             bar_count=excluded.bar_count,
             terminal_maxbars=excluded.terminal_maxbars,
             fetched_at=excluded.fetched_at""",
        (symbol, timeframe, first_bar_utc, last_bar_utc, bar_count, terminal_maxbars, fetched_at),
    )
    conn.commit()


def get_history_bounds(
    conn: sqlite3.Connection, symbol: str, timeframe: str
) -> dict | None:
    """Return the bounds row as a dict (incl. terminal_maxbars provenance) or None."""
    row = conn.execute(
        """SELECT first_bar_utc, last_bar_utc, bar_count, terminal_maxbars, fetched_at
           FROM history_bounds WHERE symbol = ? AND timeframe = ?""",
        (symbol, timeframe),
    ).fetchone()
    if row is None:
        return None
    return {
        "first_bar_utc": row[0],
        "last_bar_utc": row[1],
        "bar_count": row[2],
        "terminal_maxbars": row[3],
        "fetched_at": row[4],
    }


def upsert_gaps(
    conn: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    gaps: list[tuple[str, str]],
    detected_at: str,
) -> None:
    """Insert-or-replace gap rows keyed on (symbol, timeframe, gap_start_utc)."""
    conn.executemany(
        """INSERT OR REPLACE INTO bar_gaps
             (symbol, timeframe, gap_start_utc, gap_end_utc, detected_at)
           VALUES (?, ?, ?, ?, ?)""",
        [(symbol, timeframe, gap_start, gap_end, detected_at) for gap_start, gap_end in gaps],
    )
    conn.commit()


def get_gaps(conn: sqlite3.Connection, symbol: str, timeframe: str) -> list[tuple[str, str]]:
    """All stored gaps for (symbol, timeframe), ascending by start."""
    rows = conn.execute(
        """SELECT gap_start_utc, gap_end_utc FROM bar_gaps
           WHERE symbol = ? AND timeframe = ?
           ORDER BY gap_start_utc""",
        (symbol, timeframe),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]
