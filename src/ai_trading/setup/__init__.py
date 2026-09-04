"""MT5-free setup surface for Phase 6 (SETUP-01..04). Public re-exports for the
dashboard (plans 06-02/06-03) and the scheduled engine.

Phase 6 is an orchestration + persistence + presentation layer over the shared
pure functions from Phases 2-5 (BT-01 / D-03): the entry rule, feature
assembly, scoring, evidence serialization, narrative pipeline and barrier
resolution are all imported verbatim — never re-implemented here.
"""

from ai_trading.setup.assembly import assemble_setup, build_setup_record
from ai_trading.setup.lifecycle import (
    ACTIVE_LIFECYCLE_STATUSES,
    apply_lifecycle,
    resolve_active,
    resolve_pending,
)
from ai_trading.setup.scheduler import run_engine_once
from ai_trading.setup.store import (
    SETUP_COLUMNS,
    read_setups,
    setup_store_path,
    setup_store_root,
    upsert_setups,
)

__all__ = [
    "ACTIVE_LIFECYCLE_STATUSES",
    "SETUP_COLUMNS",
    "apply_lifecycle",
    "assemble_setup",
    "build_setup_record",
    "read_setups",
    "resolve_active",
    "resolve_pending",
    "run_engine_once",
    "setup_store_path",
    "setup_store_root",
    "upsert_setups",
]
