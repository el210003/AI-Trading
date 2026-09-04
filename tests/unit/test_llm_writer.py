"""Unit tests for the atomic narrative writer (``write_narratives``).

Pinned tests: a valid write persists the parquet atomically with no ``.tmp``
residue and round-trips; a failed write leaves no partial artifact (path absent,
no ``.tmp``); a missing required column refuses to write naming the column; an
unknown column is rejected naming it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ai_trading.llm.writer import NARRATIVE_COLUMNS, write_narratives


def _narrative_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["EURUSD"],
            "timeframe": ["M15"],
            "direction": ["long"],
            "zone_id": ["z-001"],
            "event_id": ["ev-001"],
            "pool_id": ["p-001"],
            "entry_time": [pd.Timestamp("2026-09-04 00:00:00")],
            "p_win": [0.72],
            "score_source": ["ml_llm"],
            "verdict": ["confirm"],
            "confidence": [0.8],
            "reasoning": ["evidence-grounded"],
            "citations": ["[\"direction\", \"bias_h1\"]"],
            "citation_status": ["verified"],
            "agreement": ["agree"],
            "agreement_confidence": [0.8],
            "narrative_status": ["ok"],
            "reason": [None],
            "artifact_version": [1],
            "created_at": [pd.Timestamp("2026-09-04 00:00:00")],
        }
    )


@pytest.mark.unit
def test_atomic_write_round_trip(tmp_path):
    out = tmp_path / "llm_narratives.parquet"
    write_narratives(_narrative_frame(), out)
    assert out.exists()
    assert not (tmp_path / "llm_narratives.parquet.tmp").exists()
    loaded = pd.read_parquet(out)
    assert len(loaded) == 1
    assert list(loaded.columns) == list(NARRATIVE_COLUMNS)


@pytest.mark.unit
def test_failed_write_leaves_no_partial_artifact(tmp_path, monkeypatch):
    out = tmp_path / "llm_narratives.parquet"

    def fail_replace(src, dst):
        raise OSError("simulated atomic-replace failure")

    monkeypatch.setattr("ai_trading.llm.writer.os.replace", fail_replace)
    with pytest.raises(OSError):
        write_narratives(_narrative_frame(), out)
    assert not out.exists()
    assert not (tmp_path / "llm_narratives.parquet.tmp").exists()


@pytest.mark.unit
def test_missing_required_column_raises(tmp_path):
    df = _narrative_frame().drop(columns=["p_win"])
    with pytest.raises(ValueError) as exc:
        write_narratives(df, tmp_path / "x.parquet")
    assert "p_win" in str(exc.value)


@pytest.mark.unit
def test_unknown_column_rejected(tmp_path):
    df = _narrative_frame()
    df["unexpected"] = 1
    with pytest.raises(ValueError) as exc:
        write_narratives(df, tmp_path / "x.parquet")
    assert "unexpected" in str(exc.value)
