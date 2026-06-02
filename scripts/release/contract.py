"""The build-target contract checker.

Every CCTC repo's build is expected to expose the same set of *logical* build
targets; how it does so (FAKE, MSBuild, npm, Make) is free. A repo declares the
binding in ``.github/release-targets.yml``. This module answers one question
about that manifest: does it declare every target the contract obliges, given
the repo's regulatory tier?

Two targets — ``validation-docs`` and ``sbom`` — are the regulated *evidence*
targets and are required only of regulated repos. Every other canonical target
is required of every repo. A declared target outside the canonical vocabulary
is always a problem (a typo, or a target the contract doesn't recognise).

The full contract — each target's responsibility and the CI-vs-agent split — is
documented in claude-org ``rules/guides/build-and-release.md``; the manifest
shape is ``release-targets.schema.json``.
"""

from __future__ import annotations


# Targets the contract obliges of every repo, in the order they run in a build.
ALL_SCOPE_TARGETS = (
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
)

# Additionally required of regulated repos — the inspector-facing evidence.
REGULATED_TARGETS = (
    "validation-docs",
    "sbom",
)

# The complete canonical vocabulary; any declared key outside it is unknown.
CANONICAL_TARGETS = frozenset(ALL_SCOPE_TARGETS) | frozenset(REGULATED_TARGETS)

# The only tier that is not regulated. Anything else owes the evidence targets.
UNREGULATED_TIER = "none"


def mandatory_targets(regulatory_tier: str) -> frozenset[str]:
    """The targets a repo of this tier must declare."""
    mandatory = set(ALL_SCOPE_TARGETS)
    if regulatory_tier != UNREGULATED_TIER:
        mandatory |= set(REGULATED_TARGETS)
    return frozenset(mandatory)


def check_manifest(manifest: dict, regulatory_tier: str) -> list[str]:
    """Return the contract problems with ``manifest`` for this tier.

    A problem is either a mandatory target the manifest fails to declare, or a
    declared target outside the canonical vocabulary. The returned list is
    deterministic: missing-mandatory problems first (sorted), then unknown-target
    problems (sorted). An empty list means the manifest satisfies the contract.
    """
    declared = set((manifest or {}).get("targets", {}) or {})

    missing = mandatory_targets(regulatory_tier) - declared
    unknown = declared - CANONICAL_TARGETS

    problems = [f"missing mandatory target: {name}" for name in sorted(missing)]
    problems += [f"unknown target: {name}" for name in sorted(unknown)]
    return problems
