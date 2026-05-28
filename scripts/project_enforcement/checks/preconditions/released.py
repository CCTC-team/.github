"""Released precondition.

Linked PR merged into the source repo's default branch, and a release
tag/draft referencing the merge SHA exists on the source repo.
"""

from __future__ import annotations


def check(item_meta, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    repo = item_meta.get("source_repo")
    number = item_meta.get("number")
    if not repo or not number:
        return ["Card has no linked source issue."]

    prs = evidence.linked_prs(repo, number)
    default = evidence.default_branch(repo)
    merged_to_default = [p for p in prs if p.merged and p.base_ref == default]
    if not merged_to_default:
        reasons.append(
            f"No linked PR has merged into `{repo}`'s default branch (`{default}`)."
        )
        return reasons

    pr = merged_to_default[0]
    if not pr.merge_commit_sha:
        reasons.append(f"Linked merged PR #{pr.number} has no merge commit SHA.")
        return reasons

    if not evidence.release_for_sha(repo, pr.merge_commit_sha):
        reasons.append(
            f"No release or tag on `{repo}` references the merge SHA `{pr.merge_commit_sha[:12]}` "
            f"from PR #{pr.number}."
        )

    return reasons
