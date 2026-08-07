"""Guards on the packaging metadata that makes this node installable from the Comfy Registry.

The Registry reads dependencies from ``[project] dependencies`` while ComfyUI-Manager's
git-URL install path reads ``requirements.txt``. Both files are kept, so something has to
fail the build when they drift apart.
"""

import os

import pytest

# tomllib is stdlib from 3.11; the 3.10 CI leg skips this module rather than adding a dependency.
tomllib = pytest.importorskip("tomllib")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pyproject():
    with open(os.path.join(_ROOT, "pyproject.toml"), "rb") as fh:
        return tomllib.load(fh)


def _requirements_txt():
    with open(os.path.join(_ROOT, "requirements.txt"), encoding="utf-8") as fh:
        return {stripped for line in fh if (stripped := line.split("#", 1)[0].strip())}


class TestDependencyDrift:
    def test_pyproject_dependencies_match_requirements_txt(self):
        declared = set(_pyproject()["project"]["dependencies"])

        assert declared == _requirements_txt(), (
            "requirements.txt and [project] dependencies disagree; update both."
        )


class TestRegistryMetadata:
    def test_project_fields_present(self):
        project = _pyproject()["project"]

        assert project["name"] == "tiny-model-manager"
        assert project["version"]
        assert project["description"]
        assert project["license"] == {"file": "LICENSE"}
        assert project["urls"]["Repository"]

    def test_publisher_id_present(self):
        assert _pyproject()["tool"]["comfy"]["PublisherId"] == "Zellione"

    def test_license_file_exists(self):
        assert os.path.isfile(os.path.join(_ROOT, "LICENSE"))

    def test_icon_file_exists(self):
        # [tool.comfy] Icon points at this path via raw.githubusercontent.com.
        assert os.path.isfile(os.path.join(_ROOT, "assets", "icon.svg"))


class TestPythonFloor:
    def test_ruff_target_version_matches_requires_python(self):
        """A higher ruff target would let UP rules emit syntax the declared floor cannot parse."""
        config = _pyproject()
        requires = config["project"]["requires-python"]
        target = config["tool"]["ruff"]["target-version"]

        assert requires == ">=3.10"
        assert target == "py310"
