"""Schema contract for the manifest's container-image set.

A repo that ships container images declares them under an ``images`` map keyed
by component name — one entry per independently-deployable image (a UI host, an
API, a docs site, a worker …). These tests pin that contract: a single-image
repo and a multi-image repo are both expressible, a package-only repo may omit
the map entirely, and a malformed entry is rejected.

Validation uses the ``jsonschema`` library against the actual schema document,
mirroring the runtime validation the org performs with the check-jsonschema CLI.
"""

from __future__ import annotations

import json
import os

from jsonschema import Draft202012Validator

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "release-targets.schema.json"
)


def _validator() -> Draft202012Validator:
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _manifest(images):
    """A minimal valid manifest, optionally carrying an ``images`` map."""
    m = {"targets": {"build": {"run": "dotnet build -c Release"}}}
    if images is not None:
        m["images"] = images
    return m


def _entry(repository, digest_env, **extra):
    return {"registry": "ghcr.io", "repository": repository, "digest_env": digest_env, **extra}


TWO_IMAGES = {
    "trialview": _entry("cctc-team/trialview", "TRIALVIEW_IMAGE_DIGEST"),
    "trialview-api": _entry("cctc-team/trialview-api", "TRIALVIEW_API_IMAGE_DIGEST"),
}
ONE_IMAGE = {"gtg-web": _entry("cctc-team/gtg-web", "GTG_WEB_IMAGE_DIGEST")}


class TestImagesMap:
    def test_two_entry_map_is_valid(self):
        assert _validator().is_valid(_manifest(TWO_IMAGES))

    def test_one_entry_map_is_valid(self):
        assert _validator().is_valid(_manifest(ONE_IMAGE))

    def test_no_images_key_is_valid_for_package_repos(self):
        assert _validator().is_valid(_manifest(None))

    def test_empty_images_map_is_invalid(self):
        assert not _validator().is_valid(_manifest({}))

    def test_entry_missing_digest_env_is_invalid(self):
        bad = {"trialview": {"registry": "ghcr.io", "repository": "cctc-team/trialview"}}
        assert not _validator().is_valid(_manifest(bad))

    def test_entry_with_unknown_property_is_invalid(self):
        bad = {"trialview": _entry("cctc-team/trialview", "D", bogus=1)}
        assert not _validator().is_valid(_manifest(bad))

    def test_optional_sbom_globs_are_allowed(self):
        ok = {"trialview": _entry("cctc-team/trialview", "D", sbom=["bom/trialview.cdx.json"])}
        assert _validator().is_valid(_manifest(ok))

    def test_legacy_singular_image_key_is_rejected(self):
        m = _manifest(None)
        m["image"] = {"registry": "ghcr.io", "repository": "cctc-team/trialview", "digest_env": "D"}
        assert not _validator().is_valid(m)
