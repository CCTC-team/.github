"""Behaviour of evidence._pr_from_graphql.

Confirms that failed_check_runs_history is True when any commit on the
PR has a tracked check-run (gxp-traceability, compliance, gate) with a
failing conclusion in its history — even if the head commit is now
green. The QA-approved precondition uses this to decide whether a
Deviation Ref is required.
"""

from project_enforcement.evidence import _pr_from_graphql, _select_published_release


def _pr(commit_check_runs):
    """Build a minimal GraphQL PR fixture with one commit carrying the given check-runs."""
    return {
        "number": 99,
        "state": "OPEN",
        "merged": False,
        "headRefOid": "abc",
        "baseRefName": "main",
        "repository": {"nameWithOwner": "CCTC-team/sample"},
        "statusCheckRollup": {"state": "SUCCESS"},
        "commits": {
            "nodes": [{
                "commit": {
                    "author": {"user": {"login": "alice"}},
                    "checkSuites": {
                        "nodes": [{
                            "checkRuns": {"nodes": list(commit_check_runs)},
                        }],
                    },
                },
            }],
        },
    }


def test_clean_history_keeps_flag_false():
    pr = _pr([
        {"name": "gxp-traceability / gate", "conclusion": "SUCCESS"},
        {"name": "compliance / check", "conclusion": "SUCCESS"},
    ])
    linked = _pr_from_graphql(pr, "CCTC-team/sample")
    assert linked.failed_check_runs_history is False


def test_failing_gxp_run_flips_flag_true():
    pr = _pr([
        {"name": "gxp-traceability / gate", "conclusion": "FAILURE"},
        {"name": "compliance / check", "conclusion": "SUCCESS"},
    ])
    linked = _pr_from_graphql(pr, "CCTC-team/sample")
    assert linked.failed_check_runs_history is True


def test_failing_compliance_run_flips_flag_true():
    pr = _pr([{"name": "compliance / validate", "conclusion": "FAILURE"}])
    linked = _pr_from_graphql(pr, "CCTC-team/sample")
    assert linked.failed_check_runs_history is True


def test_failing_unrelated_check_does_not_flip_flag():
    pr = _pr([{"name": "build / lint", "conclusion": "FAILURE"}])
    linked = _pr_from_graphql(pr, "CCTC-team/sample")
    assert linked.failed_check_runs_history is False


def test_substring_lookalikes_do_not_flip_flag():
    # The "gate" token must not match "aggregate" or "investigate"; the
    # "compliance" token must not match a hypothetical "compliance-helper"
    # by accident; "gxp-traceability" should still match when surrounded
    # by punctuation.
    for name in (
        "aggregate-coverage / report",
        "investigate-flake / job",
        "generate-sbom / sign",
        "compliance-utils / build",  # NOT a tracked check, just adjacent
        "navigate-to-staging / smoke",
    ):
        pr = _pr([{"name": name, "conclusion": "FAILURE"}])
        linked = _pr_from_graphql(pr, "CCTC-team/sample")
        assert linked.failed_check_runs_history is False, f"false positive on {name}"


def test_tracked_name_matches_through_workflow_separators():
    # The natural rendering is "<workflow> / <job>"; the job side often is
    # exactly "gate", and the workflow side is exactly "gxp-traceability".
    for name in (
        "gxp-traceability / gate",
        "GxP-Traceability / Gate",  # case-insensitive
        "compliance / validate",
        "Project / gxp-traceability",
    ):
        pr = _pr([{"name": name, "conclusion": "FAILURE"}])
        linked = _pr_from_graphql(pr, "CCTC-team/sample")
        assert linked.failed_check_runs_history is True, f"missed {name}"


def test_cancelled_and_timed_out_count_as_failures():
    pr_cancelled = _pr([{"name": "gxp-traceability / gate", "conclusion": "CANCELLED"}])
    pr_timeout = _pr([{"name": "gxp-traceability / gate", "conclusion": "TIMED_OUT"}])
    assert _pr_from_graphql(pr_cancelled, "CCTC-team/sample").failed_check_runs_history is True
    assert _pr_from_graphql(pr_timeout, "CCTC-team/sample").failed_check_runs_history is True


def test_pending_run_does_not_flip_flag():
    pr = _pr([{"name": "gxp-traceability / gate", "conclusion": None}])
    linked = _pr_from_graphql(pr, "CCTC-team/sample")
    assert linked.failed_check_runs_history is False


def test_commit_authors_aggregated():
    pr = _pr([])
    pr["commits"]["nodes"].append({
        "commit": {
            "author": {"user": {"login": "bob"}},
            "checkSuites": {"nodes": []},
        },
    })
    linked = _pr_from_graphql(pr, "CCTC-team/sample")
    assert linked.commit_authors == ["alice", "bob"]


# --- _select_published_release ---------------------------------------------
#
# The hardened Released gate accepts only a *published* Release whose tag
# resolves (via the tag ref, not a target_commitish string) to the merge SHA.
# A draft, a bare tag, or a release whose tag points elsewhere is not a match.
# The validation-report asset is reported on the meta, not used as a filter, so
# the precondition can give a precise "references the SHA but has no report"
# reason.

SHA = "deadbeefcafe"


def _release(tag, *, draft=False, assets=()):
    return {
        "tag_name": tag,
        "draft": draft,
        "html_url": f"https://github.com/CCTC-team/sample/releases/tag/{tag}",
        "assets": [{"name": n} for n in assets],
    }


def test_draft_release_is_not_selected():
    releases = [_release("v1.0.0", draft=True, assets=["validation-report.md"])]
    assert _select_published_release(releases, {"v1.0.0": SHA}, SHA) is None


def test_bare_tag_with_no_release_is_not_selected():
    # The tag resolves to the SHA, but there is no Release object for it.
    assert _select_published_release([], {"v1.0.0": SHA}, SHA) is None


def test_published_release_without_validation_asset_returns_meta_flagged_false():
    releases = [_release("v1.0.0", assets=["app.zip"])]
    meta = _select_published_release(releases, {"v1.0.0": SHA}, SHA)
    assert meta is not None
    assert meta.tag == "v1.0.0"
    assert meta.sha == SHA
    assert meta.has_validation_asset is False


def test_published_release_with_validation_asset_returns_meta_flagged_true():
    releases = [_release("v1.0.0", assets=["validation-report.md", "bom.json"])]
    meta = _select_published_release(releases, {"v1.0.0": SHA}, SHA)
    assert meta is not None
    assert meta.has_validation_asset is True


def test_release_tag_resolving_to_other_sha_is_not_selected():
    # target_commitish string-matching would wrongly accept this; tag-ref
    # resolution must not, because the tag points at a different commit.
    releases = [_release("v1.0.0", assets=["validation-report.md"])]
    assert _select_published_release(releases, {"v1.0.0": "othersha"}, SHA) is None
