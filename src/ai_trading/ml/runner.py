"""Retrain CLI (plan 04-03) — the executable end of Phase 4 (D-05, SC1/SC4).

Wires the complete MT5-free ML chain behind a label-count gate:

    label store (data/labels/*.parquet) -> label-count gate -> feature builder
    (ml.features) + feature audit (ml.audit) -> walk-forward windows
    (backtest.walkforward.build_windows) -> per-window eval (ml.evaluate) ->
    [--train] final calibrated model -> versioned artifact (ml.artifact).

MT5-FREE BY DESIGN: no MetaTrader5 import anywhere — the runner reads stored
Parquet bars via ``bar_store.read_bars`` and labels via ``backtest.reports``
only.

EXIT-CODE CONTRACT (pinned by tests, mirroring the backtest runner):
- 2  config errors: ``load_config`` ValueError (bad --config path / schema),
     and specifying NEITHER --train NOR --eval.
- 1  runtime refusals: label-count gate (starvation / missing class), missing
     or unreadable label store, feature/label schema invariants, final-model
     preflight refusal; the gate message names the observed decided/wins/losses
     counts, ``cfg.ml_min_train_labels``, and the backtest-plus-backfill remedy.
- 0  success — INCLUDING runs where every walk-forward window skips (heuristic
     coverage is a valid outcome, logged as INFO; never escapes the contract).

CLI: `uv run python -m ai_trading.ml --config config.toml --train --write`
(module entry via ml/__main__.py).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ai_trading.backtest.barriers import OUTCOME_LOSS, OUTCOME_TIMEOUT, OUTCOME_WIN
from ai_trading.backtest.chain import run_chain
from ai_trading.backtest.replay import LABEL_COLUMNS
from ai_trading.backtest.walkforward import build_windows
from ai_trading.config import load_config
from ai_trading.ml.artifact import build_bundle, save_artifact
from ai_trading.ml.audit import run_feature_audit, write_feature_audit
from ai_trading.ml.evaluate import run_walkforward_eval
from ai_trading.ml.features import FEATURE_NAMES, FEATURE_SPEC
from ai_trading.ml.folds import calibration_folds
from ai_trading.ml.train import (
    decided_mask,
    fit_calibrated,
    preflight_reason,
    reliability_curve,
)
from ai_trading.stores.bar_store import bar_path, read_bars

log = logging.getLogger(__name__)

_DECIDED = frozenset({OUTCOME_WIN, OUTCOME_LOSS})

_GATE_REMEDY = (
    "complete the Phase 3 backtest run (uv run python -m ai_trading.backtest "
    "over the stored bars) to populate the label store, and deepen stored "
    "history via the Phase 1 collector backfill (requires the MT5 terminal); "
    "the heuristic bootstrap inside eval covers any thin period once the gate "
    "passes on a future store"
)


def _output_dirs(cfg) -> tuple[Path, Path, Path]:
    """(labels_dir, reports_dir, models_dir) derived from the data/ root,
    guarded (ASVS V4 / threat T-04-06): each must resolve under the resolved
    data root ``Path(cfg.bars_dir).parent`` — no traversal, no user-supplied
    filenames."""
    data_root = Path(cfg.bars_dir).parent
    labels_dir = data_root / "labels"
    reports_dir = data_root / "reports"
    models_dir = data_root / "models"
    root_resolved = data_root.resolve()
    for directory in (labels_dir, reports_dir, models_dir):
        resolved = directory.resolve()
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise ValueError(
                f"output directory {resolved} must resolve under the data root "
                f"{root_resolved} (path traversal refused)"
            )
    return labels_dir, reports_dir, models_dir


def _load_label_store(labels_dir: Path) -> pd.DataFrame:
    """Load every ``*.parquet`` under ``labels_dir`` into one frame, validating
    the LABEL_COLUMNS schema per file.

    Raises RuntimeError (exit 1) with the actionable message when the directory
    is missing, contains zero label files, or a file is missing required
    columns.
    """
    labels_dir = Path(labels_dir)
    if not labels_dir.exists():
        raise RuntimeError(
            f"label store not found: {labels_dir} — run the Phase 3 backtest "
            f"(uv run python -m ai_trading.backtest) to populate data/labels/ "
            f"(the MT5 history-backfill is the prerequisite data task); "
            f"{_GATE_REMEDY}"
        )
    files = sorted(labels_dir.glob("*.parquet"))
    if not files:
        raise RuntimeError(
            f"label store is empty: no .parquet files under {labels_dir} — the "
            f"Phase 3 backtest command populates it; {_GATE_REMEDY}"
        )
    frames: list[pd.DataFrame] = []
    for path in files:
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:  # unreadable store -> runtime refusal
            raise RuntimeError(f"label store file unreadable: {path}: {exc}") from exc
        missing = [col for col in LABEL_COLUMNS if col not in frame.columns]
        if missing:
            raise RuntimeError(
                f"label store schema invariant violated in {path}: missing "
                f"required columns {missing}"
            )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _label_gate(labels: pd.DataFrame, cfg) -> None:
    """Label-count gate (D-21 style, D-05): refuse starvation data before any
    feature build or artifact write.

    Refuses (RuntimeError -> exit 1) when decided rows are below
    ``cfg.ml_min_train_labels`` OR a class (WIN/LOSS) is missing, naming the
    observed decided/wins/losses counts, the threshold, and the remedy.
    """
    outcomes = labels["outcome"].astype(str)
    wins = int((outcomes == OUTCOME_WIN).sum())
    losses = int((outcomes == OUTCOME_LOSS).sum())
    timeouts = int((outcomes == OUTCOME_TIMEOUT).sum())
    decided = wins + losses

    if decided < cfg.ml_min_train_labels:
        raise RuntimeError(
            f"label-count gate forbids training on starvation data: observed "
            f"decided={decided} (wins={wins}, losses={losses}, timeouts={timeouts}) "
            f"< ml_min_train_labels={cfg.ml_min_train_labels}. Remedy: {_GATE_REMEDY}"
        )
    if wins == 0 or losses == 0:
        raise RuntimeError(
            f"label-count gate forbids training on a single-class decided set: "
            f"observed decided={decided} wins={wins} losses={losses} — both "
            f"classes are required. Remedy: {_GATE_REMEDY}"
        )


def _symbols_present(labels: pd.DataFrame) -> list[str]:
    return sorted(pd.unique(labels["symbol"].astype(str)).tolist())


def _build_features(
    cfg, combined: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict]]:
    """Build the pooled feature frame aligned to a symbol-grouped label frame.

    Returns ``(labels_aligned, features, bars_by_symbol)`` where
    ``labels_aligned`` row i corresponds to ``features`` row i (the
    ``run_walkforward_eval`` alignment invariant), and ``bars_by_symbol`` holds
    the per-symbol M15/H1/H4 frames for the audit. A symbol present in labels
    without readable bars is a schema invariant (ValueError -> exit 1).
    """
    ordered_labels: list[pd.DataFrame] = []
    ordered_features: list[pd.DataFrame] = []
    bars_by_symbol: dict[str, dict] = {}
    for symbol in _symbols_present(combined):
        m15 = read_bars(bar_path(cfg.bars_dir, symbol, "M15"))
        h1 = read_bars(bar_path(cfg.bars_dir, symbol, "H1"))
        h4 = read_bars(bar_path(cfg.bars_dir, symbol, "H4"))
        bars_by_symbol[symbol] = {"m15": m15, "h1": h1, "h4": h4}
        sym = combined[combined["symbol"].astype(str) == symbol].reset_index(drop=True)
        chain = run_chain(m15, h1, h4)
        feat = _build_symbol_features(sym, chain, m15)
        ordered_labels.append(sym)
        ordered_features.append(feat)
    labels_aligned = pd.concat(ordered_labels, ignore_index=True)
    features = pd.concat(ordered_features, ignore_index=True)
    return labels_aligned, features, bars_by_symbol


def _build_symbol_features(sym_labels, chain, m15):
    from ai_trading.ml.features import build_feature_frame

    return build_feature_frame(sym_labels, chain, m15)


def _run_audit(cfg, labels_aligned, bars_by_symbol) -> dict:
    """Per-symbol feature audit aggregated into one payload (SC1). The audit
    runs on every training run before the artifact/report writes."""
    payloads = []
    for symbol, bars in bars_by_symbol.items():
        sym = labels_aligned[labels_aligned["symbol"].astype(str) == symbol]
        payloads.append(
            run_feature_audit(sym, bars["m15"], bars["h1"], bars["h4"], cfg)
        )
    merged = dict(payloads[0])
    merged["max_abs_diff"] = max(p["max_abs_diff"] for p in payloads)
    merged["n_labels_checked"] = sum(p["n_labels_checked"] for p in payloads)
    return merged


def _train_final(cfg, labels_aligned, features, models_dir) -> int:
    """Build the whole-store decided-only training set, derive final
    calibration folds, re-run the preflight (refuse exit 1 on failure),
    fit + calibrate, and save the versioned artifact (SC4).

    Returns the saved artifact version number.
    """
    decided_pos = np.flatnonzero(decided_mask(labels_aligned["outcome"]).to_numpy())
    entry = labels_aligned["entry_time"].iloc[decided_pos].reset_index(drop=True)
    exit_t = labels_aligned["exit_time"].iloc[decided_pos].reset_index(drop=True)
    final_folds = calibration_folds(
        entry, exit_t, cfg.ml_cal_test_days, cfg.ml_cal_train_days, cfg.ml_embargo_bars
    )
    y_final = pd.Series(
        (labels_aligned["outcome"].iloc[decided_pos].astype(str) == OUTCOME_WIN)
        .astype("int64")
        .to_numpy()
    ).reset_index(drop=True)
    reason = preflight_reason(y_final, cfg.ml_min_train_labels, final_folds)
    if reason is not None:
        raise RuntimeError(
            f"final-model preflight refused: {reason}. Remedy: {_GATE_REMEDY}"
        )

    X_final = features.iloc[decided_pos][list(FEATURE_NAMES)].reset_index(drop=True)
    for name in _categorical_names():
        X_final[name] = X_final[name].astype("category")
    calibrated = fit_calibrated(X_final, y_final, final_folds, cfg.ml_calibration_method, cfg)

    p_final = calibrated.predict_proba(X_final)[:, 1]
    rel = reliability_curve(y_final, pd.Series(p_final))
    reliability_summary = {
        "bins": int(len(rel)),
        "n_points": int(len(y_final)),
    }

    categorical_specs = {
        name: list(X_final[name].cat.categories) for name in _categorical_names()
    }
    label_counts = _label_counts(labels_aligned)
    training_window = {
        "start": str(labels_aligned["entry_time"].min()),
        "end": str(labels_aligned["entry_time"].max()),
    }
    bundle = build_bundle(
        model=calibrated,
        cfg=cfg,
        feature_names=list(FEATURE_NAMES),
        categorical_specs=categorical_specs,
        cv_fold_summary={"n_folds": len(final_folds), "method": cfg.ml_calibration_method},
        training_window=training_window,
        label_counts=label_counts,
        reliability_summary=reliability_summary,
    )
    vdir = save_artifact(bundle, models_dir)
    return int(vdir.name[1:])


def _categorical_names() -> list[str]:
    return [e["name"] for e in FEATURE_SPEC if e["dtype"] == "categorical"]


def _label_counts(labels: pd.DataFrame) -> dict:
    outcomes = labels["outcome"].astype(str)
    wins = int((outcomes == OUTCOME_WIN).sum())
    losses = int((outcomes == OUTCOME_LOSS).sum())
    timeouts = int((outcomes == OUTCOME_TIMEOUT).sum())
    return {"decided": wins + losses, "wins": wins, "losses": losses, "timeouts": timeouts}


def _atomic_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write a parquet frame through tmp + ``os.replace`` (reports discipline).

    ``entry_time``/``exit_time``/feature columns are data columns, not run
    metadata, so deterministic filenames + the frame's own row order carry the
    determinism contract; no run id or created_at is ever embedded.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
        import os as _os

        _os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _write_reports(eval_result, reports_dir: Path) -> list[Path]:
    """Persist the three ML report parquets (atomic, deterministic filenames)."""
    written: list[Path] = []
    for filename, frame in (
        ("ml_walkforward.parquet", eval_result.report),
        ("ml_reliability.parquet", eval_result.reliability),
        ("ml_scores.parquet", eval_result.scores),
    ):
        path = Path(reports_dir) / filename
        _atomic_parquet(frame, path)
        written.append(path)
    return written


def run_ml_pipeline(cfg, mode: str, write: bool) -> dict:
    """Run the ML pipeline for ``mode`` ('train' or 'eval') and return a result
    dict with the processed labels/features/windows, the EvalResult, the audit
    payload, and (on --train) the saved artifact version. ``write`` controls
    whether the audit/report artifacts are persisted.
    """
    labels_dir, reports_dir, models_dir = _output_dirs(cfg)
    combined = _load_label_store(labels_dir)
    _label_gate(combined, cfg)
    labels_aligned, features, bars_by_symbol = _build_features(cfg, combined)
    audit_payload = _run_audit(cfg, labels_aligned, bars_by_symbol)
    windows = build_windows(labels_aligned["entry_time"], cfg.wf_test_days, cfg.wf_train_days)
    eval_result = run_walkforward_eval(labels_aligned, features, windows, cfg)

    artifact_version: int | None = None
    if mode == "train" and write:
        artifact_version = _train_final(cfg, labels_aligned, features, models_dir)

    written: list[Path] = []
    if write:
        written.extend(_write_reports(eval_result, reports_dir))
        written.append(write_feature_audit(audit_payload, reports_dir))

    return {
        "labels": labels_aligned,
        "features": features,
        "windows": windows,
        "eval": eval_result,
        "audit": audit_payload,
        "reports_dir": reports_dir,
        "models_dir": models_dir,
        "written": written,
        "artifact_version": artifact_version,
        "mode": mode,
    }


def _fmt(value: object) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else str(value)


def _summary_block(result: dict, cfg) -> str:
    eval_result = result["eval"]
    report = eval_result.report
    n_ok = int((report["status"] == "ok").sum()) if len(report) else 0
    n_skipped = int((report["status"] == "skipped").sum()) if len(report) else 0
    scores = eval_result.scores
    n_decided = int((~scores["excluded"]).sum()) if len(scores) else 0
    n_timeout = int(scores["excluded"].sum()) if len(scores) else 0
    sources = scores["score_source"].value_counts().to_dict() if len(scores) else {}

    lines = [
        "ml pipeline summary",
        f"  symbols: {', '.join(_symbols_present(result['labels']))}",
        (
            f"  labels: decided={n_decided} timeout={n_timeout} "
            f"sources={sources}"
        ),
        f"  windows: trained={n_ok} skipped={n_skipped}",
    ]
    for row in report.to_dict("records"):
        if row["status"] == "skipped":
            lines.append(f"    window {row['window_id']}: skipped ({row['reason']})")
        else:
            lines.append(
                f"    window {row['window_id']}: ok "
                f"auc={_fmt(row['auc'])} log_loss={_fmt(row['log_loss'])} "
                f"brier={_fmt(row['brier'])}"
            )
    if result["artifact_version"] is not None:
        lines.append(f"  artifact: v{result['artifact_version']} saved")
    else:
        lines.append("  artifact: eval-only (no bundle saved)")
    if result["written"]:
        lines.append("  artifacts written:")
        lines.extend(f"    {path}" for path in result["written"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """ML retrain CLI: `uv run python -m ai_trading.ml [options]`.

    Exit codes: 2 config error (bad --config / no mode flag), 1 runtime refusal
    (label-count gate, missing/unreadable label store, schema invariant,
    final-model preflight), 0 success (including all-windows-skipped). See the
    module docstring for the full contract.
    """
    parser = argparse.ArgumentParser(
        prog="ai_trading.ml",
        description=(
            "MT5-free ML retrain runner: label gate -> features + audit -> "
            "walk-forward eval -> [--train] versioned artifact."
        ),
    )
    parser.add_argument(
        "--config", default="config.toml", help="path to config.toml (default: %(default)s)"
    )
    parser.add_argument("--train", action="store_true", help="save a versioned artifact")
    parser.add_argument(
        "--eval", action="store_true", help="walk-forward eval reports without saving an artifact"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "persist artifacts under data/reports/ (+ data/models/ on --train); "
            "dry-run summary when absent"
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if not args.train and not args.eval:
        log.error(
            "no mode selected: specify --train (full pipeline ending in a saved "
            "versioned artifact) or --eval (walk-forward reports only)"
        )
        return 2

    try:
        cfg = load_config(Path(args.config))
    except ValueError as exc:
        log.error("invalid configuration: %s", exc)
        return 2

    mode = "train" if args.train else "eval"
    try:
        result = run_ml_pipeline(cfg, mode, write=args.write)
    except (RuntimeError, ValueError) as exc:
        log.error("%s", exc)
        return 1

    print(_summary_block(result, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
