"""Tests for the release-targets manifest accessors.

The release workflow reads a repo's ``.github/release-targets.yml`` through these
helpers rather than parsing YAML inline, so the binding between a canonical
target and the command the workflow runs is defined (and tested) in one place.
"""

from __future__ import annotations

from release import manifest


SAMPLE = {
    "build_tool": "FAKE",
    "version_pin_env": "APP_BUILD_VERSION",
    "image": {
        "registry": "ghcr.io",
        "repository": "cctc-team/trialview",
        "digest_env": "APP_IMAGE_DIGEST",
    },
    "targets": {
        "build": {"run": "dotnet build -c Release"},
        "sbom": {"run": "make sbom", "outputs": ["artifacts/bom.json"]},
        "validation-docs": {
            "run": "make valdocs",
            "outputs": ["docs/validation/*.md"],
        },
    },
}


class TestRunCommand:
    def test_returns_declared_command(self):
        assert manifest.run_command(SAMPLE, "build") == "dotnet build -c Release"

    def test_missing_target_returns_none(self):
        assert manifest.run_command(SAMPLE, "deploy:production") is None


class TestOutputs:
    def test_returns_declared_globs(self):
        assert manifest.outputs(SAMPLE, "sbom") == ["artifacts/bom.json"]

    def test_target_without_outputs_returns_empty(self):
        assert manifest.outputs(SAMPLE, "build") == []

    def test_missing_target_returns_empty(self):
        assert manifest.outputs(SAMPLE, "nope") == []


class TestImageBlock:
    def test_image_ref_joins_registry_and_repository(self):
        assert manifest.image_ref(SAMPLE) == "ghcr.io/cctc-team/trialview"

    def test_digest_env(self):
        assert manifest.digest_env(SAMPLE) == "APP_IMAGE_DIGEST"

    def test_image_helpers_none_when_no_image_block(self):
        no_image = {"targets": {"build": {"run": "x"}}}
        assert manifest.image_ref(no_image) is None
        assert manifest.digest_env(no_image) is None


class TestVersionPinEnv:
    def test_returns_declared_env(self):
        assert manifest.version_pin_env(SAMPLE) == "APP_BUILD_VERSION"

    def test_none_when_absent(self):
        assert manifest.version_pin_env({"targets": {}}) is None
