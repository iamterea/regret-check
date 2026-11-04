"""Builders for GitHub API payloads, a fake clock, and HTTP mocks shared by the tests."""
from datetime import datetime, timedelta, timezone

import responses

# Relative to the real clock so view tests, which use timezone.now(), stay valid over time.
NOW = datetime.now(timezone.utc).replace(microsecond=0)
API = "https://api.github.com"
RESET = 1_900_000_000  # 2030-03-17T17:46:40Z


class FakeClock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def make_repo(**overrides) -> dict:
    repo = {
        "full_name": "acme/widget",
        "html_url": "https://github.com/acme/widget",
        "description": "A widget library",
        "stargazers_count": 1200,
        "archived": False,
        "has_issues": True,
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "pushed_at": iso(1),
    }
    repo.update(overrides)
    return repo


def make_commit(days_ago: float, login: str | None = "alice", user_type: str = "User") -> dict:
    name = login or "Anonymous Dev"
    return {
        "author": {"login": login, "type": user_type} if login else None,
        "commit": {
            "author": {
                "name": name,
                "email": f"{name.replace(' ', '.').lower()}@example.com",
                "date": iso(days_ago),
            },
            "committer": {"date": iso(days_ago)},
        },
    }


def make_issue(
    days_ago: float,
    state: str = "open",
    comments: int = 0,
    login: str = "bob",
    user_type: str = "User",
    pull_request: bool = False,
) -> dict:
    issue = {
        "created_at": iso(days_ago),
        "state": state,
        "comments": comments,
        "user": {"login": login, "type": user_type},
    }
    if pull_request:
        issue["pull_request"] = {"merged_at": None}
    return issue


def make_release(days_ago: float, draft: bool = False) -> dict:
    return {"draft": draft, "published_at": None if draft else iso(days_ago)}


def mock_rate_limit(remaining: int = 60) -> None:
    core = {"limit": 60, "remaining": remaining, "reset": RESET, "used": 60 - remaining}
    responses.add(responses.GET, f"{API}/rate_limit", json={"resources": {"core": core}})


def mock_healthy_repo(repo: dict | None = None, with_issues: bool = True) -> None:
    """acme/widget that should come out "low": active, shared authorship, answered issues, recent release."""
    base = f"{API}/repos/acme/widget"
    authors = ["alice", "bob", "carol", "dave", "erin"]
    responses.add(responses.GET, base, json=repo or make_repo())
    responses.add(
        responses.GET,
        f"{base}/commits",
        json=[make_commit(day, login) for day, login in enumerate(authors, start=1)],
    )
    responses.add(responses.GET, f"{base}/releases", json=[make_release(20)])
    if with_issues:
        responses.add(responses.GET, f"{base}/issues", json=[make_issue(30, comments=1) for _ in range(5)])
