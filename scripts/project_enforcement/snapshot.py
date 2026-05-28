"""Project-state snapshot + diff.

A snapshot is `{ "items": { item_id: { content_id, content_type,
source_repo, fields: { name: value } } } }`. The handler fetches the
current state via GraphQL, loads the prior snapshot from the
`_project-state` branch, computes a diff, and dispatches one
`CardChange` per detected change.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional


CardKind = Literal["added", "removed", "field_change"]
ContentType = Literal["issue", "pull_request", "draft"]


@dataclass(frozen=True)
class CardChange:
    item_id: str
    content_id: Optional[str]
    content_type: Optional[ContentType]
    source_repo: Optional[str]
    kind: CardKind
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None


def compute_diff(old: dict, new: dict) -> list[CardChange]:
    """Return one CardChange per added/removed item and per changed field."""

    old_items = (old or {}).get("items", {}) or {}
    new_items = (new or {}).get("items", {}) or {}

    changes: list[CardChange] = []

    for item_id in sorted(set(new_items) - set(old_items)):
        meta = new_items[item_id]
        changes.append(
            CardChange(
                item_id=item_id,
                content_id=meta.get("content_id"),
                content_type=meta.get("content_type"),
                source_repo=meta.get("source_repo"),
                kind="added",
            )
        )

    for item_id in sorted(set(old_items) - set(new_items)):
        meta = old_items[item_id]
        changes.append(
            CardChange(
                item_id=item_id,
                content_id=meta.get("content_id"),
                content_type=meta.get("content_type"),
                source_repo=meta.get("source_repo"),
                kind="removed",
            )
        )

    for item_id in sorted(set(old_items) & set(new_items)):
        old_meta = old_items[item_id]
        new_meta = new_items[item_id]
        old_fields = old_meta.get("fields") or {}
        new_fields = new_meta.get("fields") or {}
        for field_name in sorted(set(old_fields) | set(new_fields)):
            old_value = old_fields.get(field_name)
            new_value = new_fields.get(field_name)
            if old_value == new_value:
                continue
            changes.append(
                CardChange(
                    item_id=item_id,
                    # Prefer the newer metadata when present — captures
                    # renames/re-links without losing identity on removal.
                    content_id=new_meta.get("content_id") or old_meta.get("content_id"),
                    content_type=new_meta.get("content_type") or old_meta.get("content_type"),
                    source_repo=new_meta.get("source_repo") or old_meta.get("source_repo"),
                    kind="field_change",
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                )
            )

    return changes


_PROJECT_QUERY = """
query($owner: String!, $number: Int!, $cursor: String) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      title
      fields(first: 50) {
        nodes {
          __typename
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField {
            id name dataType
            options { id name }
          }
        }
      }
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          type
          updatedAt
          content {
            __typename
            ... on Issue        { id number title repository { nameWithOwner } }
            ... on PullRequest  { id number title repository { nameWithOwner } }
            ... on DraftIssue   { id title }
          }
          fieldValues(first: 50) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldTextValue   { text   field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldDateValue   { date   field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldIterationValue    { title field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldUserValue {
                users(first: 10) { nodes { login } }
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""


def _gh_graphql(query: str, variables: dict) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        flag = "-F" if isinstance(value, int) else "-f"
        args += [flag, f"{key}={value}"]
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _content_type(typename: Optional[str]) -> Optional[ContentType]:
    if typename == "Issue":
        return "issue"
    if typename == "PullRequest":
        return "pull_request"
    if typename == "DraftIssue":
        return "draft"
    return None


def _field_value(node: dict) -> tuple[Optional[str], Any]:
    field_meta = node.get("field") or {}
    name = field_meta.get("name")
    typename = node.get("__typename")
    if name is None:
        return None, None
    if typename == "ProjectV2ItemFieldTextValue":
        return name, node.get("text")
    if typename == "ProjectV2ItemFieldNumberValue":
        return name, node.get("number")
    if typename == "ProjectV2ItemFieldDateValue":
        return name, node.get("date")
    if typename == "ProjectV2ItemFieldSingleSelectValue":
        return name, node.get("name")
    if typename == "ProjectV2ItemFieldIterationValue":
        return name, node.get("title")
    if typename == "ProjectV2ItemFieldUserValue":
        logins = [u["login"] for u in (node.get("users") or {}).get("nodes", [])]
        return name, ",".join(logins) if logins else None
    return name, None


def fetch_project(owner: str, number: int, graphql: Optional[callable] = None) -> dict:
    """Fetch every item + field value for a ProjectV2; paginate."""

    runner = graphql or _gh_graphql
    items: dict[str, dict] = {}
    fields_meta: dict[str, dict] = {}
    cursor: Optional[str] = None
    title: Optional[str] = None
    project_id: Optional[str] = None

    while True:
        payload = runner(_PROJECT_QUERY, {"owner": owner, "number": number, "cursor": cursor})
        project = (payload.get("data") or {}).get("organization", {}).get("projectV2")
        if not project:
            raise RuntimeError(f"projectV2(owner={owner}, number={number}) returned no data")
        title = project.get("title")
        project_id = project.get("id")
        for field_node in (project.get("fields") or {}).get("nodes", []) or []:
            if not field_node:
                continue
            fields_meta[field_node["name"]] = field_node

        items_block = project.get("items") or {}
        for node in items_block.get("nodes", []) or []:
            content = node.get("content") or {}
            repo = (content.get("repository") or {}).get("nameWithOwner")
            field_values = {}
            for fv in (node.get("fieldValues") or {}).get("nodes", []) or []:
                name, value = _field_value(fv)
                if name is None:
                    continue
                field_values[name] = value
            items[node["id"]] = {
                "content_id": content.get("id"),
                "content_type": _content_type(content.get("__typename")),
                "source_repo": repo,
                "number": content.get("number"),
                "title": content.get("title"),
                "updated_at": (node.get("updatedAt") or "")[:10] or None,
                "fields": field_values,
            }

        page = items_block.get("pageInfo") or {}
        if page.get("hasNextPage"):
            cursor = page.get("endCursor")
            continue
        break

    return {
        "project_id": project_id,
        "owner": owner,
        "number": number,
        "title": title,
        "items": items,
        "fields_meta": fields_meta,
    }


def load_snapshot(path: str) -> dict:
    if not os.path.exists(path):
        return {"items": {}}
    with open(path) as f:
        return json.load(f)


def write_snapshot(path: str, snapshot: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Sort keys so the on-branch diff is human-inspectable.
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)
        f.write("\n")
