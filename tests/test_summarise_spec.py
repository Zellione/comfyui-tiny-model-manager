"""Behavioural tests for the tools/summarise_spec.py PRD extractor."""

from tools.summarise_spec import (
    extract_api,
    extract_depends_on,
    extract_non_goals,
    extract_requirements,
    extract_section,
    extract_title,
)

SAMPLE = """\
### F-10 — Settings Page

**Requirements:**
- The system shall expose a settings page
- Users can edit the media directory,
  which may be an absolute path
- A token field stores the CivitAI key

**API:**
- GET /api/settings
- PUT /api/settings

**Non-Goals:**
- Multi-user settings

Depends on F-02 and F-08, plus F-02 again.

### F-11 — Next Feature

**Requirements:**
- Unrelated requirement
"""


def test_extract_section_isolates_feature():
    section = extract_section(SAMPLE, "F-10")
    assert section is not None
    assert section.startswith("### F-10")
    assert "F-11" not in section
    assert "Unrelated requirement" not in section


def test_extract_section_missing_returns_none():
    assert extract_section(SAMPLE, "F-99") is None


def test_extract_title():
    section = extract_section(SAMPLE, "F-10")
    assert extract_title(section) == "Settings Page"


def test_extract_requirements_strips_preamble_and_joins_continuations():
    section = extract_section(SAMPLE, "F-10")
    reqs = extract_requirements(section)
    assert reqs == [
        "expose a settings page",
        "edit the media directory which may be an absolute path",
        "token field stores the CivitAI key",
    ]


def test_extract_api():
    section = extract_section(SAMPLE, "F-10")
    assert extract_api(section) == ["GET /api/settings", "PUT /api/settings"]


def test_extract_non_goals():
    section = extract_section(SAMPLE, "F-10")
    assert extract_non_goals(section) == ["Multi-user settings"]


def test_extract_depends_on_dedupes_preserving_order():
    section = extract_section(SAMPLE, "F-10")
    # The feature's own heading id is excluded (body starts after line 1).
    assert extract_depends_on(section) == ["F-02", "F-08"]
