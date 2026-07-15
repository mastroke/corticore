"""Guard against version drift between pyproject.toml and the package.

Version now lives only in pyproject.toml; `corticore.__version__` derives from
package metadata (with a source-tree fallback). This test pins that they
agree, so a release can never ship a package whose reported version disagrees
with its metadata.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import corticore  # noqa: E402


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no version found in pyproject.toml"
    return match.group(1)


def test_version_is_semver():
    assert re.match(r"^\d+\.\d+\.\d+", corticore.__version__)


def test_version_matches_pyproject_or_installed_metadata():
    pyproject_version = _pyproject_version()
    reported = corticore.__version__

    try:
        from importlib.metadata import version

        installed = version("corticore")
    except Exception:  # noqa: BLE001
        installed = None

    # Either we resolved from the source tree (matches pyproject) or from
    # installed metadata (matches what pip installed).
    assert reported in {pyproject_version, installed}
