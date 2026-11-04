import pytest

from evaluator.signals import (
    OK,
    RISK,
    UNKNOWN,
    WATCH,
    activity_signal,
    build_signals,
    bus_factor_signal,
    issues_signal,
    license_signal,
    releases_signal,
    status_signal,
)
from evaluator.tests.factories import NOW, iso, make_commit, make_issue, make_release, make_repo


def test_archived_repo_is_a_risk():
    assert status_signal(make_repo(archived=True)).status == RISK


def test_repo_that_is_not_archived_is_ok():
    assert status_signal(make_repo()).status == OK


@pytest.mark.parametrize(
    "license_info, expected",
    [
        (None, RISK),
        ({"spdx_id": "MIT", "name": "MIT License"}, OK),
        ({"spdx_id": "Apache-2.0", "name": "Apache License 2.0"}, OK),
        ({"spdx_id": "AGPL-3.0", "name": "GNU Affero General Public License v3.0"}, WATCH),
        ({"spdx_id": "NOASSERTION", "name": "Other"}, WATCH),
    ],
)
def test_license_rules(license_info, expected):
    assert license_signal(make_repo(license=license_info)).status == expected


def test_custom_license_is_shown_as_custom():
    signal = license_signal(make_repo(license={"spdx_id": "NOASSERTION", "name": "Other"}))
    assert signal.value == "Custom"


@pytest.mark.parametrize("days_ago, expected", [(1, OK), (90, OK), (91, WATCH), (365, WATCH), (366, RISK)])
def test_activity_uses_the_newest_commit(days_ago, expected):
    commits = [make_commit(days_ago + 30), make_commit(days_ago)]
    assert activity_signal(make_repo(), commits, NOW).status == expected


def test_activity_falls_back_to_pushed_at_without_commits():
    assert activity_signal(make_repo(pushed_at=iso(400)), [], NOW).status == RISK


def test_activity_is_unknown_for_an_empty_repo():
    assert activity_signal(make_repo(pushed_at=None), [], NOW).status == UNKNOWN


def commits_by(*logins: str, days_ago: float = 10) -> list[dict]:
    return [make_commit(days_ago, login) for login in logins]


@pytest.mark.parametrize(
    "logins, expected",
    [
        (["alice"] * 4 + ["bob"], RISK),  # top author 80%
        (["alice"] * 3 + ["bob", "carol"], WATCH),  # 60%
        (["alice"] * 5 + ["bob", "carol", "dave", "erin", "frank"], WATCH),  # 50%
        (["alice", "alice", "bob", "carol", "dave"], OK),  # 40%
    ],
)
def test_bus_factor_thresholds(logins, expected):
    assert bus_factor_signal(make_repo(), commits_by(*logins), NOW).status == expected


def test_bus_factor_ignores_bots_and_commits_older_than_a_year():
    commits = (
        commits_by("alice", "bob", "carol", "dave", "erin")
        + [make_commit(5, "dependabot[bot]", user_type="Bot") for _ in range(20)]
        + [make_commit(400, "alice") for _ in range(20)]
    )
    signal = bus_factor_signal(make_repo(), commits, NOW)
    assert signal.status == OK
    assert "of 5 commits" in signal.value


def test_bus_factor_groups_commits_without_a_github_account_by_name():
    commits = [make_commit(5, login=None) for _ in range(5)]
    signal = bus_factor_signal(make_repo(), commits, NOW)
    assert signal.status == RISK
    assert signal.value.startswith("Anonymous Dev")


def test_bus_factor_is_a_risk_when_one_person_wrote_every_recent_commit():
    signal = bus_factor_signal(make_repo(), commits_by("alice", "alice"), NOW)
    assert signal.status == RISK
    assert signal.value == "alice wrote all 2 commits"


def test_bus_factor_wording_for_a_single_commit():
    assert bus_factor_signal(make_repo(), commits_by("alice"), NOW).value == "alice wrote the only commit"


def test_bus_factor_is_unknown_with_few_commits_from_several_people():
    assert bus_factor_signal(make_repo(), commits_by("alice", "alice", "bob"), NOW).status == UNKNOWN


def test_bus_factor_is_unknown_without_recent_human_commits():
    commits = [make_commit(400, "alice"), make_commit(5, "dependabot[bot]", user_type="Bot")]
    assert bus_factor_signal(make_repo(), commits, NOW).status == UNKNOWN


def issues_with(unanswered: int, answered: int, days_ago: float = 30) -> list[dict]:
    return [make_issue(days_ago) for _ in range(unanswered)] + [
        make_issue(days_ago, comments=2) for _ in range(answered)
    ]


@pytest.mark.parametrize(
    "unanswered, expected",
    [(0, OK), (2, OK), (3, WATCH), (5, WATCH), (6, RISK)],
)
def test_issue_response_thresholds(unanswered, expected):
    issues = issues_with(unanswered=unanswered, answered=10 - unanswered)
    assert issues_signal(make_repo(), issues, NOW).status == expected


def test_issue_response_ignores_pull_requests_bots_and_fresh_issues():
    issues = (
        issues_with(unanswered=0, answered=5)
        + [make_issue(30, pull_request=True) for _ in range(10)]
        + [make_issue(30, login="renovate[bot]", user_type="Bot") for _ in range(10)]
        + [make_issue(3) for _ in range(10)]
    )
    signal = issues_signal(make_repo(), issues, NOW)
    assert signal.status == OK
    assert "of 5 issues" in signal.value


def test_closed_issue_without_comments_counts_as_handled():
    issues = [make_issue(30, state="closed") for _ in range(5)]
    assert issues_signal(make_repo(), issues, NOW).status == OK


def test_issue_response_is_unknown_when_issues_are_disabled():
    assert issues_signal(make_repo(has_issues=False), None, NOW).status == UNKNOWN


def test_issue_response_is_unknown_with_too_few_old_issues():
    assert issues_signal(make_repo(), issues_with(unanswered=4, answered=0), NOW).status == UNKNOWN


@pytest.mark.parametrize("days_ago, expected", [(30, OK), (365, OK), (366, WATCH)])
def test_release_age(days_ago, expected):
    assert releases_signal(make_repo(), [make_release(days_ago)], NOW).status == expected


def test_no_releases_is_watch_not_risk():
    assert releases_signal(make_repo(), [], NOW).status == WATCH


def test_draft_releases_are_ignored():
    releases = [make_release(1, draft=True), make_release(400)]
    assert releases_signal(make_repo(), releases, NOW).status == WATCH


def test_build_signals_returns_all_six_in_order_with_evidence_links():
    signals = build_signals(make_repo(), [make_commit(1)], [make_release(10)], [], NOW)
    assert [s.id for s in signals] == ["status", "license", "activity", "bus_factor", "issues", "releases"]
    assert all(s.evidence_url.startswith("https://github.com/acme/widget") for s in signals)
