"""Versioned artifact bundle: build / atomic save / load validation (SC4).

One bundle per artifact version under ``data/models/pooled/v{N}/``:
``model.joblib`` (the fitted calibrator plus every SC4 metadata key),
``manifest.json`` (same metadata as JSON-scalar-only, no pickle — human
readable and greppable), and ``data/models/LATEST.json`` (a pointer
``{artifact_version, path, config_hash}`` for the loader's convenience).

INTEGRITY CONTRACT (module docstring): model bundles are NOT held to
byte-determinism — pickle framing may differ between runs and Python
versions. Determinism is pinned at TWO levels instead:
- the probability level (retraining with identical inputs/seeds reproduces
  byte-identical ``predict_proba``; pinned by the training tests), and
- the manifest level (same config hash -> same metadata).
The loader refuses any bundle whose ``artifact_schema_version`` or
``feature_list_version`` does not match the importing module's current
constants, names expected vs found, and refuses a recorded sklearn/lightgbm
MAJOR that differs from the installed one (warns on a same-major minor
mismatch). This is the pickle-deserialization trust gate: only this repo's
own runs are trusted (ASVS V8 / threat T-04-01); a version mismatch at any
layer is a refuse, not a load.

Path safety: every path is built by the caller from a supplied ``models_dir``
under the project data root; files are written through tmp + ``os.replace``
(the reports.py discipline) so no partially-written artifact is ever observed
and no ``.tmp`` sibling survives a success.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import lightgbm
import pandas as pd
import sklearn

from ai_trading.backtest.reports import config_hash
from ai_trading.ml.features import FEATURE_LIST_VERSION

log = logging.getLogger(__name__)

#: Bump when the bundle layout changes irreconcilably (schema-lock version).
ARTIFACT_SCHEMA_VERSION = 1

#: Every key a valid bundle must carry (``artifact_version`` is stamped by
#: ``save_artifact`` and is NOT required at load so a loader can also be fed a
#: raw ``build_bundle`` dict for testing/alternate storage).
REQUIRED_BUNDLE_KEYS = (
    "artifact_schema_version",
    "feature_names",
    "categorical_specs",
    "feature_list_version",
    "model",
    "method",
    "cv_fold_summary",
    "seeds",
    "config_hash",
    "training_window",
    "label_counts",
    "reliability_summary",
    "sklearn_version",
    "lightgbm_version",
    "created_at",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_safe(value: Any) -> Any:
    """JSON-safe scalar: pd.Timestamp -> ISO string; NaN/inf -> None (strict
    JSON); numpy/pd scalars -> python natives; dict/list recurse; exotic
    values fall back to str. Mirrors backtest.reports._json_safe plus the
    timestamp case needed by the manifest's training_window."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return value
    if hasattr(value, "item"):  # numpy scalars
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    """Write through a ``.tmp`` sibling then ``os.replace`` (atomic on the same
    volume); the tmp file is unlinked even when the write fails."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write_fn(tmp)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _write_json(obj: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)


def build_bundle(
    model,
    cfg,
    feature_names: list[str],
    categorical_specs: dict,
    cv_fold_summary,
    training_window: dict,
    label_counts: dict,
    reliability_summary: dict | None = None,
) -> dict:
    """Assemble the SC4 bundle dict carrying model + feature metadata.

    ``feature_names`` is the ordered FEATURE_SPEC name list; ``categorical_specs``
    is ``{name: [ordered categories]}``; ``training_window`` is ``{start, end}``;
    ``label_counts`` is ``{decided, wins, losses, timeouts}``; ``reliability_summary``
    is the pooled calibration-curve statistics dict (empty when reliability
    cannot be computed — SC2 retention alongside the per-window reliability rows
    the runner persists). The fitted ``model`` is the ``CalibratedClassifierCV``.
    """
    return {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "feature_names": list(feature_names),
        "categorical_specs": dict(categorical_specs),
        "feature_list_version": cfg.ml_feature_list_version,
        "model": model,
        "method": cfg.ml_calibration_method,
        "cv_fold_summary": cv_fold_summary,
        "seeds": cfg.ml_random_state,
        "config_hash": config_hash(cfg),
        "training_window": dict(training_window),
        "label_counts": dict(label_counts),
        "reliability_summary": dict(reliability_summary) if reliability_summary else {},
        "sklearn_version": sklearn.__version__,
        "lightgbm_version": lightgbm.__version__,
        "created_at": _now_iso(),
    }


def _next_version(models_dir: Path) -> int:
    """One plus the max existing ``v{N}`` directory under ``models_dir/pooled``
    (1 when none exists)."""
    pooled = Path(models_dir) / "pooled"
    if not pooled.exists():
        return 1
    numbers = []
    for child in pooled.iterdir():
        if child.is_dir() and child.name.startswith("v"):
            try:
                numbers.append(int(child.name[1:]))
            except ValueError:
                continue
    return max(numbers) + 1 if numbers else 1


def save_artifact(bundle: dict, models_dir) -> Path:
    """Persist a bundle under ``models_dir/pooled/v{N}/`` and update LATEST.json.

    Stamps ``artifact_version = N`` into the bundle BEFORE serialization so the
    loaded Scorer reports it without path parsing; writes ``model.joblib``
    (atomic tmp + ``os.replace``), then ``manifest.json`` (JSON-scalar-only,
    no pickle), then ``models_dir/LATEST.json`` — the pointer is written only
    after the version directory is complete. Returns the version directory path.
    """
    models_dir = Path(models_dir)
    n = _next_version(models_dir)
    vdir = models_dir / "pooled" / f"v{n}"
    vdir.mkdir(parents=True, exist_ok=True)

    stamped = dict(bundle)
    stamped["artifact_version"] = n

    model_path = vdir / "model.joblib"
    _atomic_write(model_path, lambda tmp: joblib.dump(stamped, tmp))

    manifest_path = vdir / "manifest.json"
    payload = {k: _json_safe(v) for k, v in stamped.items() if k != "model"}
    _atomic_write(manifest_path, lambda tmp: _write_json(payload, tmp))

    latest_path = models_dir / "LATEST.json"
    pointer = {
        "artifact_version": n,
        "path": str(vdir),
        "config_hash": stamped["config_hash"],
    }
    _atomic_write(latest_path, lambda tmp: _write_json(pointer, tmp))

    return vdir


def _validate_library_version(installed: str, recorded: str, name: str) -> None:
    """Refuse a recorded MAJOR differing from the installed one; warn on a
    same-major minor/patch mismatch."""
    inst_major = int(installed.split(".")[0])
    rec_major = int(recorded.split(".")[0])
    if inst_major != rec_major:
        raise ValueError(
            f"{name} major version mismatch: bundle was recorded under "
            f"{recorded!r} but installed is {installed!r} — refusing the load "
            "(major library differences can silently change predictions)"
        )
    if installed != recorded:
        log.warning(
            "%s version differs from the bundle's recorded version "
            "(recorded %r, installed %r); same major so continuing",
            name,
            recorded,
            installed,
        )


def load_artifact(path) -> dict:
    """Joblib-load and validate a bundle at ``path``.

    Validates, in order: required bundle keys are present; ``artifact_schema_version``
    matches ``ARTIFACT_SCHEMA_VERSION``; ``feature_list_version`` matches the
    current FEATURE_SPEC version; installed sklearn/lightgbm MAJORS match the
    recorded ones (warn on same-major minor). Every refusal names expected vs
    found. Returns the validated bundle dict.
    """
    bundle = joblib.load(Path(path))
    if not isinstance(bundle, dict):
        raise ValueError("model bundle must be a dict")

    missing = [k for k in REQUIRED_BUNDLE_KEYS if k not in bundle]
    if missing:
        raise ValueError(f"model bundle missing required keys: {missing}")

    found_schema = bundle["artifact_schema_version"]
    if found_schema != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"artifact_schema_version mismatch: bundle has {found_schema!r}, "
            f"expected {ARTIFACT_SCHEMA_VERSION!r}"
        )
    found_flv = bundle["feature_list_version"]
    if found_flv != FEATURE_LIST_VERSION:
        raise ValueError(
            f"feature_list_version mismatch: bundle has {found_flv!r}, "
            f"current FEATURE_SPEC version is {FEATURE_LIST_VERSION!r}"
        )
    _validate_library_version(sklearn.__version__, bundle["sklearn_version"], "scikit-learn")
    _validate_library_version(
        lightgbm.__version__, bundle["lightgbm_version"], "lightgbm"
    )
    return bundle
