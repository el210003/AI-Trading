"""Unit tests for the setup persistence store (SETUP-01/02 store contract).

Covers the read-back-missing-file empty-frame contract, the read==written
round-trip, dedup-on-``setup_id`` keep='last', the atomic rewrite leaving no
``.tmp`` behind, and the resolve-under-data-root traversal guard (ASVS V4 /
threat T-06-01).
"""

from __future__ import annotations

import pandas as pd
import pytest
from _setup_fixtures import make_setup_row, setup_cfg

from ai_trading.setup.store import (
    SETUP_COLUMNS,
    read_setups,
    setup_store_path,
    upsert_setups,
)


@pytest.mark.unit
def test_read_missing_file_returns_empty_schema(tmp_path):
    cfg = setup_cfg(bars_dir=tmp_path / "data" / "bars")
    frame = read_setups(cfg)
    assert list(frame.columns) == list(SETUP_COLUMNS)
    assert frame.empty
    # Dtype discipline: string cols StringDtype, ts cols datetime64[us].
    assert frame["symbol"].dtype == pd.StringDtype()
    assert frame["created_at"].dtype == "datetime64[us]"


@pytest.mark.unit
def test_round_trip_read_equals_written(tmp_path):
    cfg = setup_cfg(bars_dir=tmp_path / "data" / "bars")
    row = make_setup_row()
    n = upsert_setups(cfg, row)
    assert n == 1
    pd.testing.assert_frame_equal(read_setups(cfg), row, check_exact=True)


@pytest.mark.unit
def test_upsert_dedup_on_setup_id_keep_last(tmp_path):
    cfg = setup_cfg(bars_dir=tmp_path / "data" / "bars")
    first = make_setup_row(entry=1.10000)
    second = make_setup_row(entry=1.15000)  # same setup_id, newer entry
    n = upsert_setups(cfg, first)
    assert n == 1
    n = upsert_setups(cfg, second)
    assert n == 1
    frame = read_setups(cfg)
    assert len(frame) == 1
    assert float(frame["entry"].iloc[0]) == pytest.approx(1.15000)  # keep=last


@pytest.mark.unit
def test_upsert_keeps_multiple_distinct_setups(tmp_path):
    cfg = setup_cfg(bars_dir=tmp_path / "data" / "bars")
    a = make_setup_row(setup_id="s-0001")
    b = make_setup_row(setup_id="s-0002")
    upsert_setups(cfg, a)
    upsert_setups(cfg, b)
    assert len(read_setups(cfg)) == 2


@pytest.mark.unit
def test_atomic_rewrite_leaves_no_tmp(tmp_path):
    cfg = setup_cfg(bars_dir=tmp_path / "data" / "bars")
    upsert_setups(cfg, make_setup_row())
    path = setup_store_path(cfg)
    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


@pytest.mark.unit
def test_setup_store_path_escape_raises(tmp_path):
    """A derived setup path that resolves outside the data root is refused
    (threat T-06-01). Uses a directory symlink to force the resolution
    mismatch; skips when symlinks are unavailable on the platform."""
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (data_root / "setups").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable on this platform")
    cfg = setup_cfg(bars_dir=data_root / "bars")
    with pytest.raises(ValueError, match="path traversal refused"):
        setup_store_path(cfg)
