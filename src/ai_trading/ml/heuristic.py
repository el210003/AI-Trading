"""Deterministic non-ML heuristic bootstrap (Pattern 6, AI-02 thin-data coverage).

Provides a pure, deterministic ``heuristic_score`` over the SAME FEATURE_SPEC
feature vector the ML path consumes, so a candidate row in a skipped or
starved walk-forward window is still scored (D-02: no information lost), but
carries ``score_source="heuristic"`` and is structurally barred from the ML
headline metrics (AUC / log-loss / Brier / reliability — Pattern 6). Quality
criteria are deliberately deferred to Phase 5/6 feedback (Research Open
Question 3): this module pins only determinism, the [0,1] range, missing
safety, and spec-keyed weights.

``WEIGHTS`` is a module-level dict keyed by a fixed subset of FEATURE_SPEC
numeric feature names, each with a hand-set float weight and a one-line
rationale. ``normalize(value, feature_name)`` maps one feature value to a
"goodness" scalar in [0,1] (smaller-is-better terms — recency, risk, regime —
are INVERTED so a smaller raw value maps closer to 1; a missing value maps to
0). ``heuristic_score`` vectorizes that mapping over a frame with pandas/numpy
ops (no per-row Python loop) and returns the logistic of the weighted-normalized
sum, clipped to [0,1].

HEURISTIC_VERSION is tied to the config's ``ml_feature_list_version`` (and
``ml.features.FEATURE_LIST_VERSION``): when the feature list evolves, bump this
version together with the config knob so a heuristic produced under one feature
set is never confused with another.

The module never reads label-side columns (it consumes the same feature frame
the ML path consumes) and never performs file I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Version tag for the heuristic weighting scheme. Must move in lockstep with
#: ``ml_feature_list_version`` / ``ml.features.FEATURE_LIST_VERSION``.
HEURISTIC_VERSION = 1

#: Feature names whose raw value is "smaller is better" (recency, risk, regime)
#: — inverted by ``normalize`` so a smaller raw value maps closer to 1.
_INVERSE_NAMES = frozenset({"bars_since_sweep", "atr14", "sl_dist_atr"})

#: Hand-set weights keyed by a fixed subset of FEATURE_SPEC numeric names. Each
#: weight multiplies a normalized "goodness" in [0,1]; all weights are positive
#: (inversion already encodes the sign for the smaller-is-better terms).
WEIGHTS: dict[str, float] = {
    # Reward/risk ratio at the decision close — higher structural R:R is more
    # favorable for a setup, so the weight is positive on the goodness.
    "rr_at_decision": 1.0,
    # Position within the tapped zone — deeper toward the favorable side is a
    # better location.
    "zone_position": 0.6,
    # Number of H1/H4 legs leaning the trade (0/1/2) — stronger HTF confluence.
    "htf_bias_agreement": 1.2,
    # Sweep recency (inverted) — a fresher sweep signals a stronger
    # liquidity-grab.
    "bars_since_sweep": 0.5,
    # Regime term (inverted ATR) — a calmer market makes the setup cleaner.
    "atr14": 0.25,
    # SL distance in ATR (inverted) — a tighter stop is more capital-efficient.
    "sl_dist_atr": 0.4,
}

#: Per-feature "goodness" scale factors used by ``heuristic_score``.
_goodness_upper = {"rr_at_decision": 2.0, "htf_bias_agreement": 2.0}


def normalize(value, feature_name: str) -> float:
    """Map a single feature ``value`` to a "goodness" scalar in [0, 1].

    Missing (NaN/None) values map to 0.0. Smaller-is-better terms are inverted
    so a smaller raw value maps closer to 1; every other term is clipped to its
    positive range. The mapping is deterministic and documented per feature.
    """
    if value is None or pd.isna(value):
        return 0.0
    v = float(value)
    if feature_name in _INVERSE_NAMES:
        # Inverted: smaller raw value -> goodness closer to 1 (floor at 0).
        return 1.0 / (1.0 + max(v, 0.0))
    if feature_name in _goodness_upper:
        upper = _goodness_upper[feature_name]
        return min(max(v, 0.0), upper) / upper
    # Default (zone_position, unit-scale larger-is-better): clip to [0, 1].
    return min(max(v, 0.0), 1.0)


def _goodness_vector(col: pd.Series, feature_name: str) -> pd.Series:
    """Vectorized ``normalize`` over a Series; missing values map to 0.0."""
    v = pd.to_numeric(col, errors="coerce")
    notna = v.notna()
    if feature_name in _INVERSE_NAMES:
        g = 1.0 / (1.0 + v.clip(lower=0.0))
    elif feature_name in _goodness_upper:
        upper = _goodness_upper[feature_name]
        g = v.clip(lower=0.0, upper=upper) / upper
    else:
        g = v.clip(lower=0.0, upper=1.0)
    return g.where(notna, 0.0)


def heuristic_score(features: pd.DataFrame) -> pd.Series:
    """Return a deterministic P(WIN)-style bootstrap in [0, 1] per row.

    Computes the logistic of the weighted normalized-goodness sum over the
    ``WEIGHTS`` keys present in ``features``; missing numeric features
    contribute exactly zero. Vectorized over rows (pandas/numpy only — no
    per-row Python loop). The frame is consumed read-only (never mutated); the
    module never reads label-side columns.
    """
    total = pd.Series(0.0, index=features.index, dtype="float64")
    for name, weight in WEIGHTS.items():
        if name not in features.columns:
            continue
        g = _goodness_vector(features[name], name)
        total = total + float(weight) * g

    z = total.to_numpy(dtype="float64")
    z = np.clip(z, -500.0, 500.0)
    raw = 1.0 / (1.0 + np.exp(-z))
    return pd.Series(raw, index=features.index, dtype="float64")
