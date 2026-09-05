"""Atomic config.local.toml editor for the dashboard LLM settings panel
(SEED-004) — validate-before-write discipline.

``update_local_overrides(base, updates)`` merges scalar overrides into the
sibling ``config.local.toml`` the same way ``load_config`` would, proves the
merged set is valid via ``config.validate_merged`` (fail-fast, no half-written
state), and only then atomically replaces the file (tmp + ``os.replace`` — the
store-write discipline). Any validation failure raises before the file is
touched.

File-ownership note: TOML comments are not preserved by tomllib, so a panel
write rewrites the file without its comments (a generated-by header is added).
The UI surfaces this; hand-edits after a panel write are still honored until
the next panel save.

Secret hygiene: values are never embedded in raised error messages; the API
key is a normal merged value in memory only.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

from ai_trading.config import validate_merged

_LOCAL_NAME = "config.local.toml"

_HEADER = (
    "# Managed by the dashboard LLM settings panel — hand-edits are honored\n"
    "# until the next panel save. Comments are not preserved across saves.\n"
)


def _toml_value(value: Any) -> str:
    """Serialize a scalar/inline-table value as TOML. Strings go through
    json.dumps (a JSON basic string is a valid TOML basic string for the
    characters the settings panel writes); dicts recurse to inline tables."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        inner = ", ".join(f"{k} = {_toml_value(v)}" for k, v in sorted(value.items()))
        return "{ " + inner + " }"
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value) if isinstance(value, float) else str(value)


def read_local_raw(base: Path) -> dict[str, Any]:
    """Return the parsed sibling ``config.local.toml`` ({} when absent)."""
    local = Path(base).parent / _LOCAL_NAME
    if not local.exists():
        return {}
    with open(local, "rb") as fh:
        return tomllib.load(fh)


def local_path(base: Path) -> Path:
    """The sibling ``config.local.toml`` path for ``base``."""
    return Path(base).parent / _LOCAL_NAME


def update_local_overrides(base: Path, updates: dict[str, Any]) -> None:
    """Merge ``updates`` into config.local.toml atomically after proving the
    merged configuration is valid.

    Raises ``ValueError`` (from validation) or ``OSError`` (from I/O) without
    modifying the existing file. Comment lines are not preserved.
    """
    base = Path(base)
    merged = {**read_local_raw(base), **updates}
    validate_merged(base, merged)  # ValueError propagates; file untouched

    local = local_path(base)
    lines = [_HEADER.rstrip("\n")]
    lines.extend(f"{key} = {_toml_value(value)}" for key, value in sorted(merged.items()))
    payload = "\n".join(lines) + "\n"

    tmp = local.with_suffix(".toml.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, local)
    finally:
        if tmp.exists():
            tmp.unlink()
