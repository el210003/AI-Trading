"""Loadable, MT5-free scorer for the versioned artifact (SC4, Phase-6 seam).

``load_scorer`` accepts either:
- a models root containing ``LATEST.json`` (the pointer's ``path`` is resolved),
  or
- a ``v{N}`` version directory containing ``model.joblib``.

It delegates integrity validation to ``ml.artifact.load_artifact`` (schema
version, feature-list version, library-major checks) and returns a ``Scorer``
that exposes the two surface Phase 6 consumes:

- ``score(features)`` -> ``{p_win, score_source='ml', artifact_version}`` —
  reindexes the input frame to the bundle's ordered ``feature_names`` (missing
  columns raise naming them), restores the training ``pd.CategoricalDtype``
  from ``categorical_specs`` (Pitfall 7: LightGBM aligns categories via the
  categorical dtype; unseen categories become missing — logged as a warning),
  then returns ``predict_proba[:, 1]``.
- ``contributors(features)`` -> per-row per-feature contributions via the raw
  boosting model's ``pred_contrib=True`` (shape ``(n_rows, n_features + 1)``,
  last column ``bias``). This is the RAW-MODEL contribution space (TreeSHAP on
  the uncalibrated logit), deliberately paired with the calibrated ``p_win``
  headline (A6) — convolution between the two scales is documented, not hidden.

The raw booster is reached through the fitted calibrator's first
``calibrated_classifiers_`` entry (``ensemble=True`` averages the calibrated
per-fold models for the headline ``p_win``; contributors come from the single
representative raw model for attribution). MT5-free; the only I/O is the
artifact read the loader performs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd

from ai_trading.ml.artifact import load_artifact

log = logging.getLogger(__name__)


def _version_from_path(directory: Path) -> int | None:
    """Derive the artifact version from a ``v{N}`` directory segment."""
    m = re.search(r"[vV](\d+)$", str(directory))
    return int(m.group(1)) if m else None


def _resolve_artifact_path(models_root_or_path) -> tuple[Path, int | None]:
    """Resolve the input (root / version dir / joblib path) to a ``model.joblib``
    path plus a best-effort artifact version from any available source."""
    path = Path(models_root_or_path)
    if path.is_dir():
        latest = path / "LATEST.json"
        if latest.exists():
            pointer = json.loads(latest.read_text(encoding="utf-8"))
            return Path(pointer["path"]) / "model.joblib", pointer.get("artifact_version")
        if (path / "model.joblib").exists():
            return path / "model.joblib", None
        raise ValueError(
            f"models root {path} contains neither LATEST.json nor model.joblib"
        )
    if path.name == "model.joblib":
        return path, None
    raise ValueError(
        f"load_scorer expects a models root with LATEST.json, a v{{N}} directory "
        f"with model.joblib, or a model.joblib path; got {path}"
    )


class Scorer:
    """Loadable scorer bound to one validated artifact bundle."""

    def __init__(self, bundle: dict, artifact_version: int | None):
        self.bundle = bundle
        self.artifact_version = artifact_version
        self._cat_dtypes = {
            name: pd.CategoricalDtype(categories=list(cats))
            for name, cats in bundle["categorical_specs"].items()
        }
        self._cat_sets = {
            name: set(cats) for name, cats in bundle["categorical_specs"].items()
        }

    def _prepare(self, features: pd.DataFrame) -> pd.DataFrame:
        """Reindex to ``feature_names`` order and restore training categorical
        dtypes (Pitfall 7). Missing feature columns raise naming them."""
        frame = features.copy()
        missing = [c for c in self.bundle["feature_names"] if c not in frame.columns]
        if missing:
            raise ValueError(f"features is missing required columns: {missing}")
        frame = frame[self.bundle["feature_names"]]
        for name, dtype in self._cat_dtypes.items():
            col = frame[name]
            present = col.dropna()
            if len(present):
                unseen = present.astype(str)[~present.astype(str).isin(self._cat_sets[name])]
                if len(unseen):
                    log.warning(
                        "unseen category value(s) in column %r: %s — they become "
                        "missing (LightGBM native handling)",
                        name,
                        sorted(set(unseen))[:5],
                    )
            # Restore the training CategoricalDtype. Unseen values are converted
            # EXPLICITLY to missing first so pandas never sees off-dtype values
            # (the deprecated dtype-and-foreign-values path that will raise).
            cleaned = col.mask(~col.astype(str).isin(self._cat_sets[name]))
            frame[name] = pd.Categorical(cleaned.to_numpy(), categories=dtype.categories)
        return frame

    def score(self, features: pd.DataFrame) -> pd.DataFrame:
        """Return per-row calibrated P(WIN) with provenance columns."""
        frame = self._prepare(features)
        p = self.bundle["model"].predict_proba(frame)[:, 1]
        return pd.DataFrame(
            {
                "p_win": pd.Series(p, dtype="float64"),
                "score_source": "ml",
                "artifact_version": self.artifact_version,
            }
        )

    def contributors(self, features: pd.DataFrame) -> pd.DataFrame:
        """Per-row per-feature attribution via ``pred_contrib`` (raw-model space).

        Shape ``(n_rows, n_features + 1)``; columns are ``feature_names`` plus a
        trailing ``bias`` column. Deterministic across calls.
        """
        frame = self._prepare(features)
        booster = self.bundle["model"].calibrated_classifiers_[0].estimator.booster_
        contrib = booster.predict(frame, pred_contrib=True)
        columns = list(self.bundle["feature_names"]) + ["bias"]
        return pd.DataFrame(contrib, columns=columns)


def load_scorer(models_root_or_path) -> Scorer:
    """Validate and load a ``Scorer`` from a models root / version dir / file.

    Delegates bundle validation to ``ml.artifact.load_artifact``. The artifact
    version comes from the bundle's ``artifact_version`` field (stamped by
    ``save_artifact``); it falls back to the resolved ``v{N}`` directory
    segment / LATEST.json pointer when the field is absent.
    """
    model_path, pointer_version = _resolve_artifact_path(models_root_or_path)
    bundle = load_artifact(model_path)
    version = bundle.get("artifact_version")
    if version is None:
        version = pointer_version
    if version is None:
        version = _version_from_path(model_path.parent)
    return Scorer(bundle, version)
