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


def _image(manifest: dict) -> dict:
    return (manifest or {}).get("image") or {}


def image_ref(manifest: dict) -> Optional[str]:
    """``<registry>/<repository>`` for hosted apps, or None if no image block."""
    img = _image(manifest)
    registry = img.get("registry")
    repository = img.get("repository")
    if registry and repository:
        return f"{registry}/{repository}"
    return None


def digest_env(manifest: dict) -> Optional[str]:
    return _image(manifest).get("digest_env")


def version_pin_env(manifest: dict) -> Optional[str]:
    return (manifest or {}).get("version_pin_env")


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read a release-targets manifest.")
    parser.add_argument("--manifest", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", metavar="TARGET", help="Print the target's run command.")
    group.add_argument("--outputs", metavar="TARGET", help="Print the target's output globs, one per line.")
    group.add_argument("--image-ref", action="store_true", help="Print <registry>/<repository>.")
    group.add_argument("--digest-env", action="store_true", help="Print the image digest env var name.")
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

    value = None
    if args.image_ref:
        value = image_ref(m)
    elif args.digest_env:
        value = digest_env(m)
    elif args.version_pin_env:
        value = version_pin_env(m)

    if not value:
        return 3
    print(value)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
