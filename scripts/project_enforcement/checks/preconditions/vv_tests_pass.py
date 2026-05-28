"""V&V tests pass precondition.

Linked PR's gxp-traceability and compliance check runs green on the
latest head SHA, and the issue's Feature link URL resolves to a
.feature path on the source repo's default branch.
"""

from __future__ import annotations

from project_enforcement.body_parser import extract_field


def check(item_meta, ctx, evidence) -> list[str]:
    reasons: list[str] = []
    repo = item_meta.get("source_repo")
    number = item_meta.get("number")
    if not repo or not number:
        return ["Card has no linked source issue."]

    prs = evidence.linked_prs(repo, number)
    candidate = next((p for p in prs if p.state in ("OPEN", "MERGED")), None)
    if candidate is None:
        return [f"No linked PR on `{repo}` for issue #{number}."]

    rollup = (candidate.check_runs or {}).get("rollup", "")
    if rollup not in ("SUCCESS",):
        reasons.append(
            f"PR #{candidate.number} on `{repo}` has check status `{rollup or 'unknown'}`. "
            "gxp-traceability and compliance must both be green on the latest head."
        )

    issue = evidence.issue(repo, number)
    if issue is None:
        reasons.append(f"Could not read source issue {repo}#{number}.")
        return reasons

    feature_link = (extract_field(issue.body, "Feature link:") or "").strip()
    if not feature_link:
        reasons.append("`Feature link:` on the issue is empty.")
        return reasons

    default = evidence.default_branch(repo)
    for url in [line.strip() for line in feature_link.splitlines() if line.strip()]:
        if not url.endswith(".feature"):
            reasons.append(f"Feature link `{url}` does not point at a `.feature` file.")
            continue
        if f"/blob/{default}/" not in url:
            reasons.append(
                f"Feature link `{url}` is not on `{repo}`'s default branch (`{default}`)."
            )
            continue
        if not evidence.url_exists(url):
            reasons.append(f"Feature link `{url}` does not resolve (HEAD failed).")

    return reasons
