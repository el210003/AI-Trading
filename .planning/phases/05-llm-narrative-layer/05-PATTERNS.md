# Phase 5: LLM Narrative Layer - Pattern Map

**Mapped:** 2026-09-04
**Files classified:** 23 (9 new `src/ai_trading/llm/*`, 10 test files, 4 modified config/package files)
**Analogs found:** 21 / 23 — one greenfield role (no existing string-template prompt module) resolved via RESEARCH.md Pattern + the codebase pure-function convention; one `config.local.toml` is a data file (no source analog, references the established gitignored-override pattern).

> **Reading key:** This is NOT a greenfield phase. The codebase has four mature source tiers — adapter (`mt5_client.py`), pure-transform (`ml/features.py`, `ml/scorer.py`, `backtest/candidates.py`), storage (`backtest/reports.py`, `ml/artifact.py`), and config (`config.py`) — plus a well-established duck-typed fake-test convention (`conftest.py FakeMT5Client`). Every new LLM file copies a concrete, existing pattern below. Distinguish **copy-from** (reuse the pattern nearly verbatim) from **adapt** (same skeleton, different payload/domain).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ai_trading/llm/schema.py` | model (pydantic contract) | transform/validation | `src/ai_trading/ml/artifact.py` (REQUIRED_BUNDLE_KEYS + load validation); `src/ai_trading/ml/features.py` `_CATEGORICAL_CATEGORIES` (pinned enum sets) | role-match |
| `src/ai_trading/llm/provider.py` | adapter/interface | request-response (network) | `src/ai_trading/mt5_client.py` (adapter tier, duck-typed, only module touching the SDK, error taxonomy) | exact |
| `src/ai_trading/llm/evidence.py` | service (pure transform) | transform (data assembly) | `src/ai_trading/ml/features.py` `features_at_decision`/`build_feature_frame` (pure dict-from-State); `src/ai_trading/ml/scorer.py` `score()`/`contributors()` | role-match |
| `src/ai_trading/llm/prompt.py` | utility (pure transform) | transform (string build) | `src/ai_trading/ml/features.py` (pure-function convention) + RESEARCH Pattern (D-03 no-OHLC rule) | partial (no existing string-template module) |
| `src/ai_trading/llm/citations.py` | utility (pure guard/validation) | transform | `src/ai_trading/ml/artifact.py` `_validate_library_version`/`load_artifact` (name-expected-vs-found refuse); `src/ai_trading/ml/features.py` `_validate_bars` + `FORBIDDEN` frozenset convention | role-match |
| `src/ai_trading/llm/agreement.py` | utility (pure function) | transform | `src/ai_trading/backtest/candidates.py` `bias_agrees`/`compute_rr` (pure, NA-safe, cfg-thresholded) | role-match |
| `src/ai_trading/llm/narrative.py` | service (orchestrator) | request-response + graceful fallback | `src/ai_trading/collector.py` (orchestration service, error taxonomy, retry loop) | role-match |
| `src/ai_trading/llm/writer.py` | storage/utility | file-I/O (atomic write) | `src/ai_trading/backtest/reports.py` `_atomic_json`/`_atomic_parquet` + `write_run_manifest` (invariant validation); `src/ai_trading/ml/artifact.py` `_atomic_write`/`_json_safe` | exact |
| `src/ai_trading/llm/__init__.py` | package marker | n/a | `src/ai_trading/ml/__init__.py` (bare marker, import submodules directly) | exact |
| `src/ai_trading/config.py` (MOD) | config loader + validator | transform | **itself** — extend the Phase-4 `ml_*` block (add `llm_*` keys/fields/validation) | exact |
| `pyproject.toml` (MOD) | config (deps, pytest markers) | n/a | **itself** — add `openai` dep + `llm` marker + change `addopts` | exact |
| `config.toml` (MOD) | config (committed defaults) | n/a | **itself** — add `llm_enabled`/`llm_base_url`/`llm_model`/`llm_*` knobs (no secrets) | exact |
| `config.local.toml` (MOD, gitignored) | config (local overrides) | n/a | **itself** — `llm_api_key` only here (ASVS V14) | exact |
| `tests/unit/_llm_fixtures.py` | test fixture (fake provider + cfg) | transform | `tests/conftest.py` `FakeMT5Client` (duck-typed fake, recording + scripted responses/errors); `tests/unit/_backtest_fixtures.py` `bt_cfg` + `tests/unit/_ml_fixtures.py` `ml_cfg` (config constructor) | exact |
| `tests/unit/test_llm_schema.py` | test (unit) | transform | `tests/unit/test_ml_features.py` / `test_ml_artifact.py` (schema/enum validation tests) | role-match |
| `tests/unit/test_llm_provider.py` | test (unit) | request-response | **adapted**: assert `chat.completions.create` called with mapped params via a monkeypatched client (mirror of `conftest.py` recording hooks) | role-match |
| `tests/unit/test_llm_evidence.py` | test (unit) | transform | `tests/unit/test_ml_features.py` (pure transform, no-future-info) | role-match |
| `tests/unit/test_llm_prompt.py` | test (unit) | transform | `tests/unit/test_ml_features.py` (pure transform, forbidden-input guard) | role-match |
| `tests/unit/test_llm_citations.py` | test (unit) | transform | `tests/unit/test_ml_artifact.py` / `test_ml_feature_audit.py` (fail-fast refuse + invariant) | role-match |
| `tests/unit/test_llm_agreement.py` | test (unit) | transform | `tests/unit/test_candidates.py` (pure function thresholds) | role-match |
| `tests/unit/test_llm_fallback.py` | test (unit) | request-response (error path) | `tests/unit/test_health_check.py` / `test_runner.py` (exception path + bounded time) | role-match |
| `tests/unit/test_llm_writer.py` | test (unit) | file-I/O | `tests/unit/test_idempotent_store.py` (atomic write, tmp+os.replace) | role-match |
| `tests/integration/test_llm_live.py` | test (integration, `llm`-marked) | request-response | `tests/integration/test_live_collect.py` (`mt5`-marked opt-in integration) | role-match |

**Provenance of file list:** RESEARCH.md "Recommended Project Structure" (lines 186–210) defines the `src/ai_trading/llm/*` layout and the test modules; RESEARCH.md "Validation Architecture" Wave-0 Gaps (lines 498–503) names the `pyproject.toml` `llm`-marker change, `uv add "openai>=3.8.0"`, and the fixture/test modules; RESEARCH.md Open Question 4 (lines 443–446) and `config.py`'s Phase-4 `ml_*` block define the config knobs.

## Pattern Assignments

### `src/ai_trading/llm/schema.py` (model, transform)

**Analog:** `src/ai_trading/ml/artifact.py` + `src/ai_trading/ml/features.py` — **copy the constants + validation-refuse convention, adapt to pydantic.**

**Enum / pinned-set convention** (copy from `ml/features.py` lines 97–109 — pin the allowed `verdict`/categorical sets the same way `_CATEGORICAL_CATEGORIES` pins feature categories):
```python
# ml/features.py:103-109 (copy the *discipline*: pinned enum sets are a
# module-level constant, never inferred from data)
_CATEGORICAL_CATEGORIES: dict[str, list[str]] = {
    "symbol": ["EURUSD", "GBPUSD", "USDJPY"],
    "timeframe": ["M15", "H1", "H4"],
    "direction": ["long", "short"],
    "bias_h1": ["bullish", "bearish", "neutral"],
    "bias_h4": ["bullish", "bearish", "neutral"],
}
```
Apply the same to schema: `verdict` is `Literal["confirm", "refute"]`, `confidence` is `Annotated[float, Field(ge=0.0, le=1.0)]`, `reasoning: str = Field(min_length=1)`, `citations: list[str]`. Research D-04 contract (RESEARCH.md lines 247–262) gives the model shape verbatim.

**Required-keys / schema-lock convention** (copy from `ml/artifact.py` lines 50–72 — a module constant dict of allowed keys, analog of `REQUIRED_BUNDLE_KEYS` / `FORBIDDEN_LEVEL_KEYS`):
```python
# ml/artifact.py:50-72 — the "schema-lock" constant pattern
ARTIFACT_SCHEMA_VERSION = 1
REQUIRED_BUNDLE_KEYS = ("artifact_schema_version", "feature_names", ...)
```
In `schema.py` this becomes `ALLOWED_CITATION_KEYS` (the real evidence field keys) and `FORBIDDEN_LEVEL_KEYS = {"entry","sl","tp","sl_price","tp_price","entry_price","take_profit","stop_loss"}` (RESEARCH.md line 272) — the D-02 whitelist that drops any level field the LLM emits.

**Oversize guard note:** `ml/artifact.py` `load_artifact` (lines 235–267) is the analogue of "validate and name expected vs found" the citation check must mirror. Keep the schema the single source of truth; expose a `json_schema` builder (via openai `type_to_response_format_param`, RESEARCH.md lines 261–262).

---

### `src/ai_trading/llm/provider.py` (adapter, request-response)

**Analog:** `src/ai_trading/mt5_client.py` — **copy the adapter-tier discipline almost verbatim.**

**"Only module that imports the SDK" rule** (copy `mt5_client.py` lines 1–23 — the openai SDK import lives here and only here, exactly as `import MetaTrader5 as mt5` appears once):
```python
# mt5_client.py:1-23 — module docstring establishes the adapter as the ONLY
# place the SDK is imported; every other module goes through this wrapper.
"""Thin MT5 adapter — the ONLY module in the codebase that imports
MetaTrader5 (exactly once, at module top)..."""
from __future__ import annotations
import MetaTrader5 as mt5
```
For `provider.py`: the openai SDK is imported at module top (`from openai import OpenAI` / lazily in `__init__`), and `provider.py` is the only LLM tier module touching the network.

**Error taxonomy** (copy `mt5_client.py` lines 36–42 — define the LLM-specific exception classes as distinct `RuntimeError` subclasses):
```python
# mt5_client.py:36-42
class MT5ConnectionError(RuntimeError):
    """Connection/health-check failure (terminal state, account, server, symbol)."""
class MT5DataError(RuntimeError):
    """Data-fetch failure (copy_rates_* returned None/empty unexpectedly)."""
```
For `provider.py`: define `LLMProviderError` / `LLMTruncatedError` (RESEARCH.md line 239 raises `LLMTruncatedError` when `content is None` on a reasoning model) mirroring this pattern.

**Duck-typed interface** (the fake lower in the test section implements the same surface — see `FakeMT5Client`). Define `LLMProvider` as a `Protocol` whose method signature the fake reproduces exactly, so tests inject either.

**Constructor / lazy-client convention:** build the `OpenAI` client once (config-driven) per RESEARCH.md line 105 + Commons (lines 347–352):
```python
self._client = OpenAI(
    api_key=cfg.llm_api_key,
    base_url=cfg.llm_base_url,      # http://192.168.5.178:8000/v1
    timeout=cfg.llm_timeout_ms / 1000,
    max_retries=1,
)
```
**Reasoning-model caveat (RESEARCH.md Pitfall 1, lines 310–314):** check `resp.choices[0].message.content`; if `None`, raise `LLMTruncatedError` (retry-once-then-fallback), never parse-crash.

---

### `src/ai_trading/llm/evidence.py` (service, pure transform)

**Analog:** `src/ai_trading/ml/features.py` `features_at_decision` + `build_feature_frame` — **copy the pure function + return-dict convention; adapt to assemble the evidence object from `Scorer` + `CandidateState`.**

**Pure-function signature + docstring + `del cfg` discipline** (copy `features_at_decision` lines 155–170):
```python
# ml/features.py:155-170 — pure function of already-sliced state; cfg accepted
# for signature stability but the rule is config-free.
def features_at_decision(state: CandidateState, label_row: pd.Series, cfg) -> dict:
    """... Pure function of the already-visibility-filtered CandidateState...
    Never reads the label frame's post-decision columns..."""
    del cfg  # signature fidelity; see docstring
```
`serialize_evidence(scorer_result, candidate_state, contributors, cfg) -> dict` follows the same shape. This is an **adapt** — you build the evidence object from `Scorer.score()` (returns `p_win`/`score_source`/`artifact_version`, `scorer.py` lines 114–124) and `Scorer.contributors()` (returns per-row feature `pred_contrib` with trailing `bias`, `scorer.py` lines 126–136), then rank top-5 by `|contrib|` excluding `bias` (RESEARCH.md line 305, Discretion A5).

**Fail-fast invariant guards** (copy `ml/features.py` `_validate_bars` lines 117–138 — validate inputs before blind assembly, name the offending field):
```python
# ml/features.py:117-138
def _validate_bars(bars: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_BARS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"build_feature_frame invariant violated: bars is missing required "
            f"columns {missing}"
        )
```
Use the same "invariant violated: ..." message style. **Never** reach into the label frame's post-decision columns (`entry_price`/`exit_*`/`rr`/`outcome`) — RESEARCH.md Pitfall 3 (lines 322–326) names these as FORBIDDEN.

**Point-in-time discipline:** reuse `backtest/asof.py` `visible_mask` + `close_time_of` (imported in `features.py` line 32 and `candidates.py` line 40) so the evidence object carries no future data.

---

### `src/ai_trading/llm/prompt.py` (utility, pure transform)

**Analog:** no existing string-template module. **Copy the codebase pure-function convention + the RESEARCH D-03 rule.**

- Signature follows the `features.py` pure-function pattern: `build_prompt(evidence: dict) -> tuple[list[dict], ...]` returning `system`/`user` message dicts (RESEARCH.md lines 218/367).
- The invariant to enforce (RESEARCH.md D-03, lines 288–294 Anti-Pattern): the prompt is built **only** from the evidence object's field projection. No raw OHLC/candle series, no recomputed levels. Test `test_llm_prompt.py::test_prompt_contains_only_evidence` asserts this.

---

### `src/ai_trading/llm/citations.py` (utility, pure guard)

**Analog:** `src/ai_trading/ml/artifact.py` `_validate_library_version`/`load_artifact` + `ml/features.py` `_validate_bars` — **copy the refuse-and-name-expected-vs-found discipline.**

**Refuse + name expected vs found** (copy `ml/artifact.py` lines 214–232 / 252–263):
```python
# ml/artifact.py:219-224 — refuse names expected vs found, never silent-skip
if inst_major != rec_major:
    raise ValueError(
        f"{name} major version mismatch: bundle was recorded under "
        f"{recorded!r} but installed is {installed!r} — refusing the load ..."
    )
```
`citation_check(narrative, evidence) -> dict` returns `{status: 'verified'|'unverified', dropped: [...], unknown: [...], mismatch: [...]}` (RESEARCH.md lines 274–285). Drop any citation key in `FORBIDDEN_LEVEL_KEYS` (D-02), flag `unknown` keys not in `evidence`, flag value `mismatch`. Any non-empty → `unverified` + discard + count (D-05, never silently kept).

---

### `src/ai_trading/llm/agreement.py` (utility, pure function)

**Analog:** `src/ai_trading/backtest/candidates.py` `bias_agrees`/`compute_rr` — **copy the pure, NA-safe, config-thresholded function style.**

**Pure boolean/threshold function** (copy `bias_agrees` lines 82–88 — NA-safe, deterministic, config-free rule):
```python
# candidates.py:82-88
def bias_agrees(bias_h1: Any, bias_h4: Any, direction: str) -> bool:
    want = "bullish" if direction == "long" else "bearish"
    h1_ok = (not pd.isna(bias_h1)) and bias_h1 == want
    h4_ok = (not pd.isna(bias_h4)) and bias_h4 == want
    return bool(h1_ok or h4_ok)
```
`agreement_flag(verdict, confidence, p_win, cfg) -> tuple[str, float]` returns the 3-state `agree/disagree/unclear` + confidence, thresholded on `cfg.llm_agree_min_confidence` (RESEARCH.md Open Question 1, lines 428–432). Pure function of inputs; no I/O.

---

### `src/ai_trading/llm/narrative.py` (service, orchestrator + graceful fallback)

**Analog:** `src/ai_trading/collector.py` (orchestration service, error taxonomy, retry loop) — **copy the orchestration + try/except fallback structure, adapt to the provider.**

**Orchesque flow:** serialize evidence → `build_prompt` → `provider.build_narrative(...)` → pydantic-validate → `citation_check` → `agreement_flag` → writer (RESEARCH.md ARCH lines 183). The fallback is a `try/except` around the provider call (`narrative_none, agreement_none, score_source='ml'`, `narrative_status='llm_unavailable'`, `reason='timeout|error'`) per RESEARCH.md Open Question 2 (lines 433–436). Emit a **complete ML-only setup** — never a partial record.

**Graceful-degradation discipline (Role/AI-07):** the provider call is isolated so a failing/slow endpoint never blocks setup emission. This mirrors `test_health_check.py`'s exception-path hunting, and the codebase's `mt5_client`-is-replaceable seam.

---

### `src/ai_trading/llm/writer.py` (storage, file-I/O atomic)

**Analog:** `src/ai_trading/backtest/reports.py` `_atomic_json`/`_atomic_parquet` + `write_run_manifest`; `src/ai_trading/ml/artifact.py` `_atomic_write`/`_json_safe` — **copy the atomic-write + invariant-validation pattern verbatim.**

**Atomic tmp+os.replace** (copy `reports.py` lines 65–91):
```python
# reports.py:65-77 — atomic JSON write through tmp + os.replace
def _atomic_json(obj, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)  # atomic on the same NTFS volume (Windows included)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
```
(reports.py lines 80–91 `_atomic_parquet` is identical but `df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)`.) Also `ml/artifact.py` lines 105–117 gives a generic `_atomic_write(path, write_fn)`.

**Invariant / schema validation** (copy `write_run_manifest` lines 152–174 — validate required AND reject unknown keys before writing, name them):
```python
# reports.py:161-171
missing = [key for key in MANIFEST_KEYS if key not in meta]
if missing:
    raise ValueError(f"write_run_manifest invariant violated: meta is missing required keys {missing}")
unknown = [key for key in meta if key not in MANIFEST_KEYS]
if unknown:
    raise ValueError(f"write_run_manifest invariant violated: unknown meta keys {unknown} ...")
```

**JSON-safety helper** (copy `reports.py` `_json_safe` lines 94–109, or `ml/artifact.py` `_json_safe` lines 79–102 which additionally handles `pd.Timestamp`) to serialize NaN/inf→`None`, numpy/pd scalars→natives before writing `data/reports/llm_narratives.*`.

---

### `src/ai_trading/llm/__init__.py` (package marker)

**Analog:** `src/ai_trading/ml/__init__.py` — **copy verbatim** (bare marker, import submodules directly):
```python
# ml/__init__.py:1-4
"""Pure ML transforms ...: MT5-free by design; import submodules directly — this file
stays a bare marker for the whole of Phase 4."""
```
For `llm/__init__.py`, keep it a bare marker with a one-line docstring naming the package; RESEARCH.md line 210 suggests it may re-export `LLMProvider, OpenAICompatProvider, build_narrative, agreement_flag` — but the `ml/__init__.py` precedent keeps it a marker, so the re-exports are optional and local-module imports are the convention.

---

### `src/ai_trading/config.py` (MODIFIED, config)

**Analog:** itself — extend the Phase-4 `ml_*` block. **Add `llm_*` keys in all three places the `ml_*` keys occupy:** (1) `_REQUIRED_KEYS` tuple, (2) `Config` frozen-dataclass fields with defaults, (3) `_validate` fail-fast block, plus (4) `load_config` construction.

**Placement 1 — `_REQUIRED_KEYS`** (copy from `ml/features` block lines 59–74):
```python
# config.py:59-74 (the __REQUIRED_KEYS "comments" convention)
    # ML scoring knobs (Phase 4) — same fail-fast contract: a typo'd or missing
    # ml_* key refuses load rather than silently changing training semantics.
    "ml_feature_list_version",
    "ml_calibration_method",
    ...
```
Add `llm_enabled`, `llm_base_url`, `llm_model`, `llm_api_key`, `llm_timeout_ms`, `llm_max_tokens`, `llm_top_n_contributors`, `llm_structured_mode`, `llm_agree_min_confidence`, `llm_max_retries`.

**Placement 2 — frozen Config fields with defaults** (copy pattern lines 110–126, note the comment style):
```python
# config.py:110-126 — Phase-3/4 fields carry defaults so direct construction
# (tests/conftest.py _make_cfg) keeps working unchanged.
    ml_feature_list_version: int = 1
    ml_calibration_method: str = "sigmoid"
```
Add `llm_*` fields with defaults. Per RESEARCH.md Open Question 4 (lines 443–446): commit `llm_enabled=false`, `llm_base_url`, `llm_model`, `llm_timeout_ms`, `llm_max_tokens`, `llm_top_n_contributors`, `llm_structured_mode`; `llm_api_key` is a **secret → only in `config.local.toml`**.

**Placement 3 — fail-fast validation** (copy the `ml_*` validation block lines 316–367, reusing `_is_int`/`_is_number`):
```python
# config.py:316-367 — the discipline to extend for llm_*
allowed_calibration = {"sigmoid", "isotonic"}
if cfg.ml_calibration_method not in allowed_calibration:
    raise ValueError(
        f"ml_calibration_method must be one of {sorted(allowed_calibration)}, "
        f"got {cfg.ml_calibration_method!r}"
    )
```
Add LLC-specific checks: `llm_structured_mode ∈ {json_schema, json_object, none}`, `llm_timeout_ms > 0`, `llm_max_tokens >= 2048` (reasoning-model budget, RESEARCH.md Pitfall 1), `0 <= llm_agree_min_confidence <= 1`, `llm_top_n_contributors >= 1`.

**Placement 4 — `load_config` construction** (copy the pattern at lines 147–188 — construct every field, including `llm_*`).

**Config never repr'd** (copy the docstring note lines 5–8 + the existing `ml_*`/credential hygiene): `llm_api_key` never appears in logs/`print`/repr.

---

### `pyproject.toml` (MODIFIED), `config.toml` / `config.local.toml` (MODIFIED)

**Analog:** themselves.
- `pyproject.toml`: add `"openai>=3.8.0"` to `[project].dependencies`; add the `llm` marker to the `markers` list and change `addopts` from `-m "not mt5"` to `-m "not mt5 and not llm"` (RESEARCH.md lines 476–478, 499). Current state confirmed: `addopts = '-m "not mt5"'`, `markers = ["unit: ...", "mt5: ..."]`.
- `config.toml`: commit the public `llm_*` defaults (no secrets). `config.local.toml`: `llm_api_key` only.

---

### Test files `tests/unit/_llm_fixtures.py`, `test_llm_*.py`, `tests/integration/test_llm_live.py`

### `tests/unit/_llm_fixtures.py` (fixture factory)

**Analog:** `tests/conftest.py` `FakeMT5Client` (lines 103–251) + `tests/unit/_backtest_fixtures.py` `bt_cfg` (lines 57+) + `_ml_fixtures.py` `ml_cfg` — **copy the duck-typed fake + scripted responses/errors convention, adapt to `build_narrative`.**

**Duck-typed fake surface + recording** (copy `conftest.py` lines 103–199 — implement the same method surface as `LLMProvider`, record calls, script responses/errors):
```python
# conftest.py:135-199 — the fake mirrors the real module's surface and records
# every public call so tests assert exact arguments.
class FakeMT5Client:
    def __init__(self, *, init_ok=True, connected=True, ...):
        self.calls: list[tuple[str, tuple[tuple, dict]]] = []
        self.counts: Counter[str] = Counter()
        self._rates_deques: dict[tuple[str, int], deque] = {}
    def _record(self, name, *args, **kwargs): ...
    def script_rates(self, symbol, timeframe, responses): ...
```
`FakeLLMProvider` (RESEARCH.md lines 385–400) mirrors this: constructor takes `responses` (FIFO of raw JSON strings) and `errors` (FIFO of exceptions, e.g. `TimeoutError`), a `calls` recording list, and `build_narrative(evidence, response_schema, *, cfg)` pops from the FIFOs (raising from `errors` on scripted timeout). A scripted `TimeoutError` proves AI-07/SC3 fallback with no live endpoint.

**Config fixture** (copy `_ml_fixtures.py` `ml_cfg` lines 60–64 — thin wrapper over `bt_cfg` carrying the new `llm_*` defaults, never touches `load_config`):
```python
# _ml_fixtures.py:60-64
def ml_cfg(**overrides) -> Any:
    """Frozen Config carrying the Phase-4 ml_* defaults ... never touches load_config."""
    return bt_cfg(**overrides)
```
For LLM tests: add `llm_cfg` extending `bt_cfg` with `llm_*` defaults. This keeps LLM unit tests offline and filesystem-free.

### Test modules `test_llm_{schema,provider,evidence,prompt,citations,agreement,fallback,writer}.py`

**Analog:** `tests/unit/test_ml_scorer.py` (lines 1–70) — **copy the unit-test module structure** (module docstring naming pinned tests, `@pytest.mark.unit`, imports from the `_*_fixtures` via direct import, no MT5/network dependency):
```python
# test_ml_scorer.py:1-25 — module docstring pins named tests; imports fixtures
# directly (pytest puts tests/ on sys.path); no MetaTrader5 import anywhere.
"""Unit tests for the loadable scorer ..."""
from __future__ import annotations
import pandas as pd
import pytest
from _ml_fixtures import make_labels, ml_cfg, synthetic_feature_frame
from ai_trading.ml.scorer import load_scorer

@pytest.mark.unit
```
Every LLM test module mirrors this: `from _llm_fixtures import FakeLLMProvider, make_evidence, llm_cfg`; decorator `@pytest.mark.unit`; the live-endpoint test lives in `tests/integration/` under a separate `llm` marker.

### `tests/integration/test_llm_live.py` (integration, `llm`-marked)

**Analog:** `tests/integration/test_live_collect.py` (`mt5`-marked opt-in) — **copy the opt-in integration structure.** It gets the `llm` marker and is auto-excluded by default.

## Shared Patterns

### 1. Adapter-tier isolation (one SDK import)
**Source:** `src/ai_trading/mt5_client.py` lines 1–23, 36–42.
**Apply to:** `llm/provider.py`, and indirectly every LLM module (they never import the openai SDK). The `openai` import exists exactly once, in `provider.py`, exactly as `MetaTrader5` exists once in `mt5_client.py`. Error taxonomy as `RuntimeError` subclasses (`LLMProviderError`, `LLMTruncatedError`).

### 2. Duck-typed test double (scripted responses/errors)
**Source:** `tests/conftest.py` `FakeMT5Client` lines 103–251.
**Apply to:** `tests/unit/_llm_fixtures.py` `FakeLLMProvider`. Same surface as `LLMProvider`; records calls; FIFO-scripts raw JSON responses and exceptions. The AI-07 fallback is proven by a scripted `TimeoutError`, offline, no live vLLM.

### 3. Pure-function discipline (no I/O, no mutation, no future info)
**Source:** `src/ai_trading/ml/features.py` `features_at_decision`/`build_feature_frame` lines 155–387; `src/ai_trading/ml/scorer.py` `score()`/`contributors()` lines 114–136; `src/ai_trading/backtest/asof.py` `visible_mask`/`close_time_of`.
**Apply to:** `llm/evidence.py`, `llm/prompt.py`, `llm/citations.py`, `llm/agreement.py`. All pure, MT5-free; serialize only from `CandidateState` + `Scorer` outputs; never recompute R:R/SL/TP (RESEARCH.md Pitfall 3) and never inject OHLC (D-03).

### 4. Schema-level refuse, never trust prompt adherence (SC1)
**Source:** `src/ai_trading/ml/artifact.py` `_validate_library_version`/`load_artifact` lines 214–267; `ml/features.py` `_CATEGORICAL_CATEGORIES` lines 97–109.
**Apply to:** `llm/schema.py` + `llm/citations.py`. A `FORBIDDEN_LEVEL_KEYS` frozenset + `ALLOWED_CITATION_KEYS` drops any level field; any unknown/mismatched citation ⇒ `unverified` + discard + count (D-05). Never persist what the guard rejected.

### 5. Atomic tmp+os.replace writer + invariant validation
**Source:** `src/ai_trading/backtest/reports.py` `_atomic_json`/`_atomic_parquet`/`write_run_manifest` lines 65–174; `src/ai_trading/ml/artifact.py` `_atomic_write`/`_json_safe` lines 79–117.
**Apply to:** `llm/writer.py`. Validate required AND reject unknown keys naming them; write through a `.tmp` sibling then `os.replace`; unlink tmp on failure. Serialize NaN/inf/numpy/pd scalars via `_json_safe`.

### 6. Frozen `Config` fail-fast extension
**Source:** `src/ai_trading/config.py` lines 59–74, 110–126, 316–367.
**Apply to:** `config.py` (add `llm_*`), `config.toml`, `config.local.toml`, `_llm_fixtures.llm_cfg`. Every `llm_*` key added in `_REQUIRED_KEYS`, the `Config` field list (with defaults), `_validate`, *and* `load_config` construction. `llm_api_key` only in gitignored `config.local.toml` (ASVS V14); `Config` never repr'd.

### 7. Test layering & markers
**Source:** `pyproject.toml` current `[tool.pytest.ini_options]`; RESEARCH.md lines 476–478, 499.
**Apply to:** `pyproject.toml`. Add the `llm` marker and change `addopts` to `-m "not mt5 and not llm"` so the live-endpoint test is excluded by default, keeping the suite offline-clean. Default `uv run pytest -q` runs unit-only and network-free.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/ai_trading/llm/prompt.py` | utility | transform | No existing string-template/prompt module in the codebase. Use the RESEARCH D-03 rule (only the evidence object; no OHLC/levels) + the pure-function convention from `ml/features.py`. |
| `config.local.toml` | config | n/a | Data/config file (gitignored), no source analog — it carries `llm_api_key` only, per the established `config.toml`/`config.local.toml` override discipline. |

## Metadata

**Analog search scope:** `src/ai_trading/` (adapter `mt5_client.py`, config, `backtest/{reports,candidates,asof}.py`, `ml/{features,scorer,artifact}.py`), `tests/` (`conftest.py`, `_backtest_fixtures.py`, `_ml_fixtures.py`, `test_ml_scorer.py`), `pyproject.toml`.
**Files scanned:** 23 new/modified files classified; ~14 source files read for analog extraction.
**Copy-from vs adapt:** **Copy-from** — `writer.py` (reports.py `_atomic_*`/`write_run_manifest`), `provider.py` (mt5_client.py adapter discipline), `__init__.py` (ml/__init__.py), `_llm_fixtures.py` (FakeMT5Client + ml_cfg/bt_cfg config constructor), all test modules (test_ml_scorer.py structure). **Adapt** — `schema.py` (pydantic over artifact/features constants), `evidence.py` (pure dict from Scorer+CandidateState), `citations.py` (artifact load-refuse + features `_validate_bars`), `agreement.py` (candidates.bias_agrees), `narrative.py` (collector orchestration + provider try/except), `config.py` (extend ml_* block), `pyproject.toml`.
**Pattern extraction date:** 2026-09-04
