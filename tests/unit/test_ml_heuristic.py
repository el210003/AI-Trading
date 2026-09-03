"""Unit tests for the deterministic non-ML heuristic bootstrap (Pattern 6,
AI-02 thin-data coverage, Open Question 3).

Named tests pin the Pattern 6 contract and the Open Question 3 acceptance
framing: deterministic same-input -> same-output, [0,1] range over synthetic +
extreme + all-missing frames, missing numeric features contribute EXACTLY zero
(the score equals the logistic of zero = 0.5), monotonicity in ``rr_at_decision``,
every ``WEIGHTS`` key is a FEATURE_SPEC name (keeps the bootstrap honest when the
feature list evolves), and the module is pure (inputs unmutated, no file I/O).

No MetaTrader5 import anywhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from _ml_fixtures import synthetic_feature_frame

from ai_trading.ml.features import FEATURE_SPEC
from ai_trading.ml.heuristic import (
    HEURISTIC_VERSION,
    WEIGHTS,
    heuristic_score,
    normalize,
)

_SPEC_NAMES = {e["name"] for e in FEATURE_SPEC}
_SPEC_NUMERIC_NAMES = {e["name"] for e in FEATURE_SPEC if e["dtype"] == "float64"}


def _frame(n_rows: int = 20, seed: int = 0) -> pd.DataFrame:
    return synthetic_feature_frame(n_rows, seed=seed)


@pytest.mark.unit
def test_heuristic_deterministic_same_input_same_output():
    f = _frame()
    a = heuristic_score(f)
    b = heuristic_score(f)
    np.testing.assert_array_equal(a.to_numpy(), b.to_numpy())


@pytest.mark.unit
def test_heuristic_in_unit_range():
    # Synthetic frame with plausible ranges stays in [0, 1].
    f = _frame(30, seed=1)
    s = heuristic_score(f)
    assert s.dtype == "float64"
    assert bool(((s >= 0) & (s <= 1)).all())

    # Extreme / adversarial values must never escape [0, 1].
    ext = f.copy()
    ext["rr_at_decision"] = [1e9, -1e9, 0.0, 2.5, np.nan] * 6
    ext["zone_position"] = [10.0, -10.0, 0.5, 1.0, np.nan] * 6
    ext["htf_bias_agreement"] = [99.0, -1.0, 0.0, 2.0, np.nan] * 6
    ext["bars_since_sweep"] = [1e9, -5.0, 0.0, 3.0, np.nan] * 6
    ext["atr14"] = [1e9, -2.0, 0.0, 1.0, np.nan] * 6
    ext["sl_dist_atr"] = [1e9, -3.0, 0.5, 2.0, np.nan] * 6
    s2 = heuristic_score(ext)
    assert bool(((s2 >= 0) & (s2 <= 1)).all())


@pytest.mark.unit
def test_heuristic_missing_features_contribute_zero():
    f = _frame(15, seed=2)
    for name in WEIGHTS:
        f[name] = np.nan
    s = heuristic_score(f)
    # All-missing numerics -> weighted-normalized sum 0 -> logistic(0) == 0.5.
    np.testing.assert_allclose(s.to_numpy(), 0.5, atol=1e-12)


@pytest.mark.unit
def test_heuristic_monotone_in_rr():
    base = _frame(20, seed=3)
    hi = base.copy()
    lo = base.copy()
    hi["rr_at_decision"] = base["rr_at_decision"] + 5.0
    lo["rr_at_decision"] = base["rr_at_decision"] - 5.0
    s_lo = heuristic_score(lo)
    s_hi = heuristic_score(hi)
    assert bool((s_hi.to_numpy() >= s_lo.to_numpy() - 1e-12).all())


@pytest.mark.unit
def test_heuristic_weights_subset_of_feature_spec():
    assert WEIGHTS, "WEIGHTS must not be empty"
    for key in WEIGHTS:
        assert key in _SPEC_NAMES, f"{key!r} is not a FEATURE_SPEC name"
        assert key in _SPEC_NUMERIC_NAMES, f"{key!r} is not a numeric FEATURE_SPEC name"


@pytest.mark.unit
def test_heuristic_pure_no_io():
    f = _frame(10, seed=4)
    f_before = f.copy()
    _ = heuristic_score(f)
    pd.testing.assert_frame_equal(f, f_before, check_exact=True)
    # normalize is a pure scalar mapping.
    assert isinstance(normalize(1.5, "rr_at_decision"), float)
    assert isinstance(HEURISTIC_VERSION, int)
