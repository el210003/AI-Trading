"""Wave-0 scaffold tests: tooling config + core imports (no MT5 required)."""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@pytest.mark.unit
def test_core_libraries_import_and_report_versions():
    """pandas/pyarrow import cleanly under the uv-managed environment (A3 de-risk)."""
    import pandas
    import pyarrow

    assert pandas.__version__
    assert pyarrow.__version__


@pytest.mark.unit
def test_pytest_markers_declared_and_mt5_excluded_by_default():
    """The two markers exist and default addopts excludes mt5-marked tests."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    opts = data["tool"]["pytest"]["ini_options"]

    markers = " ".join(opts["markers"])
    assert "unit:" in markers
    assert "mt5:" in markers
    assert 'not mt5' in opts["addopts"]
    assert opts["testpaths"] == ["tests"]
