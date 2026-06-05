"""Summarise grype vulnerability-scan output.

The release workflow runs grype over the SBOM and feeds its JSON here. This is
the pure, testable part: validate that grype actually completed, tally findings
by severity, decide whether the result should block a release in `active` mode
(any Critical or High), and render a step-summary markdown block. Running grype,
and acting on ``has_blocking``, are the workflow's job.

``load`` is **fail-closed**: a scan that did not genuinely run — a non-zero
grype exit, empty or unparseable output, or a document with no vulnerability-DB
descriptor — raises :class:`ScanError` rather than being silently tallied as a
clean image. This stops a broken scanner (most importantly, a failed
vulnerability-DB download) from masquerading as "no vulnerabilities" and waving
a release through the gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


class ScanError(RuntimeError):
    """The grype run did not complete — a scanner failure, not a clean result."""

# Severity buckets in descending order; anything grype reports outside this set
# is counted as "unknown" rather than dropped.
SEVERITIES = ("critical", "high", "medium", "low", "negligible")

# Severities that fail an `active` release.
BLOCKING = ("critical", "high")


@dataclass
class ScanResult:
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    negligible: int = 0
    unknown: int = 0

    @property
    def total(self) -> int:
        return (
            self.critical + self.high + self.medium
            + self.low + self.negligible + self.unknown
        )

    @property
    def has_blocking(self) -> bool:
        return (self.critical + self.high) > 0

    @property
    def markdown(self) -> str:
        lines = ["## Vulnerability scan", ""]
        if self.total == 0:
            lines.append("✅ No known vulnerabilities in the SBOM.")
            return "\n".join(lines) + "\n"
        lines += ["| Severity | Count |", "|---|---|"]
        for sev in SEVERITIES:
            lines.append(f"| {sev.capitalize()} | {getattr(self, sev)} |")
        if self.unknown:
            lines.append(f"| Unknown | {self.unknown} |")
        verdict = (
            "❌ Critical/High findings present — blocks an `active` release."
            if self.has_blocking
            else "⚠️ No Critical/High findings; lower-severity issues noted above."
        )
        lines += ["", verdict]
        return "\n".join(lines) + "\n"


def summarize(grype: dict) -> ScanResult:
    """Tally a grype JSON document into a :class:`ScanResult`."""
    result = ScanResult()
    for match in (grype or {}).get("matches") or []:
        severity = ((match.get("vulnerability") or {}).get("severity") or "").strip().lower()
        if severity in SEVERITIES:
            setattr(result, severity, getattr(result, severity) + 1)
        else:
            result.unknown += 1
    return result


def load(stdout: str, *, returncode: int = 0, stderr: str = "") -> ScanResult:
    """Validate a grype invocation and summarise it, or raise :class:`ScanError`.

    Fail-closed: only a genuinely completed scan is summarised. A genuinely clean
    image (DB loaded, zero matches) returns an empty :class:`ScanResult`; a scan
    that never ran raises rather than reporting a false clean.
    """
    if returncode != 0:
        raise ScanError(
            f"grype exited with status {returncode}: {stderr.strip() or '(no stderr)'}"
        )
    text = (stdout or "").strip()
    if not text:
        raise ScanError("grype produced no output")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScanError(f"grype output is not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or "matches" not in document:
        raise ScanError("grype output has no 'matches' — the scan did not complete")
    descriptor = document.get("descriptor")
    if not isinstance(descriptor, dict) or not descriptor.get("db"):
        raise ScanError(
            "grype output carries no vulnerability-DB descriptor — the DB did not "
            "load; refusing to treat an unscanned image as clean"
        )
    return summarize(document)
