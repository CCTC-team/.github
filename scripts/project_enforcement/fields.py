"""Resolve a project's field metadata to a name → FieldRef map.

Project field IDs are project-scoped — cloning the test board to production
gives every field a fresh ID. The handler therefore looks fields up by name
at the start of each run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class FieldRef:
    id: str
    name: str
    data_type: str
    options: Optional[dict[str, str]] = None  # single-select: option name → option id


def resolve_fields(
    project_json: dict,
    required: Sequence[str] = (),
) -> dict[str, FieldRef]:
    """Return name → FieldRef for every field on the project.

    `project_json` is the dict returned by ``snapshot.fetch_project``;
    ``fields_meta`` carries the raw GraphQL nodes keyed by name.

    Raises KeyError naming any missing required field.
    """

    raw = (project_json or {}).get("fields_meta") or {}
    resolved: dict[str, FieldRef] = {}
    for name, node in raw.items():
        options = None
        if node.get("dataType") == "SINGLE_SELECT" or node.get("__typename") == "ProjectV2SingleSelectField":
            opts = node.get("options") or []
            options = {opt["name"]: opt["id"] for opt in opts}
        resolved[name] = FieldRef(
            id=node["id"],
            name=name,
            data_type=node.get("dataType") or "UNKNOWN",
            options=options,
        )

    missing = [r for r in required if r not in resolved]
    if missing:
        raise KeyError(
            f"Project is missing required field(s): {', '.join(missing)}. "
            f"Have: {', '.join(sorted(resolved)) or '<none>'}"
        )

    return resolved
