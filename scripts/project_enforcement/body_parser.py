"""Extract values from GitHub issue-form rendered bodies.

The issue form labels (`Risk ID:`, `Requirement ID:`) render in the
issue body as `### Risk ID:` headers followed by the value on a
subsequent line. The traceability gate uses an inline regex that
sometimes matches the empty rest of the header line; this parser is
the form-aware version it should have been.
"""

from __future__ import annotations

import re
from typing import Optional


def extract_field(body: str, label: str) -> Optional[str]:
    """Return the value rendered under a ``### <label>`` heading.

    ``label`` may include or omit a trailing colon; the search tolerates
    either. Returns ``None`` when the section is missing or empty.
    """

    if not body:
        return None

    stripped = label.rstrip(":")
    pattern = re.compile(
        rf"^#+\s*{re.escape(stripped)}:?\s*$\s*(.*?)(?=^#+\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None
