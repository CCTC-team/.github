"""Released precondition.

A card may enter ``Released`` only when a linked PR has merged into the source
repo's default branch **and** a *published* GitHub Release — carrying the
validation evidence — references that merge commit.

This is deliberately stricter than "a tag or draft exists": a bare tag, a draft
release, or a published release with no validation report attached does **not**
satisfy the gate. The validation report is attached by the release workflow only
when it runs and succeeds, so the gate proves the release pipeline actually ran.

The optional signed-manifest requirement (config flag
``require_signed_manifest``, default off) additionally requires the release to
carry the signed release manifest's detached signature
(``release-manifest.json.sig``). It stays off until the release workflow is
active across the estate.
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

    sha = pr.merge_commit_sha
    release = evidence.published_release_for_sha(repo, sha)
    if release is None:
        reasons.append(
            f"No published Release on `{repo}` references the merge SHA `{sha[:12]}` "
            f"from PR #{pr.number}. A bare tag or a draft release does not satisfy "
            f"Released — the release workflow must run and publish."
        )
        return reasons

    if not release.has_validation_asset:
        reasons.append(
            f"Release `{release.tag}` references the merge SHA `{sha[:12]}` but has no "
            f"validation report attached — the release workflow must run in active "
            f"mode and succeed before this card can reach Released."
        )

    if (ctx.config or {}).get("require_signed_manifest") and not release.has_signed_manifest:
        reasons.append(
            f"Release `{release.tag}` has no signed release manifest "
            f"(`release-manifest.json.sig`), required while `require_signed_manifest` "
            f"is enabled."
        )

    return reasons
