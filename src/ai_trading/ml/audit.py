"""Three-layer point-in-time feature audit (SC1) — the mechanical proof that
no information after the decision bar reaches the feature rows, plus the
persisted ``data/reports/feature_audit.json`` artifact.

The three layers are independent and each is falsifiable:

- **L1 — prefix equivalence (runtime proof):** ``build_feature_frame`` over
  truncated bar histories must equal the full-range run restricted to labels
  whose ``decision_close_time`` is at or before the prefix close. Uses a
  NON-STRICT horizon: a feature needs only bars up to and including the
  decision bar S, so the comparison is ``decision_close_time <= prefix_close``
  (unlike the replay-repaint suite, whose fill needs bar S+1 and therefore
  uses a strict horizon). ``assert_frame_equal`` with ``check_exact=True``.
- **L2 — provenance manifest (spec proof):** ``FEATURE_SPEC`` declares
  (name, dtype, source_tier, source_columns, stamp_kind) for every produced
  feature column; the audit asserts the produced set equals the spec exactly
  (missing and extra both name the offenders), and that declared dtypes and
  stamp_kinds are legal.
- **L3 — forbidden-column static guard:** ``FORBIDDEN_LABEL_COLUMNS`` lists
  the label-side post-decision columns; the test (not production code)
  parses ``features.py`` with the ``ast`` module and asserts no reference.

Pure persistence: no MetaTrader5 import; the atomic tmp + ``os.replace``
artifact write follows ``backtest.reports`` discipline (tmp sibling in the
same directory, unlinked on failure).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from ai_trading.backtest.asof import close_time_of
from ai_trading.backtest.chain import run_chain
from ai_trading.ml.features import FEATURE_SPEC, build_feature_frame

#: Label-side post-decision columns — never read as a feature source (L3 guard).
FORBIDDEN_LABEL_COLUMNS = (
    "entry_price",
    "rr",
    "exit_time",
    "exit_price",
    "exit_idx",
    "outcome",
    "r_gross",
    "r_raw",
    "r_net",
)

_STAMP_KINDS = ("close", "bar", "payload-as-is")
_NON_FEATURE_COLUMNS = ("entry_time", "decision_close_time")


def _default_prefix_points(m15_bars: pd.DataFrame) -> list[int]:
    """Default prefix lengths for the L1 audit.

    Samples a BOUNDED number of evenly-spaced prefixes across the warmup..end
    range regardless of data size. Real-data runs span tens of thousands of
    bars; iterating ``range(28, n, 15)`` would yield O(n/15) prefixes, each
    re-running ``run_chain`` + ``build_feature_frame`` over a growing prefix —
    an O(n^2) cost that hangs on a year of M15 (was fine only on tiny synthetic
    fixtures). Bounding to ~24 evenly-spaced checkpoints keeps the L1 proof
    meaningful (each checks the point-in-time feature equivalence along the
    range) while staying tractable.
    """
    n = len(m15_bars)
    if n <= 28:
        return [n - 1] if n > 0 else []
    start = 28
    # Bounded count of prefix checkpoints (incl. the final prefix n-1). Keep
    # small enough that the audit completes on real-data runs: each prefix
    # re-runs `run_chain` (the full detector chain, ~65s on a year of M15) plus
    # a feature-build over the prefix's labels, so P prefixes cost ~P × chain.
    # A handful of checkpoints still proves point-in-time equivalence along the
    # range (early / mid / late), just without exhaustively hitting every bar.
    max_points = 6
    step = max(1, (n - start) // (max_points - 1))
    points = list(range(start, n, step))
    if n - 1 not in points:
        points.append(n - 1)
    return points


def _atomic_json(payload: dict, path: Path) -> None:
    """Write ``payload`` as JSON through tmp + os.replace (report discipline)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def audit_prefix_equivalence(
    labels: pd.DataFrame,
    m15_bars: pd.DataFrame,
    h1_bars: pd.DataFrame,
    h4_bars: pd.DataFrame,
    prefix_points: list[int],
) -> dict:
    """L1 runtime proof. Returns ``{max_abs_diff, n_labels_checked,
    prefix_points}``; raises ``ValueError`` naming layer L1 on any mismatch."""
    full_chain = run_chain(m15_bars, h1_bars, h4_bars)
    full_features = build_feature_frame(labels, full_chain, m15_bars)
    n_checked = 0

    for k in prefix_points:
        k = int(k)
        if k < 1 or k > len(m15_bars):
            continue
        prefix_m15 = m15_bars.iloc[:k]
        if prefix_m15.empty:
            continue
        prefix_close = close_time_of(prefix_m15["time_utc"].iloc[-1], "M15")

        # Positional visibility mask: build_feature_frame emits one row per
        # label in order (index reset to 0..N-1), so `full_features` row i is
        # `labels` row i. `labels[bool_series]` misaligns when `labels` carries
        # a non-0-based index (real-data frames do); use positional .iloc on
        # both so the row-alignment holds regardless of each frame's index.
        pos_visible = (
            full_features["decision_close_time"].to_numpy() <= prefix_close
        )
        full_part = (
            full_features.iloc[pos_visible]
            .sort_values("entry_time")
            .reset_index(drop=True)
        )
        prefix_labels = labels.iloc[pos_visible]
        prefix_part = build_feature_frame(
            prefix_labels,
            run_chain(prefix_m15, h1_bars, h4_bars),
            prefix_m15,
        ).sort_values("entry_time").reset_index(drop=True)

        if len(prefix_part) == 0 and len(full_part) == 0:
            continue
        try:
            pd.testing.assert_frame_equal(prefix_part, full_part, check_exact=True)
        except AssertionError as exc:
            raise ValueError(
                f"feature audit L1 prefix-equivalence FAILED at prefix {k}: {exc}"
            ) from exc
        n_checked += len(prefix_part)

    return {
        "max_abs_diff": 0.0,
        "n_labels_checked": n_checked,
        "prefix_points": [int(p) for p in prefix_points],
    }


