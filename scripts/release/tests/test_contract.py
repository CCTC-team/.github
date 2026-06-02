"""Tests for the build-target contract checker.

``check_manifest`` decides whether a repo's release-targets manifest declares
every target the contract obliges it to, given the repo's regulatory tier.
The two evidence targets (``validation-docs``, ``sbom``) are required only of
regulated repos; everything else is required of every repo. A declared target
outside the canonical vocabulary is always a problem.
"""

from __future__ import annotations

from release import contract


# Every target the contract obliges of all repos, regardless of tier.
ALL_SCOPE_TARGETS = [
    "clean",
    "restore",
    "build",
    "test",
    "docs",
    "version",
    "package",
    "publish:registry",
    "deploy:staging",
    "verify:staging",
    "functional-tests",
    "tag",
    "deploy:production",
    "verify:production",
]

# Additionally required of regulated repos.
REGULATED_TARGETS = ["validation-docs", "sbom"]


def manifest_with(names):
    """A manifest declaring each named target with a placeholder command."""
    return {"targets": {name: {"run": f"do {name}"} for name in names}}


def complete_regulated_manifest():
    return manifest_with(ALL_SCOPE_TARGETS + REGULATED_TARGETS)


def complete_unregulated_manifest():
    return manifest_with(ALL_SCOPE_TARGETS)


class TestCompleteManifests:
    def test_complete_regulated_manifest_is_ok(self):
        assert contract.check_manifest(
            complete_regulated_manifest(), "gcp-critical"
        ) == []

    def test_unregulated_manifest_without_evidence_targets_is_ok(self):
        # A `none`-tier repo is not obliged to produce a validation report or SBOM.
        assert contract.check_manifest(
            complete_unregulated_manifest(), "none"
        ) == []


class TestMissingMandatoryTargets:
    def test_regulated_missing_sbom_is_flagged(self):
        m = manifest_with(ALL_SCOPE_TARGETS + ["validation-docs"])
        problems = contract.check_manifest(m, "gcp-critical")
        assert "missing mandatory target: sbom" in problems

    def test_regulated_missing_validation_docs_is_flagged(self):
        m = manifest_with(ALL_SCOPE_TARGETS + ["sbom"])
        problems = contract.check_manifest(m, "gcp-critical")
        assert "missing mandatory target: validation-docs" in problems

    def test_missing_tag_is_flagged_for_every_tier(self):
        m = manifest_with(
            [t for t in ALL_SCOPE_TARGETS if t != "tag"] + REGULATED_TARGETS
        )
        assert "missing mandatory target: tag" in contract.check_manifest(
            m, "gcp-critical"
        )
        unreg = manifest_with([t for t in ALL_SCOPE_TARGETS if t != "tag"])
        assert "missing mandatory target: tag" in contract.check_manifest(
            unreg, "none"
        )

    def test_evidence_targets_not_required_for_none_tier(self):
        # Absent validation-docs/sbom must NOT be flagged when the repo is unregulated.
        problems = contract.check_manifest(complete_unregulated_manifest(), "none")
        assert "missing mandatory target: sbom" not in problems
        assert "missing mandatory target: validation-docs" not in problems

    def test_gcp_supporting_is_regulated(self):
        # A non-critical regulated tier still owes the evidence targets.
        problems = contract.check_manifest(
            complete_unregulated_manifest(), "gcp-supporting"
        )
        assert "missing mandatory target: sbom" in problems
        assert "missing mandatory target: validation-docs" in problems


class TestUnknownTargets:
    def test_unknown_target_name_is_flagged(self):
        m = complete_regulated_manifest()
        m["targets"]["frobnicate"] = {"run": "do frobnicate"}
        assert "unknown target: frobnicate" in contract.check_manifest(
            m, "gcp-critical"
        )

    def test_unknown_target_does_not_suppress_missing_report(self):
        m = manifest_with(ALL_SCOPE_TARGETS + ["validation-docs"])
        m["targets"]["frobnicate"] = {"run": "x"}
        problems = contract.check_manifest(m, "gcp-critical")
        assert "missing mandatory target: sbom" in problems
        assert "unknown target: frobnicate" in problems


class TestDeterministicOrdering:
    def test_problems_are_ordered_missing_then_unknown_each_sorted(self):
        # Drop two mandatory targets and add two unknowns, out of alphabetical order.
        kept = [t for t in ALL_SCOPE_TARGETS if t not in ("tag", "build")]
        m = manifest_with(kept + REGULATED_TARGETS)
        m["targets"]["zeta"] = {"run": "x"}
        m["targets"]["alpha"] = {"run": "x"}
        problems = contract.check_manifest(m, "gcp-critical")
        assert problems == [
            "missing mandatory target: build",
            "missing mandatory target: tag",
            "unknown target: alpha",
            "unknown target: zeta",
        ]

    def test_repeated_calls_are_stable(self):
        m = manifest_with(ALL_SCOPE_TARGETS)  # missing both evidence targets
        first = contract.check_manifest(m, "gcp-critical")
        second = contract.check_manifest(m, "gcp-critical")
        assert first == second
