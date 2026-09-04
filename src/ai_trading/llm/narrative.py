"""Narrative pipeline orchestrator (AI-05 / AI-06 / AI-07) with graceful
fallback.

``run_narrative_pipeline(provider, evidence, cfg) -> NarrativeResult``
orchestrates: ``build_prompt(evidence)`` → ``provider.build_narrative(...)`` →
parse + pydantic-validate ``LLMNarrative`` → ``citation_check`` →
``agreement_flag``. The provider call is enclosed so a slow/down endpoint never
blocks setup emission (AI-07 / SC3).

``NarrativeResult`` carries the full observable state — including the ML-only
provenance on every fallback path — so a setup's provenance (LLM vs ML vs
unavailable) is never ambiguous (T-05-08 repudiation).

Fallback policy (research OQ2, pinned):
- On a provider error/timeout the pipeline returns a complete ML-only setup:
  ``narrative=None``, ``agreement=None``, ``score_source="ml"``,
  ``narrative_status="llm_unavailable"``, ``reason="timeout" | "error"``, with
  ``p_win`` preserved from the evidence.
- ``LLMTruncatedError`` (content=None on a reasoning model; RESEARCH Pitfall 1)
  triggers one retry, then the same ML-only fallback on a second failure.
- ``llm_enabled=False`` short-circuits to the ML-only path with NO provider call.
- A citation check ``unverified`` discards the narrative (``narrative=None``,
  ``agreement=None``, ``score_source="ml"``,
  ``narrative_status="citation_rejected"``) — never kept (D-05).

Success path carries the verified ``LLMNarrative`` + agreement flag + agreement
confidence with ``score_source="ml_llm"``, ``narrative_status="ok"``,
``citation_status="verified"``. The result NEVER contains an LLM-originated
level/probability — only verdict / confidence / reasoning / citations (D-02 /
T-05-11).

MT5-free; the only I/O is inside the injected provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_trading.llm.agreement import agreement_flag
from ai_trading.llm.citations import citation_check
from ai_trading.llm.provider import LLMTruncatedError
from ai_trading.llm.schema import LLMNarrative, narrative_response_format


@dataclass(frozen=True)
class NarrativeResult:
    """The full, auditable outcome of one narrative pipeline run."""

    narrative: Any  # LLMNarrative | None
    citation_status: str | None  # "verified" | "unverified" | None
    agreement: str | None  # "agree" | "disagree" | "unclear" | None
    agreement_confidence: float | None
    p_win: float | None
    score_source: str  # "ml" | "ml_llm"
    narrative_status: str  # "ok" | "citation_rejected" | "llm_unavailable"
    reason: str | None
    artifact_version: int | None


def _artifact_version(evidence: dict) -> int | None:
    value = evidence.get("artifact_version")
    return int(value) if value is not None else None


def _ml_only_result(evidence: dict, reason: str) -> NarrativeResult:
    """The complete ML-only fallback record (AI-07 / SC3): labeled observable
    state, never silence."""
    return NarrativeResult(
        narrative=None,
        citation_status=None,
        agreement=None,
        agreement_confidence=None,
        p_win=evidence.get("p_win"),
        score_source="ml",
        narrative_status="llm_unavailable",
        reason=reason,
        artifact_version=_artifact_version(evidence),
    )


def run_narrative_pipeline(provider, evidence: dict, cfg) -> NarrativeResult:
    """Run the narrative pipeline and return a complete ``NarrativeResult``.

    ``evidence`` is the serialized D-01 evidence object (see
    ``evidence.serialize_evidence``). This function never raises on a provider
    failure/disable/unverified citation — it always returns a valid result.
    """
    if not cfg.llm_enabled:
        return _ml_only_result(evidence, "llm_disabled")

    response_schema = narrative_response_format()
    try:
        raw = provider.build_narrative(evidence, response_schema, cfg=cfg)
    except LLMTruncatedError:
        # RESEARCH A3/Pitfall 1: content=None on a reasoning model → retry once.
        try:
            raw = provider.build_narrative(evidence, response_schema, cfg=cfg)
        except TimeoutError:
            return _ml_only_result(evidence, "timeout")
        except Exception:
            return _ml_only_result(evidence, "error")
    except TimeoutError:
        return _ml_only_result(evidence, "timeout")
    except Exception:
        return _ml_only_result(evidence, "error")

    try:
        narrative = LLMNarrative.model_validate_json(raw)
    except Exception:
        # Unparseable / schema-violating output is an error, not a parse crash.
        return _ml_only_result(evidence, "error")

    check = citation_check(narrative, evidence)
    if check["status"] != "verified":
        return NarrativeResult(
            narrative=None,
            citation_status="unverified",
            agreement=None,
            agreement_confidence=None,
            p_win=evidence.get("p_win"),
            score_source="ml",
            narrative_status="citation_rejected",
            reason="unverified_citation",
            artifact_version=_artifact_version(evidence),
        )

    agreement, agreement_confidence = agreement_flag(
        narrative.verdict, narrative.confidence, evidence["p_win"], cfg
    )
    return NarrativeResult(
        narrative=narrative,
        citation_status="verified",
        agreement=agreement,
        agreement_confidence=agreement_confidence,
        p_win=evidence.get("p_win"),
        score_source="ml_llm",
        narrative_status="ok",
        reason=None,
        artifact_version=_artifact_version(evidence),
    )