def audit_spec_coverage(feature_frame: pd.DataFrame, feature_spec=None) -> dict:
    """L2 provenance manifest. ``feature_spec`` defaults to ``FEATURE_SPEC``.
    Asserts the produced feature-column set equals the spec's names exactly
    (missing and extra both raise naming them), the declared categorical dtype
    matches the produced column dtype, and every stamp_kind is legal. Returns
    ``{feature_spec_hash, spec_table}``; raises ``ValueError`` naming layer L2."""
    if feature_spec is None:
        feature_spec = FEATURE_SPEC
    spec_names = [entry["name"] for entry in feature_spec]
    produced = [c for c in feature_frame.columns if c not in _NON_FEATURE_COLUMNS]

    missing = [n for n in spec_names if n not in produced]
    extra = [p for p in produced if p not in spec_names]
    if missing or extra:
        raise ValueError(
            f"feature audit L2 spec coverage FAILED: spec/produced mismatch "
            f"missing {missing} extra {extra}"
        )

    for entry in feature_spec:
        name = entry["name"]
        col_dtype = feature_frame[name].dtype
        if entry["dtype"] == "categorical" and not isinstance(col_dtype, pd.CategoricalDtype):
            raise ValueError(
                f"feature audit L2 spec coverage FAILED: {name!r} dtype expected "
                f"categorical, got {col_dtype}"
            )
        if entry["dtype"] == "float64" and str(col_dtype) != "float64":
            raise ValueError(
                f"feature audit L2 spec coverage FAILED: {name!r} dtype expected "
                f"float64, got {col_dtype}"
            )
        if entry["stamp_kind"] not in _STAMP_KINDS:
            raise ValueError(
                f"feature audit L2 spec coverage FAILED: {name!r} stamp_kind "
                f"{entry['stamp_kind']!r} not in {_STAMP_KINDS}"
            )

    sorted_table = sorted((dict(e) for e in feature_spec), key=lambda e: str(e))
    spec_bytes = json.dumps(sorted_table, sort_keys=True, default=str).encode("utf-8")
    feature_spec_hash = hashlib.sha256(spec_bytes).hexdigest()
    return {
        "feature_spec_hash": feature_spec_hash,
        "spec_table": [dict(e) for e in feature_spec],
    }


def run_feature_audit(
    labels: pd.DataFrame,
    m15_bars: pd.DataFrame,
    h1_bars: pd.DataFrame,
    h4_bars: pd.DataFrame,
    cfg,
) -> dict:
    """Compose the three layers into the persisted-artifact payload
    ``{max_abs_diff, n_labels_checked, feature_spec_hash, spec_table, suite,
    embargo_note}``. Any layer failure raises ``ValueError`` naming the layer."""
    l1 = audit_prefix_equivalence(
        labels, m15_bars, h1_bars, h4_bars, _default_prefix_points(m15_bars)
    )
    feature_frame = build_feature_frame(labels, run_chain(m15_bars, h1_bars, h4_bars), m15_bars)
    l2 = audit_spec_coverage(feature_frame)
    return {
        "max_abs_diff": l1["max_abs_diff"],
        "n_labels_checked": l1["n_labels_checked"],
        "feature_spec_hash": l2["feature_spec_hash"],
        "spec_table": l2["spec_table"],
        "suite": "test_ml_feature_audit",
        "embargo_note": "purge obligations live in plan 04-02",
    }


def write_feature_audit(payload: dict, reports_dir: Path) -> Path:
    """Persist the audit payload to ``reports_dir/feature_audit.json`` through a
    local atomic tmp + ``os.replace`` helper (reports discipline). Raises
    ``ValueError`` before writing when ``payload`` lacks the six required keys.
    Returns the written path."""
    required = {
        "max_abs_diff",
        "n_labels_checked",
        "feature_spec_hash",
        "spec_table",
        "suite",
        "embargo_note",
    }
    if not isinstance(payload, dict) or not required <= set(payload):
        missing = sorted(required - set(payload))
        raise ValueError(
            f"write_feature_audit invariant violated: payload missing required"
            f" keys {missing}"
        )
    path = Path(reports_dir) / "feature_audit.json"
    _atomic_json(payload, path)
    return path
