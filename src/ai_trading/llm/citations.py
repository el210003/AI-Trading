"""Strict citation check (D-02 / D-05 / SC1) — pure guard, never trusts the
prompt.

``citation_check(narrative, evidence)`` returns ``{status, dropped, unknown,
mismatch}``. A narrative is ``verified`` ONLY when every cited key is a real,
non-level evidence field and its value is consistent; any unknown key, any
forbidden level key, or any value mismatch flags it ``unverified`` and the
narrative pipeline discards it (D-05 — counted, never silently kept).

- ``dropped``: any cited key in the schema's ``FORBIDDEN_LEVEL_KEYS`` (D-02 —
  a level field the LLM cited is structurally dropped; it is not a legal
  citation target).
- ``unknown``: any cited key not present in the evidence object (a key the
  model invented — never silently passed, D-05).
- ``mismatch``: for a cited scalar enum field (direction, zone_state,
  bias_h1/bias_h4, sweep_side), the reasoning's asserted value differs from the
  evidence value (normalized string equality, research OQ3). Numeric fields
  (p_win, contributors) are NEVER required to reproduce a value —
  existence-in-evidence is what matters (OQ3: recomputed numeric values never
  originate), so they are not value-checked.

Pure: no I/O, no mutation.
"""

from __future__ import annotations

import re

from ai_trading.llm.schema import FORBIDDEN_LEVEL_KEYS

#: Scalar enum citation fields whose cited value is compared against the
#: evidence value (research OQ3: normalized string equality).
_ENUM_CITATION_KEYS = frozenset({"direction", "zone_state", "bias_h1", "bias_h4", "sweep_side"})

#: Allowed values per enum field, used only to detect a contradiction (the
#: reasoning asserting a DIFFERENT value than the evidence). Pinned here the
#: same way ml/features pins ``_CATEGORICAL_CATEGORIES`` — never inferred from
#: data.
_ENUM_CITATION_VALUES: dict[str, tuple[str, ...]] = {
    "direction": ("long", "short"),
    "zone_state": ("created", "tapped", "mitigated", "invalidated", "premium", "discount"),
    "bias_h1": ("bullish", "bearish", "neutral"),
    "bias_h4": ("bullish", "bearish", "neutral"),
    "sweep_side": ("high", "low"),
}


def _norm(value) -> str:
    """Strip-and-lowercase normalization for value comparison (OQ3)."""
    return str(value).strip().lower()


def _mentions(reasoning: str, value: str) -> bool:
    """True when ``reasoning`` mentions ``value`` as a standalone token
    (case-insensitive, word-boundary; skips too-short tokens)."""
    value = _norm(value)
    if len(value) < 2:
        return False
    return re.search(rf"\b{re.escape(value)}\b", reasoning, flags=re.IGNORECASE) is not None


def _reasoning_contradicts(reasoning: str, key: str, evidence_value) -> bool:
    """True when the reasoning asserts a value for ``key`` that differs from
    ``evidence_value``.

    If the reasoning contains the evidence value it agrees → no contradiction.
    Otherwise, if it contains any OTHER allowed value for that enum field it is
    asserting a different value → contradiction. If neither is present the
    check is lenient (existence-in-evidence is what matters).
    """
    normalized = _norm(evidence_value)
    if _mentions(reasoning, normalized):
        return False
    for alt in _ENUM_CITATION_VALUES.get(key, ()):
        alt_norm = _norm(alt)
        if alt_norm != normalized and _mentions(reasoning, alt_norm):
            return True
    return False


def citation_check(narrative, evidence: dict) -> dict:
    """Return ``{status, dropped, unknown, mismatch}`` for the narrative.

    ``status`` is ``'verified'`` only when ``dropped``, ``unknown`` and
    ``mismatch`` are all empty; otherwise ``'unverified'`` (D-05 — never pass
    a suspect narrative silently).
    """
    citations = set(narrative.citations)
    dropped = [key for key in citations if key in FORBIDDEN_LEVEL_KEYS]
    unknown = [key for key in citations if key not in evidence]
    mismatch: list[str] = []
    for key in citations:
        if key in FORBIDDEN_LEVEL_KEYS or key not in evidence:
            continue
        if key in _ENUM_CITATION_KEYS:
            if _reasoning_contradicts(narrative.reasoning, key, evidence[key]):
                mismatch.append(key)
    status = "verified" if not (dropped or unknown or mismatch) else "unverified"
    return {
        "status": status,
        "dropped": sorted(dropped),
        "unknown": sorted(unknown),
        "mismatch": sorted(mismatch),
    }
