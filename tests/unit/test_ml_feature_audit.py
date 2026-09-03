"""Unit tests for the three-layer point-in-time feature audit (SC1) and the
persisted feature_audit.json artifact writer.

- L1 prefix-equivalence (runtime proof; falsifiable via the leak mutation test)
- L2 spec coverage + provenance manifest
- L3 AST forbidden-column guard + ml/ vendor-purity static check
- run_feature_audit composition + atomic artifact writer

No MetaTrader5 import anywhere.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest
from _ml_fixtures import ml_cfg, sculpted_label_world

from ai_trading.ml.audit import (
    FORBIDDEN_LABEL_COLUMNS,
    audit_prefix_equivalence,
    audit_spec_coverage,
    run_feature_audit,
    write_feature_audit,
)

SRC_ML = Path("src/ai_trading/ml")


@pytest.fixture
def world():
    return sculpted_label_world()


# ---------------------------------------------------------------------------
# L1: prefix equivalence (audit passes on the synthetic world)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_l1_prefix_equivalence_single_and_chunked_appends(world):
    m15, h1, h4, labels = world
    points = list(range(28, 130, 5)) + [len(m15) - 1]
    payload = audit_prefix_equivalence(labels, m15, h1, h4, points)
    assert payload["max_abs_diff"] == 0.0
    assert payload["n_labels_checked"] > 0
    assert payload["prefix_points"] == points


@pytest.mark.unit
def test_l1_prefix_equivalence_one_by_one():
    m15, h1, h4, labels = sculpted_label_world()
    points = list(range(28, min(len(m15), 110)))
    payload = audit_prefix_equivalence(labels, m15, h1, h4, points)
    assert payload["max_abs_diff"] == 0.0
    assert payload["n_labels_checked"] > 0


# ---------------------------------------------------------------------------
# L1 is falsifiable: a builder that reads one bar past the decision index
# must make the audit raise, naming layer L1.
# ---------------------------------------------------------------------------

def _leaky_build_feature_frame(labels, chain, bars):
    """Reimplementation of features.build_feature_frame whose M15 slice for
    each label includes ONE bar past the decision index (the fill bar S+1) —
    a genuine future leak the L1 prefix-equivalence layer must catch."""

    from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask
    from ai_trading.backtest.candidates import CandidateState
    from ai_trading.ml.features import FEATURE_NAMES, features_at_decision

    symbol = labels["symbol"].astype(str).unique()
    assert len(symbol) == 1
    symbol = str(symbol[0])
    times = bars["time_utc"]

    def sym(frame):
        return frame if (frame is None or "symbol" not in frame.columns) else frame[
            frame["symbol"] == symbol
        ]

    events_all = sym(chain.get("events15"))
    zones_all = sym(chain.get("zones15"))
    pools_all = sym(chain.get("pools15"))
    swings_all = sym(chain.get("swings15"))
    payload_all = sym(chain.get("payload"))

    rows = []
    for _, lr in labels.iterrows():
        entry_time = pd.Timestamp(lr["entry_time"])
        fill_pos = int(times.searchsorted(entry_time, side="left"))
        decision_idx = fill_pos - 1
        bar_t = pd.Timestamp(times.iloc[decision_idx])
        close_t = close_time_of(bar_t, "M15")
        # LEAK: slice includes the bar AFTER the decision index.
        m15_slice = bars.iloc[: decision_idx + 2].reset_index(drop=True)
        payload_rows = (
            payload_all[payload_all["time_utc"] == bar_t]
            if payload_all is not None and not payload_all.empty
            else payload_all
        )
        state = CandidateState(
            m15_bars=m15_slice,
            events15=(
                events_all[visible_mask(events_all, "resolved_at", STAMP_BAR, bar_t, close_t)]
                if events_all is not None and not events_all.empty
                else events_all
            ),
            zones15=(
                zones_all[visible_mask(zones_all, "mitigated_at", STAMP_BAR, bar_t, close_t)]
                if zones_all is not None and not zones_all.empty
                else zones_all
            ),
            pools15=(
                pools_all[visible_mask(pools_all, "activated_at", STAMP_CLOSE, bar_t, close_t)]
                if pools_all is not None and not pools_all.empty
                else pools_all
            ),
            swings15=(
                swings_all[visible_mask(swings_all, "confirmed_at", STAMP_CLOSE, bar_t, close_t)]
                if swings_all is not None and not swings_all.empty
                else swings_all
            ),
            payload_row=payload_rows.iloc[0] if len(payload_rows) else None,
        )
        feats = features_at_decision(state, lr, None)
        feats["entry_time"] = entry_time
        feats["decision_close_time"] = close_t
        rows.append(feats)

    frame = pd.DataFrame(rows)
    out = [c for c in list(FEATURE_NAMES) + ["entry_time", "decision_close_time"]]
    return frame[out].reset_index(drop=True)


@pytest.mark.unit
def test_l1_detects_runtime_leak_mutation(world, monkeypatch):
    m15, h1, h4, labels = world
    import ai_trading.ml.audit as audit_mod

    monkeypatch.setattr(audit_mod, "build_feature_frame", _leaky_build_feature_frame)
    points = list(range(40, min(len(m15), 120)))
    with pytest.raises(ValueError, match="L1"):
        audit_prefix_equivalence(labels, m15, h1, h4, points)


# ---------------------------------------------------------------------------
# L2: spec coverage — every produced column declared; checks dtypes + kinds.
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_l2_spec_covers_every_column(world):
    from ai_trading.backtest.chain import run_chain
    from ai_trading.ml.features import build_feature_frame

    m15, h1, h4, labels = world
    chain = run_chain(m15, h1, h4)
    frame = build_feature_frame(labels, chain, m15)
    payload = audit_spec_coverage(frame, None)  # default spec from features module
    assert payload["feature_spec_hash"]
    assert isinstance(payload["spec_table"], list)
    assert len(payload["spec_table"]) == 18


@pytest.mark.unit
def test_l2_missing_column_raises(world):
    from ai_trading.backtest.chain import run_chain
    from ai_trading.ml.features import FEATURE_SPEC, build_feature_frame

    m15, h1, h4, labels = world
    chain = run_chain(m15, h1, h4)
    frame = build_feature_frame(labels, chain, m15)
    mutated = [e for e in FEATURE_SPEC if e["name"] != "rr_at_decision"]
    with pytest.raises(ValueError, match="rr_at_decision"):
        audit_spec_coverage(frame, mutated)


# ---------------------------------------------------------------------------
# L3: AST forbidden-column static guard + ml/ vendor purity
# ---------------------------------------------------------------------------

def _docstring_value_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


def _forbidden_refs(path: Path) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    docstrings = _docstring_value_ids(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            found.add(node.value)
    return found & set(FORBIDDEN_LABEL_COLUMNS)


@pytest.mark.unit
def test_l3_forbidden_columns_absent_from_source():
    features_src = SRC_ML / "features.py"
    offenders = _forbidden_refs(features_src)
    assert offenders == set(), f"features.py references post-decision columns: {offenders}"


@pytest.mark.unit
def test_l3_forbidden_column_access_in_tmp_raises_naming_it(tmp_path):
    tmp = tmp_path / "bad_source.py"
    tmp.write_text(
        "import pandas as pd\n"
        "def f(row):\n"
        "    return row['rr'], row['exit_time'], row['outcome']\n",
        encoding="utf-8",
    )
    offenders = _forbidden_refs(tmp)
    assert {"rr", "exit_time", "outcome"} <= offenders


@pytest.mark.unit
def test_l3_vendor_purity_no_mt5_import():
    """No .py under src/ai_trading/ml/ declares a MetaTrader5 import (module
    docstrings legitimately mention the rule in prose — the check parses import
    statements, not prose)."""
    offenders = []
    for path in SRC_ML.glob("*.py"):
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any("MetaTrader5" in (alias.name or "") for alias in node.names):
                    offenders.append(path.name)
            elif isinstance(node, ast.ImportFrom) and "MetaTrader5" in (node.module or ""):
                offenders.append(path.name)
    assert offenders == [], f"ml/ modules must stay MT5-free: {offenders}"


@pytest.mark.unit
def test_l3_features_purity_of_transform():
    text = (SRC_ML / "features.py").read_text(encoding="utf-8")
    for symbol in ("open(", "to_parquet", "to_csv", "os.replace"):
        assert symbol not in text, f"features.py must be a pure transform (found {symbol})"


# ---------------------------------------------------------------------------
# run_feature_audit composition + atomic artifact writer
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_run_feature_audit_payload_shape(world):
    m15, h1, h4, labels = world
    payload = run_feature_audit(labels, m15, h1, h4, ml_cfg())
    assert payload["max_abs_diff"] == 0.0
    assert payload["n_labels_checked"] > 0
    assert payload["feature_spec_hash"]
    assert isinstance(payload["spec_table"], list)
    assert payload["suite"] == "test_ml_feature_audit"
    assert payload["embargo_note"] == "purge obligations live in plan 04-02"
    # spec hash stable across calls
    again = run_feature_audit(labels, m15, h1, h4, ml_cfg())
    assert payload["feature_spec_hash"] == again["feature_spec_hash"]


@pytest.mark.unit
def test_write_feature_audit_atomic(world, tmp_path):
    m15, h1, h4, labels = world
    payload = run_feature_audit(labels, m15, h1, h4, ml_cfg())
    reports_dir = tmp_path / "reports"
    path = write_feature_audit(payload, reports_dir)
    assert path == reports_dir / "feature_audit.json"
    assert path.exists()
    # no .tmp sibling left behind
    assert not list(reports_dir.glob("*.tmp"))
    # malformed payload raises before writing
    with pytest.raises(ValueError):
        write_feature_audit({"max_abs_diff": 0.0}, reports_dir)
    assert (reports_dir / "feature_audit.json").exists()  # prior write intact
