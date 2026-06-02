"""Read a repo's release-targets manifest.

The reusable release workflow binds canonical build targets to a repo's actual
commands purely through ``.github/release-targets.yml`` (schema:
``release-targets.schema.json``). These accessors are the one place that knows
the manifest's shape, so the workflow never parses it inline and the binding is
unit-tested.

A small CLI (``python -m release.manifest …``) exposes the same accessors to the
workflow's shell steps.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

import yaml


def load(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _target(manifest: dict, name: str) -> dict:
    return ((manifest or {}).get("targets") or {}).get(name) or {}


def run_command(manifest: dict, target: str) -> Optional[str]:
    """The command the workflow runs for ``target``, or None if undeclared."""
    return _target(manifest, target).get("run")


def outputs(manifest: dict, target: str) -> list[str]:
    """Declared output globs for ``target`` (empty if none / target absent)."""
    return list(_target(manifest, target).get("outputs") or [])


def _images(manifest: dict) -> dict:
    return (manifest or {}).get("images") or {}


def component_names(manifest: dict) -> list[str]:
    """Sorted names of the component images this repo ships (empty if none)."""
    return sorted(_images(manifest).keys())


def _component(manifest: dict, name: str) -> dict:
    return _images(manifest).get(name) or {}


def component_ref(manifest: dict, name: str) -> Optional[str]:
    """``<registry>/<repository>`` for one component image, or None if unknown."""
    img = _component(manifest, name)
    registry = img.get("registry")
    repository = img.get("repository")
    if registry and repository:
        return f"{registry}/{repository}"
    return None


def component_digest_env(manifest: dict, name: str) -> Optional[str]:
    """The env var the build stamps this component's pushed digest into."""
    return _component(manifest, name).get("digest_env") or None


def component_sbom_globs(manifest: dict, name: str) -> list[str]:
    """Declared SBOM output glob(s) for this component image (empty if none)."""
    return list(_component(manifest, name).get("sbom") or [])


def version_pin_env(manifest: dict) -> Optional[str]:
    return (manifest or {}).get("version_pin_env")


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read a release-targets manifest.")
    parser.add_argument("--manifest", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", metavar="TARGET", help="Print the target's run command.")
    group.add_argument("--outputs", metavar="TARGET", help="Print the target's output globs, one per line.")
    group.add_argument("--list-components", action="store_true", help="Print component image names, one per line (sorted).")
    group.add_argument("--component-ref", metavar="NAME", help="Print one component's <registry>/<repository>.")
    group.add_argument("--component-digest-env", metavar="NAME", help="Print one component's digest env var name.")
    group.add_argument("--component-sbom", metavar="NAME", help="Print one component's SBOM output globs, one per line.")
    group.add_argument("--version-pin-env", action="store_true", help="Print the version-pin env var name.")
    args = parser.parse_args(argv)

    m = load(args.manifest)

    if args.run is not None:
        cmd = run_command(m, args.run)
        if cmd is None:
            print(f"target '{args.run}' is not declared in the manifest", file=sys.stderr)
            return 3
        print(cmd)
        return 0
    if args.outputs is not None:
        for glob in outputs(m, args.outputs):
            print(glob)
        return 0
    if args.list_components:
        for name in component_names(m):
            print(name)
        return 0
    if args.component_sbom is not None:
        for glob in component_sbom_globs(m, args.component_sbom):
            print(glob)
        return 0

    value = None
    if args.component_ref is not None:
        value = component_ref(m, args.component_ref)
    elif args.component_digest_env is not None:
        value = component_digest_env(m, args.component_digest_env)
    elif args.version_pin_env:
        value = version_pin_env(m)

    if not value:
        return 3
    print(value)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
