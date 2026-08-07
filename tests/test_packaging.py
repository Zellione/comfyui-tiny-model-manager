"""Guards on the packaging metadata that makes this node installable from the Comfy Registry.

The Registry reads dependencies from ``[project] dependencies`` while ComfyUI-Manager's
git-URL install path reads ``requirements.txt``. Both files are kept, so something has to
fail the build when they drift apart.

Only a subset of ``pyproject.toml`` reaches the Registry. comfy-cli's publish payload
(``ComfyRegistryAPI.publish_node_version``) carries the project ``name``, ``description``,
``version``, ``dependencies`` and ``license``, the ``[tool.comfy]`` ``DisplayName``/``Icon``/
``Banner``, the ``Repository`` URL, and the ``supported_os``/``supported_accelerators`` it derives
from ``classifiers``. ``authors``, ``keywords`` and every other URL key are never sent — the tests
below pin the declared values anyway, but do not expect them on the listing.
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
        assert project["authors"]
        assert project["keywords"]

    def test_license_is_declared_as_text(self):
        """`serialize_license` prefers `file` over `text`, so the file form ships a path.

        With ``license = {file = "LICENSE"}`` the Registry stored the literal
        ``{"file": "LICENSE"}`` instead of the license itself.
        """
        license_field = _pyproject()["project"]["license"]

        assert license_field == {"text": "MIT"}

    def test_license_classifier_matches_license_file(self):
        assert "License :: OSI Approved :: MIT License" in _pyproject()["project"]["classifiers"]

    def test_os_classifier_present(self):
        """The one classifier the Registry reads: it becomes the listing's `supported_os`."""
        assert "Operating System :: OS Independent" in _pyproject()["project"]["classifiers"]

    def test_authors_carry_a_name(self):
        assert all(author.get("name") for author in _pyproject()["project"]["authors"])

    def test_urls_use_the_keys_comfy_cli_reads(self):
        """comfy-cli looks up Homepage/Documentation/Repository/Issues — anything else is dropped."""
        urls = _pyproject()["project"]["urls"]

        assert set(urls) == {"Homepage", "Repository", "Documentation", "Issues"}
        assert all(url.startswith("https://github.com/Zellione/") for url in urls.values())

    def test_publisher_id_matches_registry_handle(self):
        # The Registry publisher id is lowercase; the capitalised form 404s on the API.
        assert _pyproject()["tool"]["comfy"]["PublisherId"] == "zellione"

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
