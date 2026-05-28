"""Parse `- [x]` / `- [ ]` checklists scoped to a header section."""

from __future__ import annotations

import re
from typing import Iterable


_CHECKBOX_LINE = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<label>.+?)\s*$",
    re.MULTILINE,
)


def parse_checklist(body: str, header: str) -> list[tuple[str, bool]]:
    """Return ``(label, checked)`` for every checklist row under ``header``.

    The header is matched as a `### <header>` Markdown heading (the issue
    form's standard render). Trailing colons on ``header`` are tolerated.
    """

    if not body or not header:
        return []

    stripped = header.rstrip(":")
    header_pattern = re.compile(
        rf"^#+\s*{re.escape(stripped)}:?\s*$",
        re.MULTILINE,
    )
    start = header_pattern.search(body)
    if not start:
        return []

    next_header = re.compile(r"^#+\s.+$", re.MULTILINE)
    section_start = start.end()
    next_match = next_header.search(body, pos=section_start)
    section_end = next_match.start() if next_match else len(body)
    section = body[section_start:section_end]

    results: list[tuple[str, bool]] = []
    for m in _CHECKBOX_LINE.finditer(section):
        results.append((m.group("label").strip(), m.group("mark") in ("x", "X")))
    return results


def all_ticked(items: Iterable[tuple[str, bool]]) -> bool:
    items = list(items)
    if not items:
        return False
    return all(checked for _, checked in items)
