"""Summarise grype vulnerability-scan output.

The release workflow runs grype over the SBOM and feeds its JSON here. This is
the pure, testable part: tally findings by severity, decide whether the result
should block a release in `active` mode (any Critical or High), and render a
step-summary markdown block. Running grype, and acting on ``has_blocking``, are
the workflow's job.
"""

from __future__ import annotations

from dataclasses import dataclass

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
