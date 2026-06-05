"""Tests for the grype-output summariser.

The release workflow runs grype over the SBOM and pipes its JSON here. This
module is the pure part: validate that grype actually completed (so a scanner
failure can never read as a clean image), count vulnerabilities by severity,
decide whether the result blocks an `active` release (any critical or high), and
render a step-summary block. Invoking grype itself stays in the workflow.
"""

from __future__ import annotations

import json

import pytest

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


def grype_run(*severities, db=True):
    """A full `grype -o json` document: matches plus the run descriptor.

    A real grype run always emits a ``descriptor`` carrying the vulnerability-DB
    status. Omitting it (``db=False``) models the failure mode where the DB never
    loaded — which must be rejected, not read as a clean image.
    """
    doc = grype(*severities)
    descriptor = {"name": "grype", "version": "0.0.0"}
    if db:
        descriptor["db"] = {"status": "valid", "schemaVersion": 5}
    doc["descriptor"] = descriptor
    return doc


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


class TestLoad:
    """`load` is fail-closed: it returns a ScanResult only for a grype run that
    actually completed. A scanner failure (non-zero exit, empty/garbage output,
    or a document with no DB descriptor) raises ScanError instead of being
    silently counted as a clean image."""

    def test_completed_scan_with_findings_counts_and_blocks(self):
        result = sbom_scan.load(json.dumps(grype_run("Critical", "High", "Low")))
        assert result.critical == 1
        assert result.high == 1
        assert result.low == 1
        assert result.has_blocking is True

    def test_genuinely_clean_scan_passes(self):
        # DB loaded, zero matches — a real clean image must NOT raise.
        result = sbom_scan.load(json.dumps(grype_run()))
        assert result.total == 0
        assert result.has_blocking is False

    def test_nonzero_exit_raises(self):
        with pytest.raises(sbom_scan.ScanError):
            sbom_scan.load("", returncode=1, stderr="failed to load vulnerability db")

    def test_empty_output_raises(self):
        with pytest.raises(sbom_scan.ScanError):
            sbom_scan.load("", returncode=0)

    def test_empty_json_object_raises(self):
        # The old `stdout or "{}"` fallback used to read as clean — it must not.
        with pytest.raises(sbom_scan.ScanError):
            sbom_scan.load("{}", returncode=0)

    def test_garbage_output_raises(self):
        with pytest.raises(sbom_scan.ScanError):
            sbom_scan.load("not json at all", returncode=0)

    def test_missing_db_descriptor_raises(self):
        # Matches present but no DB ever loaded — fail closed, do not read clean.
        with pytest.raises(sbom_scan.ScanError):
            sbom_scan.load(json.dumps(grype_run("High", db=False)))
