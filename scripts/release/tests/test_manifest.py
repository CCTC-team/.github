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
    "images": {
        "trialview": {
            "registry": "ghcr.io",
            "repository": "cctc-team/trialview",
            "digest_env": "TRIALVIEW_IMAGE_DIGEST",
            "sbom": ["bom/trialview.cdx.json"],
        },
        "trialview-api": {
            "registry": "ghcr.io",
            "repository": "cctc-team/trialview-api",
            "digest_env": "TRIALVIEW_API_IMAGE_DIGEST",
        },
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


NO_IMAGES = {"targets": {"build": {"run": "x"}}}


class TestComponents:
    def test_component_names_are_sorted(self):
        assert manifest.component_names(SAMPLE) == ["trialview", "trialview-api"]

    def test_component_names_empty_when_no_images(self):
        assert manifest.component_names(NO_IMAGES) == []

    def test_component_ref_joins_registry_and_repository(self):
        assert manifest.component_ref(SAMPLE, "trialview") == "ghcr.io/cctc-team/trialview"
        assert manifest.component_ref(SAMPLE, "trialview-api") == "ghcr.io/cctc-team/trialview-api"

    def test_component_ref_none_for_unknown(self):
        assert manifest.component_ref(SAMPLE, "nope") is None

    def test_component_digest_env(self):
        assert manifest.component_digest_env(SAMPLE, "trialview") == "TRIALVIEW_IMAGE_DIGEST"
        assert manifest.component_digest_env(SAMPLE, "trialview-api") == "TRIALVIEW_API_IMAGE_DIGEST"

    def test_component_digest_env_none_for_unknown(self):
        assert manifest.component_digest_env(SAMPLE, "nope") is None

    def test_component_sbom_globs(self):
        assert manifest.component_sbom_globs(SAMPLE, "trialview") == ["bom/trialview.cdx.json"]

    def test_component_sbom_globs_empty_when_absent(self):
        assert manifest.component_sbom_globs(SAMPLE, "trialview-api") == []


class TestCli:
    def _write(self, tmp_path):
        import yaml

        p = tmp_path / "release-targets.yml"
        p.write_text(yaml.safe_dump(SAMPLE))
        return str(p)

    def test_list_components_sorted_one_per_line(self, tmp_path, capsys):
        rc = manifest._main(["--manifest", self._write(tmp_path), "--list-components"])
        assert rc == 0
        assert capsys.readouterr().out.split() == ["trialview", "trialview-api"]

    def test_component_ref_cli(self, tmp_path, capsys):
        rc = manifest._main(
            ["--manifest", self._write(tmp_path), "--component-ref", "trialview-api"]
        )
        assert rc == 0
        assert capsys.readouterr().out.strip() == "ghcr.io/cctc-team/trialview-api"

    def test_component_digest_env_cli(self, tmp_path, capsys):
        rc = manifest._main(
            ["--manifest", self._write(tmp_path), "--component-digest-env", "trialview"]
        )
        assert rc == 0
        assert capsys.readouterr().out.strip() == "TRIALVIEW_IMAGE_DIGEST"

    def test_unknown_component_ref_cli_nonzero(self, tmp_path, capsys):
        rc = manifest._main(
            ["--manifest", self._write(tmp_path), "--component-ref", "nope"]
        )
        assert rc == 3


class TestVersionPinEnv:
    def test_returns_declared_env(self):
        assert manifest.version_pin_env(SAMPLE) == "APP_BUILD_VERSION"

    def test_none_when_absent(self):
        assert manifest.version_pin_env({"targets": {}}) is None
