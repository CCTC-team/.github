"""Tests for the grype-output summariser.

The release workflow runs grype over the SBOM and pipes its JSON here. This
module is the pure part: count vulnerabilities by severity, decide whether the
result blocks an `active` release (any critical or high), and render a
step-summary block. Invoking grype itself stays in the workflow.
"""

from __future__ import annotations

from release import sbom_scan


def grype(*severities):
    """A minimal grype JSON document with one match per given severity."""
    return {
        "matches": [
            {
                "vulnerability": {"id": f"CVE-2026-{i:04d}", "severity": sev},
                "artifact": {"name": "libfoo", "version": "1.0"},
            }
            for i, sev in enumerate(severities)
        ]
    }


class TestCounts:
    def test_clean_report_has_no_blocking_findings(self):
        result = sbom_scan.summarize(grype())
        assert result.critical == 0
        assert result.high == 0
        assert result.total == 0
        assert result.has_blocking is False

    def test_high_severity_counts_and_blocks(self):
        result = sbom_scan.summarize(grype("High", "High", "Medium"))
        assert result.high == 2
        assert result.medium == 1
        assert result.critical == 0
        assert result.total == 3
        assert result.has_blocking is True

    def test_critical_severity_counts_and_blocks(self):
        result = sbom_scan.summarize(grype("Critical", "Low"))
        assert result.critical == 1
        assert result.low == 1
        assert result.has_blocking is True

    def test_severity_matching_is_case_insensitive(self):
        result = sbom_scan.summarize(grype("critical", "HIGH"))
        assert result.critical == 1
        assert result.high == 1

    def test_unknown_severity_bucketed_not_dropped(self):
        result = sbom_scan.summarize(grype("Frobnitz"))
        assert result.total == 1
        assert result.unknown == 1
        assert result.has_blocking is False


class TestMarkdown:
    def test_markdown_reports_counts(self):
        md = sbom_scan.summarize(grype("Critical", "High", "Medium")).markdown
        assert "1" in md and "Critical" in md and "High" in md
        assert "Vulnerability scan" in md

    def test_clean_markdown_is_reassuring(self):
        md = sbom_scan.summarize(grype()).markdown
        assert "No known vulnerabilities" in md
