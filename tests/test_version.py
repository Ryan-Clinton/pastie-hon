"""One version, everywhere it is read.

0.3.1 went out with `pastie.__version__` saying 0.3.1 and pyproject.toml still
saying 0.3.0. The Windows build read one and PyPI the other, and the PyPI
upload failed as a duplicate. The version is now read from the package; this
keeps it that way.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

import pastie

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_the_installed_package_reports_the_code_s_own_version() -> None:
    assert version("pastie-hon") == pastie.__version__


def test_pyproject_does_not_carry_a_second_copy_of_the_version() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]
