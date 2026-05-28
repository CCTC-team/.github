"""Discovery logic for org projects that look like lifecycle boards but
aren't in the config.
"""

from project_enforcement.audit import CANONICAL_LIFECYCLE, discover_unmonitored


def _project(number, options, *, archived=False, name="Sample Lifecycle"):
    return {
        "id": f"PVT_{number}",
        "number": number,
        "title": name,
        "url": f"https://github.com/orgs/CCTC-team/projects/{number}",
        "closed": archived,
        "status_options": list(options),
    }


def _config(numbers):
    return {"projects": [{"owner": "CCTC-team", "number": n} for n in numbers]}


def test_exact_match_in_config_is_not_a_finding():
    org_projects = [_project(31, CANONICAL_LIFECYCLE)]
    findings = discover_unmonitored(org_projects, _config([31]))
    assert findings == []


def test_exact_match_not_in_config_is_a_finding():
    org_projects = [_project(99, CANONICAL_LIFECYCLE)]
    findings = discover_unmonitored(org_projects, _config([31]))
    assert len(findings) == 1
    assert "99" in findings[0].summary or "Lifecycle" in findings[0].summary


def test_superset_not_in_config_is_a_finding():
    options = list(CANONICAL_LIFECYCLE) + ["Custom column"]
    org_projects = [_project(50, options)]
    findings = discover_unmonitored(org_projects, _config([31]))
    assert len(findings) == 1


def test_unrelated_options_not_a_finding():
    org_projects = [_project(99, ["Todo", "Doing", "Done"])]
    findings = discover_unmonitored(org_projects, _config([31]))
    assert findings == []


def test_archived_project_not_a_finding():
    org_projects = [_project(99, CANONICAL_LIFECYCLE, archived=True)]
    findings = discover_unmonitored(org_projects, _config([31]))
    assert findings == []
