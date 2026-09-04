"""Streamlit AppTest suite for the DASH-03 evidence trace.

Runs ``views_setups.render_evidence`` via ``AppTest.from_string`` against
fixture setup rows (verified narrative vs the labeled ML-only fallback),
asserting the six sub-sections render in the fixed UI-SPEC order, the agreement
chip + ML contributors render, the ``⌀`` + reason fallback is shown for an
unavailable narrative (never a blank), and a malformed evidence object degrades
gracefully. Marked ``@pytest.mark.streamlit`` (offline, no MT5/LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "tests" / "unit"))

import pytest  # noqa: E402  (after sys.path fixture-bootstrap)
from streamlit.testing.v1 import AppTest  # noqa: E402

#: Fixed evidence-trace section order (UI-SPEC Evidence Trace layout).
_SECTIONS = [
    "**1. Setup:",
    "**2. Bias & Context:",
    "**3. Zone:",
    "**4. Sweep:",
    "**5. ML Contributors:",
    "**6. Narrative:",
]


def _run_evidence(code: str) -> AppTest:
    at = AppTest.from_string(code)
    at.run()
    assert not at.exception
    return at


def _verified_code() -> str:
    return (
        "import streamlit as st\n"
        "from _dashboard_fixtures import make_verified_row\n"
        "from ai_trading.dashboard import views_setups\n"
        "setup = make_verified_row()\n"
        "views_setups.render_evidence(setup)\n"
    )


def _unavailable_code() -> str:
    return (
        "import streamlit as st\n"
        "from _dashboard_fixtures import make_unavailable_row\n"
        "from ai_trading.dashboard import views_setups\n"
        "setup = make_unavailable_row()\n"
        "views_setups.render_evidence(setup)\n"
    )


def _markdown_texts(at) -> list:
    return [m.value for m in at.markdown]


@pytest.mark.streamlit
def test_evidence_sections_render_in_fixed_order():
    at = _run_evidence(_verified_code())
    md = _markdown_texts(at)
    indices = [next(i for i, v in enumerate(md) if v.startswith(marker)) for marker in _SECTIONS]
    assert indices == sorted(indices), "evidence sections must render in the fixed UI-SPEC order"


@pytest.mark.streamlit
def test_evidence_agreement_chip_and_ml_contributors_render():
    at = _run_evidence(_verified_code())
    md = "\n".join(_markdown_texts(at))
    # Agreement chip for a verified, agreeing narrative.
    assert "Agree" in md
    # ML contributors: whole-percent p_win + featured attribution.
    assert "62% [ML+LLM]" in md
    assert "swing_strength" in md
    assert "zone_quality" in md
    # Verified narrative details.
    assert "Confirm" in md
    assert "Citations:" in md


@pytest.mark.streamlit
def test_evidence_llm_unavailable_renders_circle_and_reason():
    at = _run_evidence(_unavailable_code())
    md = "\n".join(_markdown_texts(at))
    warnings = [w.value for w in at.warning]
    # Honesty rule: ⌀ + reason, never a blank.
    assert "\u2300" in md or any("\u2300" in str(w) for w in warnings)
    assert any("timeout" in str(w) or "unavailable" in str(w) for w in warnings)
    assert "ML-only" in "\n".join(str(w) for w in warnings)


@pytest.mark.streamlit
def test_evidence_malformed_evidence_json_degrades_without_raise():
    code = (
        "import streamlit as st\n"
        "from ai_trading.dashboard import views_setups\n"
        "setup = {"
        "'symbol': 'EURUSD', 'timeframe': 'M15', 'direction': 'long', "
        "'entry': 1.10, 'sl_price': 1.095, 'tp_price': 1.12, "
        "'rr_at_decision': 4.0, 'created_at': '2026-08-20 09:00', "
        "'zone_id': 'z-001', 'zone_state': 'mitigated', "
        "'zone_range_high': 1.105, 'zone_range_low': 1.098, "
        "'event_id': 'ev-001', 'pool_id': 'p-001', "
        "'p_win': 0.62, 'score_source': 'ml', "
        "'evidence_json': 'not-valid-json{{{', "
        "'narrative_status': 'llm_unavailable', 'narrative_reason': 'error'}\n"
        "views_setups.render_evidence(setup)\n"
    )
    at = _run_evidence(code)
    warnings = [w.value for w in at.warning]
    assert any("unavailable" in str(w) for w in warnings)
