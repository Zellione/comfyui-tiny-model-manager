#!/usr/bin/env python3
"""Parse a single PRD feature section and print compact YAML."""

import argparse
import re
import sys
from pathlib import Path

# YAML special characters that require quoting
_YAML_SPECIAL = set(":#{}[]|>&*!,?'\"\\")


def _yaml_scalar(value: str) -> str:
    if any(c in _YAML_SPECIAL for c in value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _yaml_list(key: str, items: list[str]) -> str:
    lines = [f"{key}:"] + [f"  - {_yaml_scalar(item)}" for item in items]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

_SECTION_HEADER = re.compile(r"^### (F-\d+) — (.+)$")


def extract_section(content: str, feature_id: str) -> str | None:
    lines = content.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        m = _SECTION_HEADER.match(line)
        if m and m.group(1) == feature_id:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _SECTION_HEADER.match(lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# Field parsers
# ---------------------------------------------------------------------------


def extract_title(section: str) -> str:
    m = _SECTION_HEADER.match(section.splitlines()[0])
    return m.group(2).strip() if m else ""


_PREAMBLE = re.compile(
    r"^(The system shall |Users can |Users |A |An |Each |Every |This )",
    re.IGNORECASE,
)


def _lines_under_heading(section: str, heading_pattern: re.Pattern[str]) -> list[str]:
    """Return the lines following the first matching heading, up to the next bold heading.

    Blockquote lines are dropped, and the heading line itself is excluded.
    """
    block: list[str] = []
    active = False
    for line in section.splitlines():
        if line.startswith(">"):
            continue
        if heading_pattern.match(line):
            active = True
            continue
        if not active:
            continue
        if re.match(r"^\*\*[^*]", line):
            break
        block.append(line)
    return block


def _bullets_under(section: str, heading_pattern: re.Pattern[str]) -> list[str]:
    """Return bullet text under the first matching heading, stopping at the next bold heading.

    Continuation lines (indented with 2+ spaces, no leading dash) are joined onto the
    previous bullet so multi-line PRD bullets become single YAML strings.
    """
    result: list[str] = []
    current: str | None = None
    for line in _lines_under_heading(section, heading_pattern):
        m = re.match(r"^- (.+)$", line)
        if m:
            if current is not None:
                result.append(current)
            current = m.group(1).rstrip()
        elif current is not None and line.startswith("  "):
            current = current.rstrip(",") + " " + line.strip()
    if current is not None:
        result.append(current)
    return result


_REQ_HEADING = re.compile(r"^\*\*Requirements:\*\*")
_API_HEADING = re.compile(r"^\*\*API")
_NON_GOALS_HEADING = re.compile(r"^\*\*Non-Goals:\*\*")


def extract_requirements(section: str) -> list[str]:
    items = _bullets_under(section, _REQ_HEADING)
    cleaned: list[str] = []
    for item in items:
        # Strip inline bold markers and backtick fences from the leading preamble
        text = re.sub(r"^\*\*[^*]+\*\*[:\s]*", "", item)
        text = _PREAMBLE.sub("", text).strip()
        if text:
            cleaned.append(text)
    return cleaned


def extract_api(section: str) -> list[str]:
    return _bullets_under(section, _API_HEADING)


def extract_depends_on(section: str) -> list[str]:
    body = "\n".join(section.splitlines()[1:])
    seen: set[str] = set()
    result: list[str] = []
    for fid in re.findall(r"F-\d+", body):
        if fid not in seen:
            seen.add(fid)
            result.append(fid)
    return result


def extract_non_goals(section: str) -> list[str]:
    return _bullets_under(section, _NON_GOALS_HEADING)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a PRD feature section as compact YAML.")
    parser.add_argument("feature_id", help="Feature identifier, e.g. F-23")
    parser.add_argument("prd_file", help="Path to PRD.md")
    args = parser.parse_args()

    try:
        content = Path(args.prd_file).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: file not found: {args.prd_file}", file=sys.stderr)
        sys.exit(1)

    section = extract_section(content, args.feature_id)
    if section is None:
        print(f"Error: feature '{args.feature_id}' not found in {args.prd_file}", file=sys.stderr)
        sys.exit(1)

    title = extract_title(section)
    requirements = extract_requirements(section)
    api = extract_api(section)
    depends_on = extract_depends_on(section)
    non_goals = extract_non_goals(section)

    print(f"feature_id: {args.feature_id}")
    print(f"title: {_yaml_scalar(title)}")
    if requirements:
        print(_yaml_list("requirements", requirements))
    if api:
        print(_yaml_list("api", api))
    if depends_on:
        print(_yaml_list("depends_on", depends_on))
    if non_goals:
        print(_yaml_list("non_goals", non_goals))


if __name__ == "__main__":
    main()
