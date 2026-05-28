"""Side-effect operations the checks invoke.

Wraps GitHub mutations and queries so they can be stubbed in tests.
The default implementation shells out to `gh` (already authenticated
via GH_TOKEN in the workflow).

The actions class deliberately exposes a narrow surface — checks are
not allowed to invent new GitHub side-effects beyond the four below.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Protocol


class ActionsLike(Protocol):
    def post_comment(self, repo: str, number: int, body: str) -> None: ...
    def apply_label(self, repo: str, number: int, label: str) -> None: ...
    def remove_label(self, repo: str, number: int, label: str) -> None: ...
    def revert_single_select(
        self, project_id: str, item_id: str, field_id: str, option_id: str
    ) -> None: ...
    def user_exists(self, login: str) -> bool: ...


class GhActions:
    """Shells out to `gh`. Each call assumes GH_TOKEN is set."""

    def post_comment(self, repo: str, number: int, body: str) -> None:
        subprocess.run(
            ["gh", "issue", "comment", str(number), "-R", repo, "--body", body],
            check=True,
        )

    def apply_label(self, repo: str, number: int, label: str) -> None:
        subprocess.run(
            ["gh", "issue", "edit", str(number), "-R", repo, "--add-label", label],
            check=True,
        )

    def remove_label(self, repo: str, number: int, label: str) -> None:
        subprocess.run(
            ["gh", "issue", "edit", str(number), "-R", repo, "--remove-label", label],
            check=True,
        )

    def revert_single_select(
        self, project_id: str, item_id: str, field_id: str, option_id: str
    ) -> None:
        mutation = """
        mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
          updateProjectV2ItemFieldValue(
            input: { projectId: $project, itemId: $item, fieldId: $field,
                     value: { singleSelectOptionId: $option } }
          ) { projectV2Item { id } }
        }
        """
        subprocess.run(
            [
                "gh", "api", "graphql",
                "-f", f"query={mutation}",
                "-f", f"project={project_id}",
                "-f", f"item={item_id}",
                "-f", f"field={field_id}",
                "-f", f"option={option_id}",
            ],
            check=True,
        )

    def user_exists(self, login: str) -> bool:
        result = subprocess.run(
            ["gh", "api", f"/users/{login}", "--silent"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


@dataclass
class RecordingActions:
    """Test double — records every call without touching GitHub."""

    comments: list[tuple[str, int, str]] = field(default_factory=list)
    labels_added: list[tuple[str, int, str]] = field(default_factory=list)
    labels_removed: list[tuple[str, int, str]] = field(default_factory=list)
    field_writes: list[tuple[str, str, str, str]] = field(default_factory=list)
    known_users: set[str] = field(default_factory=set)

    def post_comment(self, repo, number, body):
        self.comments.append((repo, number, body))

    def apply_label(self, repo, number, label):
        self.labels_added.append((repo, number, label))

    def remove_label(self, repo, number, label):
        self.labels_removed.append((repo, number, label))

    def revert_single_select(self, project_id, item_id, field_id, option_id):
        self.field_writes.append((project_id, item_id, field_id, option_id))

    def user_exists(self, login):
        return login in self.known_users
