# Regret Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A small web app that takes a GitHub repository and answers "will we regret adopting this in two years?" with six explained risk signals and a verdict.

**Architecture:** Django backend (no database) fetches at most 4 GitHub REST endpoints per evaluation through a cached, rate-limit-aware client, turns the raw data into signals with pure functions, and serves JSON. A Vite + React + TypeScript frontend parses the user's input, calls the API and renders the verdict, the signals (worst first), the remaining GitHub budget and every error state.

**Tech Stack:** Python 3.12, Django 5.2, requests, pytest + pytest-django + responses; Node 24, React, TypeScript (strict), Vite, Vitest + Testing Library.

Spec: `docs/superpowers/specs/2026-11-04-regret-check-design.md`.

## Global Constraints

- Python 3.12 in a virtualenv at `backend/.venv`; run Python only as `backend/.venv/bin/python`. Django `>=5.2,<5.3`. No database, no Django REST framework.
- Automated tests never touch the real network: backend uses `responses`, frontend stubs `fetch`.
- Every GitHub request sends `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: regret-check`, and `Authorization: Bearer <token>` only when `GITHUB_TOKEN` is set.
- Signal ids, labels, thresholds and verdict rules are exactly the spec's: ids `status`, `license`, `activity`, `bus_factor`, `issues`, `releases`; statuses `ok`, `watch`, `risk`, `unknown`; levels `low`, `medium`, `high`.
- API error body is always `{"error": <code>, "message": <text>}` (plus `reset_at` for `rate_limited`).
- UI copy is English. A status is never shown by colour alone: always with a text label.
- Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (pass it as a second `-m`).
- All commands run from the repository root unless they start with `cd`.

## File Structure

```
.gitignore
README.md                          Task 7
Dockerfile, .dockerignore          Task 8 (optional)
backend/
  requirements.txt                 runtime deps
  requirements-dev.txt             + test deps
  pytest.ini
  conftest.py                      cache fixtures
  manage.py
  config/
    __init__.py
    settings.py                    no DB, file cache, GitHub settings
    settings_test.py               locmem cache for tests
    urls.py                        mounts evaluator.urls at /api/
    wsgi.py
  evaluator/
    __init__.py
    signals.py                     pure: raw data + now → Signal list, Verdict
    github_client.py               HTTP, per-URL cache, rate-limit errors
    service.py                     one evaluation: budget check, fetches, report dict
    views.py                       /api/evaluate, /api/rate-limit
    urls.py
    tests/
      __init__.py
      factories.py                 payload builders, FakeClock, HTTP mocks
      test_signals.py
      test_verdict.py
      test_github_client.py
      test_service.py
      test_views.py
frontend/
  package.json, package-lock.json
  index.html
  tsconfig.json
  vite.config.ts                   dev proxy /api → :8000, vitest config
  src/
    main.tsx
    App.tsx                        state machine: idle/loading/done/error
    App.test.tsx
    index.css
    setupTests.ts
    types.ts                       API contract types
    api.ts, api.test.ts            fetch wrappers, ApiError
    parseRepo.ts, parseRepo.test.ts
    format.ts                      time formatting
    components/
      RepoForm.tsx
      VerdictBanner.tsx
      SignalCard.tsx
      RateLimitNote.tsx
```

---

### Task 1: Backend skeleton and risk signals

**Files:**
- Create: `.gitignore`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pytest.ini`, `backend/conftest.py`, `backend/manage.py`, `backend/config/__init__.py`, `backend/config/settings.py`, `backend/config/settings_test.py`, `backend/config/urls.py`, `backend/config/wsgi.py`, `backend/evaluator/__init__.py`, `backend/evaluator/signals.py`, `backend/evaluator/tests/__init__.py`, `backend/evaluator/tests/factories.py`
- Test: `backend/evaluator/tests/test_signals.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `evaluator.signals`: constants `OK = "ok"`, `WATCH = "watch"`, `RISK = "risk"`, `UNKNOWN = "unknown"`; frozen dataclass `Signal(id: str, label: str, status: str, value: str, detail: str, evidence_url: str)`; `parse_time(value: str) -> datetime`; `build_signals(repo: dict, commits: list[dict], releases: list[dict], issues: list[dict] | None, now: datetime) -> list[Signal]` (always 6 signals, in order `status, license, activity, bus_factor, issues, releases`); plus the six `*_signal` functions used by tests.
  - `evaluator.tests.factories`: `NOW`, `API`, `RESET`, `FakeClock`, `iso(days_ago)`, `make_repo(**overrides)`, `make_commit(days_ago, login="alice", user_type="User")`, `make_issue(days_ago, state="open", comments=0, login="bob", user_type="User", pull_request=False)`, `make_release(days_ago, draft=False)`, `mock_rate_limit(remaining=60)`, `mock_healthy_repo(repo=None, with_issues=True)`.
  - `backend/conftest.py` fixtures: `memory_cache` (isolated `LocMemCache`), autouse `clear_default_cache`.

- [ ] **Step 1: Create the project files**

`.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
backend/.cache/
node_modules/
frontend/dist/
.DS_Store
```

`backend/requirements.txt`:

```text
Django>=5.2,<5.3
requests>=2.32,<3
```

`backend/requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.3
pytest-django>=4.9
responses>=0.25
```

`backend/pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings_test
python_files = test_*.py
addopts = -q
```

`backend/manage.py`:

```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
```

`backend/config/__init__.py`: empty file.

`backend/config/settings.py`:

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = ["evaluator"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No database: the app is stateless apart from the GitHub response cache.
DATABASES = {}

USE_TZ = True
TIME_ZONE = "UTC"

# File-based so every gunicorn worker on one host shares the same cache.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("CACHE_DIR", str(BASE_DIR / ".cache")),
    }
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_CACHE_TTL_SECONDS = int(os.environ.get("GITHUB_CACHE_TTL_SECONDS", "3600"))
```

`backend/config/settings_test.py`:

```python
from .settings import *  # noqa: F401,F403

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
GITHUB_TOKEN = ""
```

`backend/config/urls.py`:

```python
urlpatterns: list = []
```

`backend/config/wsgi.py`:

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
```

`backend/evaluator/__init__.py` and `backend/evaluator/tests/__init__.py`: empty files.

`backend/conftest.py`:

```python
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache


@pytest.fixture
def memory_cache():
    """An in-memory cache no other test can see."""
    return LocMemCache(f"test-{uuid4()}", {})


@pytest.fixture(autouse=True)
def clear_default_cache():
    cache.clear()
    yield
    cache.clear()
```

`backend/evaluator/tests/factories.py`:

```python
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
```

- [ ] **Step 2: Install dependencies and check Django boots**

Run:

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt && .venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Write the failing signal tests**

`backend/evaluator/tests/test_signals.py`:

```python
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


def test_bus_factor_is_unknown_with_too_few_commits():
    assert bus_factor_signal(make_repo(), commits_by("alice", "alice"), NOW).status == UNKNOWN


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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_signals.py`
Expected: collection error, `ModuleNotFoundError: No module named 'evaluator.signals'`.

- [ ] **Step 5: Implement the signals**

`backend/evaluator/signals.py`:

```python
"""Turn raw GitHub API data into explained risk signals.

Pure functions only: no I/O, and `now` is always passed in.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

OK, WATCH, RISK, UNKNOWN = "ok", "watch", "risk", "unknown"

ACTIVE_DAYS = 90
STALE_DAYS = 365
RECENT_WINDOW_DAYS = 365
ISSUE_MIN_AGE_DAYS = 14
MIN_SAMPLE = 5

PERMISSIVE_LICENSES = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Unlicense",
        "Zlib",
        "BSL-1.0",
        "CC0-1.0",
        "PSF-2.0",
        "Python-2.0",
    }
)


@dataclass(frozen=True)
class Signal:
    id: str
    label: str
    status: str
    value: str
    detail: str
    evidence_url: str


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def describe_age(then: datetime, now: datetime) -> str:
    days = (now - then).days
    if days < 1:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 60:
        return f"{days} days ago"
    if days < 730:
        return f"{days // 30} months ago"
    return f"{days // 365} years ago"


def is_bot(user: dict | None, name: str = "") -> bool:
    if user and (user.get("type") == "Bot" or (user.get("login") or "").endswith("[bot]")):
        return True
    return name.endswith("[bot]")


def status_signal(repo: dict) -> Signal:
    url = repo["html_url"]
    if repo.get("archived"):
        return Signal(
            "status",
            "Archived",
            RISK,
            "Archived",
            "The owners archived this repository. It is read-only and will get no fixes, security fixes included.",
            url,
        )
    return Signal("status", "Archived", OK, "Not archived", "The repository is open for changes.", url)


def license_signal(repo: dict) -> Signal:
    url = repo["html_url"]
    license_info = repo.get("license")
    if not license_info:
        return Signal(
            "license",
            "License",
            RISK,
            "None",
            "No license detected. Without one you have no legal right to use the code.",
            url,
        )
    spdx = license_info.get("spdx_id") or "NOASSERTION"
    if spdx in PERMISSIVE_LICENSES:
        return Signal("license", "License", OK, spdx, "A permissive license: fine for a commercial product.", url)
    value = "Custom" if spdx == "NOASSERTION" else spdx
    name = license_info.get("name") or value
    return Signal(
        "license",
        "License",
        WATCH,
        value,
        f"{name} is copyleft, source-available or non-standard. "
        "Check it fits a commercial product before adopting.",
        url,
    )


def _commit_time(commit: dict) -> datetime:
    return parse_time(commit["commit"]["committer"]["date"])


def activity_signal(repo: dict, commits: list[dict], now: datetime) -> Signal:
    url = f"{repo['html_url']}/commits"
    if commits:
        last = max(_commit_time(commit) for commit in commits)
    elif repo.get("pushed_at"):
        last = parse_time(repo["pushed_at"])
    else:
        return Signal("activity", "Recent activity", UNKNOWN, "No commits", "The repository has no commits yet.", url)
    value = f"Last commit {describe_age(last, now)}"
    age_days = (now - last).days
    if age_days <= ACTIVE_DAYS:
        return Signal(
            "activity", "Recent activity", OK, value, "Code is still changing, so a fix you need is likely to land.", url
        )
    if age_days <= STALE_DAYS:
        return Signal(
            "activity",
            "Recent activity",
            WATCH,
            value,
            "No commits for over three months. Small, finished libraries can be quiet: "
            "check whether issues still get answers.",
            url,
        )
    return Signal(
        "activity", "Recent activity", RISK, value, "No commits for over a year. If you need a fix, expect to fork.", url
    )


def _commit_author(commit: dict) -> str | None:
    """Who wrote a commit: GitHub login, else git name or email. None for bots."""
    user = commit.get("author")
    git_author = commit["commit"]["author"]
    name = git_author.get("name") or ""
    if is_bot(user, name):
        return None
    if user and user.get("login"):
        return user["login"]
    return name or git_author.get("email") or "unknown"


def bus_factor_signal(repo: dict, commits: list[dict], now: datetime) -> Signal:
    url = f"{repo['html_url']}/graphs/contributors"
    cutoff = now - timedelta(days=RECENT_WINDOW_DAYS)
    authors = []
    for commit in commits:
        author = _commit_author(commit)
        if author is not None and _commit_time(commit) >= cutoff:
            authors.append(author)
    if len(authors) < MIN_SAMPLE:
        return Signal(
            "bus_factor",
            "Bus factor",
            UNKNOWN,
            f"{len(authors)} human commits in the last year",
            "Too few commits in the last year to tell who maintains it.",
            url,
        )
    counts = Counter(authors)
    top_author, top_count = counts.most_common(1)[0]
    share = top_count / len(authors)
    value = f"{top_author} wrote {share:.0%} of {len(authors)} commits"
    if share >= 0.8:
        return Signal(
            "bus_factor",
            "Bus factor",
            RISK,
            value,
            "One person writes almost all the code. If they step away, the project stalls.",
            url,
        )
    if share >= 0.5:
        return Signal(
            "bus_factor", "Bus factor", WATCH, value, "One person writes most of the code, with thin backup.", url
        )
    return Signal(
        "bus_factor", "Bus factor", OK, value, f"Work is spread across {len(counts)} people in the last year.", url
    )


def issues_signal(repo: dict, issues: list[dict] | None, now: datetime) -> Signal:
    url = f"{repo['html_url']}/issues?q=is%3Aissue+is%3Aopen+comments%3A0"
    if issues is None or not repo.get("has_issues", True):
        return Signal(
            "issues",
            "Issue response",
            UNKNOWN,
            "Issues disabled",
            "Issues are turned off, so there is no public record of how bug reports are handled.",
            repo["html_url"],
        )
    cutoff = now - timedelta(days=ISSUE_MIN_AGE_DAYS)
    considered = [
        issue
        for issue in issues
        if "pull_request" not in issue
        and not is_bot(issue.get("user"))
        and parse_time(issue["created_at"]) <= cutoff
    ]
    if len(considered) < MIN_SAMPLE:
        return Signal(
            "issues",
            "Issue response",
            UNKNOWN,
            f"{len(considered)} issues older than two weeks",
            "Too few issues older than two weeks to judge how they are handled.",
            url,
        )
    unanswered = sum(1 for issue in considered if issue["state"] == "open" and issue["comments"] == 0)
    share = unanswered / len(considered)
    value = f"{share:.0%} of {len(considered)} issues got no reply"
    if share <= 0.2:
        return Signal("issues", "Issue response", OK, value, "Most issues get a reply or get closed.", url)
    if share <= 0.5:
        return Signal(
            "issues",
            "Issue response",
            WATCH,
            value,
            "A noticeable share of issues sit for two weeks or more with no reply.",
            url,
        )
    return Signal(
        "issues",
        "Issue response",
        RISK,
        value,
        "Most issues get no reply at all. Expect the same for your bug reports.",
        url,
    )


def releases_signal(repo: dict, releases: list[dict], now: datetime) -> Signal:
    url = f"{repo['html_url']}/releases"
    published = [
        parse_time(release["published_at"])
        for release in releases
        if not release.get("draft") and release.get("published_at")
    ]
    if not published:
        return Signal(
            "releases",
            "Releases",
            WATCH,
            "No releases",
            "No GitHub releases. The project may ship only tags or registry versions: check its changelog.",
            url,
        )
    last = max(published)
    value = f"Last release {describe_age(last, now)}"
    if (now - last).days <= STALE_DAYS:
        return Signal("releases", "Releases", OK, value, "Releases are still being cut.", url)
    return Signal(
        "releases",
        "Releases",
        WATCH,
        value,
        "No release for over a year, so fixes may sit unreleased on the main branch.",
        url,
    )


def build_signals(
    repo: dict,
    commits: list[dict],
    releases: list[dict],
    issues: list[dict] | None,
    now: datetime,
) -> list[Signal]:
    return [
        status_signal(repo),
        license_signal(repo),
        activity_signal(repo, commits, now),
        bus_factor_signal(repo, commits, now),
        issues_signal(repo, issues, now),
        releases_signal(repo, releases, now),
    ]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_signals.py`
Expected: all tests pass (36 passed).

- [ ] **Step 7: Commit**

```bash
git add .gitignore backend
git commit -m "feat(backend): Django skeleton and the six risk signals" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Verdict rules

**Files:**
- Modify: `backend/evaluator/signals.py` (append verdict code at the end)
- Test: `backend/evaluator/tests/test_verdict.py`

**Interfaces:**
- Consumes: `Signal`, `OK`, `WATCH`, `RISK`, `UNKNOWN` from Task 1.
- Produces: in `evaluator.signals`, frozen dataclass `Verdict(level: str, headline: str, reasons: list[str])` and `decide_verdict(signals: list[Signal]) -> Verdict`.

- [ ] **Step 1: Write the failing tests**

`backend/evaluator/tests/test_verdict.py`:

```python
import pytest

from evaluator.signals import OK, RISK, UNKNOWN, WATCH, Signal, decide_verdict


def signal(signal_id: str, status: str) -> Signal:
    return Signal(signal_id, signal_id, status, "", "", "")


@pytest.mark.parametrize(
    "statuses, level",
    [
        ({"activity": OK, "releases": OK}, "low"),
        ({"releases": WATCH}, "low"),
        ({"releases": WATCH, "bus_factor": WATCH}, "medium"),
        ({"activity": RISK}, "medium"),
        ({"activity": RISK, "issues": RISK}, "high"),
        ({"status": RISK}, "high"),
        ({"license": RISK}, "high"),
        ({"activity": UNKNOWN, "issues": UNKNOWN, "bus_factor": UNKNOWN}, "low"),
    ],
)
def test_verdict_levels(statuses, level):
    verdict = decide_verdict([signal(signal_id, status) for signal_id, status in statuses.items()])
    assert verdict.level == level


def test_reasons_list_risks_before_watches_in_signal_order():
    verdict = decide_verdict([signal("license", WATCH), signal("activity", RISK), signal("releases", WATCH)])
    assert verdict.reasons == ["activity", "license", "releases"]
    assert verdict.headline == "Medium regret risk"


def test_low_verdict_headline():
    assert decide_verdict([signal("activity", OK)]).headline == "Low regret risk"


def test_high_verdict_headline():
    assert decide_verdict([signal("status", RISK)]).headline == "High regret risk"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_verdict.py`
Expected: `ImportError: cannot import name 'decide_verdict'`.

- [ ] **Step 3: Implement the verdict**

Append to `backend/evaluator/signals.py`:

```python
DEALBREAKERS = frozenset({"status", "license"})
HEADLINES = {"low": "Low regret risk", "medium": "Medium regret risk", "high": "High regret risk"}


@dataclass(frozen=True)
class Verdict:
    level: str
    headline: str
    reasons: list[str]


def decide_verdict(signals: list[Signal]) -> Verdict:
    risks = [s.id for s in signals if s.status == RISK]
    watches = [s.id for s in signals if s.status == WATCH]
    if (DEALBREAKERS & set(risks)) or len(risks) >= 2:
        level = "high"
    elif risks or len(watches) >= 2:
        level = "medium"
    else:
        level = "low"
    return Verdict(level, HEADLINES[level], risks + watches)
```

- [ ] **Step 4: Run all backend tests**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/evaluator/signals.py backend/evaluator/tests/test_verdict.py
git commit -m "feat(backend): verdict rules over the signals" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Cached, rate-limit-aware GitHub client

**Files:**
- Create: `backend/evaluator/github_client.py`
- Test: `backend/evaluator/tests/test_github_client.py`

**Interfaces:**
- Consumes: `FakeClock`, `RESET` from `evaluator.tests.factories`; `memory_cache` fixture.
- Produces, in `evaluator.github_client`:
  - Exceptions `GitHubError(Exception)`, `NotFound(GitHubError)`, `RateLimited(GitHubError)` with attribute `reset_at: datetime`.
  - Frozen dataclass `RateLimit(limit: int, remaining: int, reset_at: datetime)`.
  - `GitHubClient(cache, token: str = "", ttl_seconds: int = 3600, session=None, clock=time.time)` with:
    - `get(path: str, params: dict | None = None) -> Any` — fresh cache hit without a request; otherwise one request; on rate limit or other failure falls back to a cached copy of any age, else raises.
    - `cached(path: str, params: dict | None = None) -> Any | None` — cached copy of any age, never requests.
    - `is_fresh(path: str, params: dict | None = None) -> bool`
    - `rate_limit() -> RateLimit` — free `/rate_limit` call; raises `GitHubError` on failure.
    - Attributes `requests_made: int`, `served_stale: bool`, `oldest_fetched_at: float | None`.

- [ ] **Step 1: Write the failing tests**

`backend/evaluator/tests/test_github_client.py`:

```python
from datetime import datetime, timezone

import pytest
import responses

from evaluator.github_client import GitHubClient, GitHubError, NotFound, RateLimited
from evaluator.tests.factories import API, RESET, FakeClock

REPO_URL = f"{API}/repos/acme/widget"
RATE_LIMITED_HEADERS = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(RESET)}


def make_client(cache, clock=None, token=""):
    return GitHubClient(cache, token=token, ttl_seconds=3600, clock=clock or FakeClock())


@responses.activate
def test_fresh_cache_entry_is_served_without_a_request(memory_cache):
    responses.add(responses.GET, REPO_URL, json={"name": "widget"})
    first = make_client(memory_cache)
    second = make_client(memory_cache)

    assert first.get("/repos/acme/widget") == {"name": "widget"}
    assert second.get("/repos/acme/widget") == {"name": "widget"}

    assert len(responses.calls) == 1
    assert (first.requests_made, second.requests_made) == (1, 0)
    assert second.is_fresh("/repos/acme/widget")


@responses.activate
def test_entry_older_than_the_ttl_is_fetched_again(memory_cache):
    clock = FakeClock()
    responses.add(responses.GET, REPO_URL, json={"v": 1})
    make_client(memory_cache, clock).get("/repos/acme/widget")

    clock.now += 3600
    client = make_client(memory_cache, clock)
    assert not client.is_fresh("/repos/acme/widget")
    client.get("/repos/acme/widget")

    assert len(responses.calls) == 2


@responses.activate
def test_query_params_are_part_of_the_cache_key(memory_cache):
    responses.add(responses.GET, f"{REPO_URL}/commits", json=[])
    client = make_client(memory_cache)
    client.get("/repos/acme/widget/commits", {"per_page": 100})
    client.get("/repos/acme/widget/commits", {"per_page": 10})
    assert len(responses.calls) == 2


@responses.activate
def test_rate_limited_without_a_cached_copy_raises_with_the_reset_time(memory_cache):
    responses.add(responses.GET, REPO_URL, status=403, headers=RATE_LIMITED_HEADERS, json={"message": "rate limit"})
    with pytest.raises(RateLimited) as caught:
        make_client(memory_cache).get("/repos/acme/widget")
    assert caught.value.reset_at == datetime.fromtimestamp(RESET, tz=timezone.utc)


@responses.activate
def test_status_429_is_treated_as_rate_limited(memory_cache):
    responses.add(responses.GET, REPO_URL, status=429, headers={"X-RateLimit-Reset": str(RESET)})
    with pytest.raises(RateLimited):
        make_client(memory_cache).get("/repos/acme/widget")


@responses.activate
def test_forbidden_with_budget_left_is_a_plain_github_error(memory_cache):
    responses.add(responses.GET, REPO_URL, status=403, headers={"X-RateLimit-Remaining": "12"})
    with pytest.raises(GitHubError) as caught:
        make_client(memory_cache).get("/repos/acme/widget")
    assert not isinstance(caught.value, RateLimited)


@responses.activate
def test_rate_limit_falls_back_to_the_stale_copy(memory_cache):
    clock = FakeClock()
    responses.add(responses.GET, REPO_URL, json={"v": "old"})
    make_client(memory_cache, clock).get("/repos/acme/widget")

    clock.now += 7200
    responses.reset()
    responses.add(responses.GET, REPO_URL, status=403, headers=RATE_LIMITED_HEADERS)
    client = make_client(memory_cache, clock)

    assert client.get("/repos/acme/widget") == {"v": "old"}
    assert client.served_stale is True
    assert client.oldest_fetched_at == 1_000_000.0


@responses.activate
def test_not_found_raises(memory_cache):
    responses.add(responses.GET, REPO_URL, status=404, json={"message": "Not Found"})
    with pytest.raises(NotFound):
        make_client(memory_cache).get("/repos/acme/widget")


@responses.activate
def test_server_error_without_a_cached_copy_raises(memory_cache):
    responses.add(responses.GET, REPO_URL, status=502)
    with pytest.raises(GitHubError):
        make_client(memory_cache).get("/repos/acme/widget")


@responses.activate
def test_token_is_sent_as_a_bearer_header(memory_cache):
    responses.add(responses.GET, REPO_URL, json={})
    make_client(memory_cache, token="secret-token").get("/repos/acme/widget")
    headers = responses.calls[0].request.headers
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["User-Agent"] == "regret-check"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


@responses.activate
def test_no_authorization_header_without_a_token(memory_cache):
    responses.add(responses.GET, REPO_URL, json={})
    make_client(memory_cache).get("/repos/acme/widget")
    assert "Authorization" not in responses.calls[0].request.headers


@responses.activate
def test_rate_limit_reads_the_core_budget(memory_cache):
    core = {"limit": 60, "remaining": 41, "reset": RESET, "used": 19}
    responses.add(responses.GET, f"{API}/rate_limit", json={"resources": {"core": core}})
    budget = make_client(memory_cache).rate_limit()
    assert (budget.limit, budget.remaining) == (60, 41)
    assert budget.reset_at == datetime.fromtimestamp(RESET, tz=timezone.utc)


@responses.activate
def test_rate_limit_failure_is_a_github_error(memory_cache):
    responses.add(responses.GET, f"{API}/rate_limit", status=500)
    with pytest.raises(GitHubError):
        make_client(memory_cache).rate_limit()


@responses.activate
def test_cached_returns_an_old_copy_without_a_request(memory_cache):
    clock = FakeClock()
    responses.add(responses.GET, REPO_URL, json={"v": 1})
    make_client(memory_cache, clock).get("/repos/acme/widget")
    responses.reset()

    clock.now += 7200
    client = make_client(memory_cache, clock)
    assert client.cached("/repos/acme/widget") == {"v": 1}
    assert client.served_stale is True
    assert client.cached("/repos/acme/other") is None
    assert len(responses.calls) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_github_client.py`
Expected: `ModuleNotFoundError: No module named 'evaluator.github_client'`.

- [ ] **Step 3: Implement the client**

`backend/evaluator/github_client.py`:

```python
"""GitHub REST client with a per-URL cache and rate-limit awareness.

Without a token GitHub allows 60 requests an hour per IP, and a 304 answer to a
conditional request still counts against that (measured 2026-11-04). So the
cache is time-based: a fresh entry is served with no request at all, and older
entries are kept for a week as a fallback for when the limit runs out.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode

import requests

API_ROOT = "https://api.github.com"
KEEP_SECONDS = 7 * 24 * 3600
TIMEOUT_SECONDS = 10


class GitHubError(Exception):
    """GitHub failed and no cached copy could stand in."""


class NotFound(GitHubError):
    """The repository does not exist or is private."""


class RateLimited(GitHubError):
    def __init__(self, reset_at: datetime):
        super().__init__(f"GitHub rate limit exhausted until {reset_at.isoformat()}")
        self.reset_at = reset_at


@dataclass(frozen=True)
class RateLimit:
    limit: int
    remaining: int
    reset_at: datetime


class GitHubClient:
    """Use one instance per evaluation: it counts the requests it made and whether it used stale data."""

    def __init__(
        self,
        cache,
        token: str = "",
        ttl_seconds: int = 3600,
        session: requests.Session | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self._cache = cache
        self._ttl = ttl_seconds
        self._session = session or requests.Session()
        self._clock = clock
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "regret-check",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self.requests_made = 0
        self.served_stale = False
        self.oldest_fetched_at: float | None = None

    def is_fresh(self, path: str, params: dict | None = None) -> bool:
        entry = self._cache.get(_key(path, params))
        return entry is not None and self._is_fresh(entry)

    def cached(self, path: str, params: dict | None = None) -> Any | None:
        """The cached copy of any age, or None. Never makes a request."""
        entry = self._cache.get(_key(path, params))
        if entry is None:
            return None
        if not self._is_fresh(entry):
            self.served_stale = True
        return self._use(entry)

    def get(self, path: str, params: dict | None = None) -> Any:
        key = _key(path, params)
        entry = self._cache.get(key)
        if entry is not None and self._is_fresh(entry):
            return self._use(entry)
        try:
            response = self._session.get(
                f"{API_ROOT}{path}", params=params, headers=self._headers, timeout=TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            return self._fall_back(entry, GitHubError(f"Could not reach GitHub: {exc}"))
        self.requests_made += 1
        if response.status_code == 200:
            entry = {"data": response.json(), "fetched_at": self._clock()}
            self._cache.set(key, entry, timeout=KEEP_SECONDS)
            return self._use(entry)
        if response.status_code == 404:
            raise NotFound(path)
        if _is_rate_limited(response):
            return self._fall_back(entry, RateLimited(self._reset_at(response)))
        return self._fall_back(entry, GitHubError(f"GitHub returned {response.status_code} for {path}"))

    def rate_limit(self) -> RateLimit:
        """Current budget. GitHub does not count this call against it."""
        try:
            response = self._session.get(f"{API_ROOT}/rate_limit", headers=self._headers, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GitHubError(f"Could not read the rate limit: {exc}") from exc
        core = response.json()["resources"]["core"]
        return RateLimit(core["limit"], core["remaining"], datetime.fromtimestamp(core["reset"], tz=timezone.utc))

    def _is_fresh(self, entry: dict) -> bool:
        return self._clock() - entry["fetched_at"] < self._ttl

    def _use(self, entry: dict) -> Any:
        if self.oldest_fetched_at is None or entry["fetched_at"] < self.oldest_fetched_at:
            self.oldest_fetched_at = entry["fetched_at"]
        return entry["data"]

    def _fall_back(self, entry: dict | None, error: GitHubError) -> Any:
        if entry is None:
            raise error
        self.served_stale = True
        return self._use(entry)

    def _reset_at(self, response: requests.Response) -> datetime:
        reset = response.headers.get("X-RateLimit-Reset")
        seconds = int(reset) if reset else int(self._clock()) + 60
        return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _key(path: str, params: dict | None) -> str:
    return f"github:{path}?{urlencode(sorted((params or {}).items()))}"


def _is_rate_limited(response: requests.Response) -> bool:
    return response.status_code == 429 or (
        response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_github_client.py`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/evaluator/github_client.py backend/evaluator/tests/test_github_client.py
git commit -m "feat(backend): cached GitHub client with rate-limit fallback" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Evaluation service and HTTP API

**Files:**
- Create: `backend/evaluator/service.py`, `backend/evaluator/views.py`, `backend/evaluator/urls.py`
- Modify: `backend/config/urls.py` (replace whole file)
- Test: `backend/evaluator/tests/test_service.py`, `backend/evaluator/tests/test_views.py`

**Interfaces:**
- Consumes: `build_signals`, `decide_verdict` (Tasks 1–2); `GitHubClient`, `GitHubError`, `NotFound`, `RateLimited` (Task 3); factories `NOW`, `API`, `FakeClock`, `make_repo`, `mock_rate_limit`, `mock_healthy_repo`.
- Produces:
  - `evaluator.service.evaluate(full_name: str, client: GitHubClient, now: datetime) -> dict` returning the spec's JSON shape (`repo`, `verdict`, `signals`, `meta` with `data_as_of`, `stale`, `rate_limit`).
  - `evaluator.service.iso(moment: datetime) -> str` (UTC, `Z` suffix).
  - HTTP: `GET /api/evaluate?repo=owner/name` and `GET /api/rate-limit`, status codes per the spec (400, 404, 429 with `reset_at`, 502).

- [ ] **Step 1: Write the failing service tests**

`backend/evaluator/tests/test_service.py`:

```python
import pytest
import responses

from evaluator.github_client import GitHubClient, RateLimited
from evaluator.service import evaluate
from evaluator.tests.factories import API, NOW, FakeClock, make_repo, mock_healthy_repo, mock_rate_limit


def make_client(cache, clock):
    return GitHubClient(cache, ttl_seconds=3600, clock=clock)


@responses.activate
def test_evaluate_builds_the_full_report(memory_cache):
    mock_rate_limit(remaining=60)
    mock_healthy_repo()

    result = evaluate("acme/widget", make_client(memory_cache, FakeClock()), NOW)

    assert result["repo"] == {
        "full_name": "acme/widget",
        "description": "A widget library",
        "html_url": "https://github.com/acme/widget",
        "stars": 1200,
    }
    assert result["verdict"] == {"level": "low", "headline": "Low regret risk", "reasons": []}
    assert [s["id"] for s in result["signals"]] == ["status", "license", "activity", "bus_factor", "issues", "releases"]
    assert result["meta"]["stale"] is False
    assert result["meta"]["rate_limit"]["remaining"] == 56
    assert result["meta"]["rate_limit"]["reset_at"] == "2030-03-17T17:46:40Z"


@responses.activate
def test_issues_are_not_fetched_when_the_repo_has_them_disabled(memory_cache):
    mock_rate_limit()
    mock_healthy_repo(repo=make_repo(has_issues=False), with_issues=False)

    result = evaluate("acme/widget", make_client(memory_cache, FakeClock()), NOW)

    issues = next(s for s in result["signals"] if s["id"] == "issues")
    assert issues["status"] == "unknown"
    assert result["meta"]["rate_limit"]["remaining"] == 57


@responses.activate
def test_fresh_cache_needs_no_budget(memory_cache):
    clock = FakeClock()
    mock_rate_limit(remaining=60)
    mock_healthy_repo()
    evaluate("acme/widget", make_client(memory_cache, clock), NOW)

    responses.reset()
    mock_rate_limit(remaining=0)
    result = evaluate("acme/widget", make_client(memory_cache, clock), NOW)

    assert result["meta"]["stale"] is False
    assert [call.request.url for call in responses.calls] == [f"{API}/rate_limit"]


@responses.activate
def test_low_budget_uses_cached_copies_without_spending_requests(memory_cache):
    clock = FakeClock()
    mock_rate_limit(remaining=60)
    mock_healthy_repo()
    evaluate("acme/widget", make_client(memory_cache, clock), NOW)

    clock.now += 7200  # every cached copy is now past the TTL
    responses.reset()
    mock_rate_limit(remaining=0)
    result = evaluate("acme/widget", make_client(memory_cache, clock), NOW)

    assert result["meta"]["stale"] is True
    assert result["verdict"]["level"] == "low"
    assert [call.request.url for call in responses.calls] == [f"{API}/rate_limit"]


@responses.activate
def test_low_budget_without_a_cache_refuses_before_spending(memory_cache):
    mock_rate_limit(remaining=2)

    with pytest.raises(RateLimited):
        evaluate("acme/widget", make_client(memory_cache, FakeClock()), NOW)

    assert [call.request.url for call in responses.calls] == [f"{API}/rate_limit"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_service.py`
Expected: `ModuleNotFoundError: No module named 'evaluator.service'`.

- [ ] **Step 3: Implement the service**

`backend/evaluator/service.py`:

```python
"""One evaluation: check the budget, fetch what is needed, build the report."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .github_client import GitHubClient, RateLimited
from .signals import build_signals, decide_verdict


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _endpoints(full_name: str) -> dict[str, tuple[str, dict | None]]:
    base = f"/repos/{full_name}"
    return {
        "repo": (base, None),
        "commits": (f"{base}/commits", {"per_page": 100}),
        "releases": (f"{base}/releases", {"per_page": 10}),
        "issues": (f"{base}/issues", {"state": "all", "sort": "created", "direction": "desc", "per_page": 100}),
    }


def evaluate(full_name: str, client: GitHubClient, now: datetime) -> dict:
    endpoints = _endpoints(full_name)
    budget = client.rate_limit()
    needed = sum(not client.is_fresh(path, params) for path, params in endpoints.values())
    # Not enough budget for the uncached calls: answer from the cache or not at all,
    # rather than spend half the calls and then fail.
    offline = needed > budget.remaining

    def fetch(name: str):
        path, params = endpoints[name]
        if not offline:
            return client.get(path, params)
        data = client.cached(path, params)
        if data is None:
            raise RateLimited(budget.reset_at)
        return data

    repo = fetch("repo")
    commits = fetch("commits")
    releases = fetch("releases")
    issues = fetch("issues") if repo.get("has_issues", True) else None

    signals = build_signals(repo, commits, releases, issues, now)
    oldest = client.oldest_fetched_at
    return {
        "repo": {
            "full_name": repo["full_name"],
            "description": repo.get("description") or "",
            "html_url": repo["html_url"],
            "stars": repo.get("stargazers_count", 0),
        },
        "verdict": asdict(decide_verdict(signals)),
        "signals": [asdict(signal) for signal in signals],
        "meta": {
            "data_as_of": iso(datetime.fromtimestamp(oldest, tz=timezone.utc)) if oldest else iso(now),
            "stale": client.served_stale,
            "rate_limit": {
                "limit": budget.limit,
                "remaining": max(budget.remaining - client.requests_made, 0),
                "reset_at": iso(budget.reset_at),
            },
        },
    }
```

- [ ] **Step 4: Run the service tests**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_service.py`
Expected: 5 passed.

- [ ] **Step 5: Write the failing view tests**

`backend/evaluator/tests/test_views.py`:

```python
import pytest
import responses

from evaluator.tests.factories import API, mock_healthy_repo, mock_rate_limit


@responses.activate
def test_evaluate_returns_the_report(client):
    mock_rate_limit()
    mock_healthy_repo()

    response = client.get("/api/evaluate", {"repo": "acme/widget"})

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"]["level"] == "low"
    assert len(body["signals"]) == 6
    assert body["meta"]["rate_limit"]["remaining"] == 56


@pytest.mark.parametrize("repo", ["", "acme", "acme/widget/extra", "acme/wid get", "../etc"])
def test_evaluate_rejects_names_that_are_not_owner_slash_name(client, repo):
    response = client.get("/api/evaluate", {"repo": repo})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_repo"


@responses.activate
def test_unknown_repo_is_404(client):
    mock_rate_limit()
    responses.add(responses.GET, f"{API}/repos/acme/ghost", status=404, json={"message": "Not Found"})

    response = client.get("/api/evaluate", {"repo": "acme/ghost"})

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


@responses.activate
def test_no_budget_and_no_cache_is_429_with_reset_time(client):
    mock_rate_limit(remaining=0)

    response = client.get("/api/evaluate", {"repo": "acme/widget"})

    assert response.status_code == 429
    assert response.json() == {
        "error": "rate_limited",
        "message": "GitHub's hourly request limit is used up.",
        "reset_at": "2030-03-17T17:46:40Z",
    }


@responses.activate
def test_github_outage_is_502(client):
    mock_rate_limit()
    responses.add(responses.GET, f"{API}/repos/acme/widget", status=500)

    response = client.get("/api/evaluate", {"repo": "acme/widget"})

    assert response.status_code == 502
    assert response.json()["error"] == "github_error"


@responses.activate
def test_rate_limit_endpoint_reports_the_budget(client):
    mock_rate_limit(remaining=42)

    response = client.get("/api/rate-limit")

    assert response.status_code == 200
    assert response.json() == {"limit": 60, "remaining": 42, "reset_at": "2030-03-17T17:46:40Z"}


def test_evaluate_only_accepts_get(client):
    assert client.post("/api/evaluate", {"repo": "acme/widget"}).status_code == 405
```

- [ ] **Step 6: Run them to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_views.py`
Expected: failures with status 404 (no routes yet).

- [ ] **Step 7: Implement views and routes**

`backend/evaluator/views.py`:

```python
import re

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .github_client import GitHubClient, GitHubError, NotFound, RateLimited
from .service import evaluate, iso

REPO_PATTERN = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}")


def make_client() -> GitHubClient:
    return GitHubClient(cache, token=settings.GITHUB_TOKEN, ttl_seconds=settings.GITHUB_CACHE_TTL_SECONDS)


def _error(status: int, code: str, message: str, **extra) -> JsonResponse:
    return JsonResponse({"error": code, "message": message, **extra}, status=status)


@require_GET
def evaluate_view(request):
    full_name = request.GET.get("repo", "").strip()
    if not REPO_PATTERN.fullmatch(full_name):
        return _error(400, "invalid_repo", "Use the form owner/name, for example django/django.")
    try:
        result = evaluate(full_name, make_client(), timezone.now())
    except NotFound:
        return _error(404, "not_found", f"{full_name} does not exist or is private.")
    except RateLimited as exc:
        return _error(429, "rate_limited", "GitHub's hourly request limit is used up.", reset_at=iso(exc.reset_at))
    except GitHubError:
        return _error(502, "github_error", "GitHub did not respond as expected. Try again shortly.")
    return JsonResponse(result)


@require_GET
def rate_limit_view(request):
    try:
        budget = make_client().rate_limit()
    except GitHubError:
        return _error(502, "github_error", "Could not read GitHub's rate limit. Try again shortly.")
    return JsonResponse({"limit": budget.limit, "remaining": budget.remaining, "reset_at": iso(budget.reset_at)})
```

`backend/evaluator/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("evaluate", views.evaluate_view, name="evaluate"),
    path("rate-limit", views.rate_limit_view, name="rate-limit"),
]
```

`backend/config/urls.py` (replace the whole file):

```python
from django.urls import include, path

urlpatterns = [path("api/", include("evaluator.urls"))]
```

- [ ] **Step 8: Run all backend tests**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all pass.

- [ ] **Step 9: Smoke-test the real server (the rate-limit call is free)**

Run:

```bash
cd backend && (.venv/bin/python manage.py runserver 8000 > /tmp/regret-check-runserver.log 2>&1 &) && sleep 3 && curl -s http://127.0.0.1:8000/api/rate-limit && echo && curl -s "http://127.0.0.1:8000/api/evaluate?repo=nope" && echo; pkill -f "manage.py runserver 8000"
```

Expected: a JSON budget like `{"limit": 60, "remaining": ..., "reset_at": "..."}`, then `{"error": "invalid_repo", ...}`.

- [ ] **Step 10: Commit**

```bash
git add backend/evaluator/service.py backend/evaluator/views.py backend/evaluator/urls.py backend/config/urls.py backend/evaluator/tests/test_service.py backend/evaluator/tests/test_views.py
git commit -m "feat(backend): evaluation service and /api endpoints" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend skeleton, input parsing and API client

**Files:**
- Create: `frontend/package.json`, `frontend/index.html`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/App.tsx` (placeholder), `frontend/src/setupTests.ts`, `frontend/src/types.ts`, `frontend/src/parseRepo.ts`, `frontend/src/api.ts`
- Test: `frontend/src/parseRepo.test.ts`, `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: the API contract from Task 4 (`/api/evaluate`, `/api/rate-limit`, error body shape).
- Produces:
  - `src/types.ts`: `Status`, `Level`, `Signal`, `RateLimit`, `Evaluation` (fields exactly as the API JSON).
  - `src/parseRepo.ts`: `parseRepo(input: string): string | null`.
  - `src/api.ts`: `type ApiErrorCode = "invalid_repo" | "not_found" | "rate_limited" | "github_error" | "network"`; `class ApiError extends Error { code: ApiErrorCode; resetAt?: string }`; `evaluateRepo(fullName: string): Promise<Evaluation>`; `fetchRateLimit(): Promise<RateLimit>`.

- [ ] **Step 1: Create the project files**

`frontend/package.json`:

```json
{
  "name": "regret-check-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "typecheck": "tsc",
    "test": "vitest run"
  }
}
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Regret Check</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`frontend/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
  },
});
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx` (placeholder until Task 6):

```tsx
export default function App() {
  return <h1>Regret Check</h1>;
}
```

`frontend/src/setupTests.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
```

`frontend/src/types.ts`:

```ts
export type Status = "ok" | "watch" | "risk" | "unknown";
export type Level = "low" | "medium" | "high";

export interface Signal {
  id: string;
  label: string;
  status: Status;
  value: string;
  detail: string;
  evidence_url: string;
}

export interface RateLimit {
  limit: number;
  remaining: number;
  reset_at: string;
}

export interface Evaluation {
  repo: { full_name: string; description: string; html_url: string; stars: number };
  verdict: { level: Level; headline: string; reasons: string[] };
  signals: Signal[];
  meta: { data_as_of: string; stale: boolean; rate_limit: RateLimit };
}
```

- [ ] **Step 2: Install dependencies**

Run:

```bash
cd frontend && npm install react react-dom && npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom vitest jsdom @testing-library/react @testing-library/dom @testing-library/jest-dom @testing-library/user-event
```

Expected: `package.json` gains `dependencies` and `devDependencies`; `package-lock.json` is created.

- [ ] **Step 3: Write the failing tests**

`frontend/src/parseRepo.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseRepo } from "./parseRepo";

describe("parseRepo", () => {
  it.each([
    ["django/django", "django/django"],
    ["  django/django  ", "django/django"],
    ["https://github.com/django/django", "django/django"],
    ["http://www.github.com/django/django/", "django/django"],
    ["github.com/django/django.git", "django/django"],
    ["https://github.com/facebook/react/tree/main/packages", "facebook/react"],
    ["https://github.com/psf/requests?tab=readme-ov-file#readme", "psf/requests"],
  ])("reads %s", (input, expected) => {
    expect(parseRepo(input)).toBe(expected);
  });

  it.each(["", "django", "not a repo", "owner/na me", "https://gitlab.com/group/project"])(
    "rejects %j",
    (input) => {
      expect(parseRepo(input)).toBeNull();
    },
  );
});
```

`frontend/src/api.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { ApiError, evaluateRepo, fetchRateLimit } from "./api";

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async (_url: string) => ({ ok: status < 400, status, json: async () => body }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api", () => {
  it("requests the encoded repository", async () => {
    const fetchMock = stubFetch(200, { signals: [] });
    await evaluateRepo("acme/widget");
    expect(fetchMock).toHaveBeenCalledWith("/api/evaluate?repo=acme%2Fwidget");
  });

  it("turns a 429 into a rate_limited error with the reset time", async () => {
    stubFetch(429, { error: "rate_limited", message: "Limit used up.", reset_at: "2030-03-17T17:46:40Z" });
    await expect(evaluateRepo("acme/widget")).rejects.toMatchObject({
      code: "rate_limited",
      message: "Limit used up.",
      resetAt: "2030-03-17T17:46:40Z",
    });
  });

  it("reports a network failure as an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const failure = evaluateRepo("acme/widget");
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ code: "network" });
  });

  it("reads the rate limit", async () => {
    stubFetch(200, { limit: 60, remaining: 12, reset_at: "2030-03-17T17:46:40Z" });
    await expect(fetchRateLimit()).resolves.toEqual({ limit: 60, remaining: 12, reset_at: "2030-03-17T17:46:40Z" });
  });
});
```

- [ ] **Step 4: Run them to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL, cannot resolve `./parseRepo` and `./api`.

- [ ] **Step 5: Implement parsing and the API client**

`frontend/src/parseRepo.ts`:

```ts
const OWNER = /^[A-Za-z0-9-]{1,39}$/;
const NAME = /^[A-Za-z0-9._-]{1,100}$/;

/** "owner/name" or any github.com URL → "owner/name"; null when it is neither. */
export function parseRepo(input: string): string | null {
  const path = input
    .trim()
    .split(/[?#]/)[0]
    .replace(/^(https?:\/\/)?(www\.)?github\.com\//i, "");
  const [owner, rawName] = path.split("/");
  if (!owner || !rawName) return null;
  const name = rawName.replace(/\.git$/i, "");
  return OWNER.test(owner) && NAME.test(name) ? `${owner}/${name}` : null;
}
```

`frontend/src/api.ts`:

```ts
import type { Evaluation, RateLimit } from "./types";

export type ApiErrorCode = "invalid_repo" | "not_found" | "rate_limited" | "github_error" | "network";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly resetAt?: string;

  constructor(code: ApiErrorCode, message: string, resetAt?: string) {
    super(message);
    this.code = code;
    this.resetAt = resetAt;
  }
}

async function getJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ApiError("network", "Could not reach the server. Is the backend running?");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body?.error ?? "github_error",
      body?.message ?? `Request failed with status ${response.status}.`,
      body?.reset_at,
    );
  }
  return body as T;
}

export function evaluateRepo(fullName: string): Promise<Evaluation> {
  return getJson<Evaluation>(`/api/evaluate?repo=${encodeURIComponent(fullName)}`);
}

export function fetchRateLimit(): Promise<RateLimit> {
  return getJson<RateLimit>("/api/rate-limit");
}
```

- [ ] **Step 6: Run tests, type-check and build**

Run: `cd frontend && npm test && npm run build`
Expected: all tests pass; `tsc` reports nothing; `vite build` writes `dist/`.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/index.html frontend/tsconfig.json frontend/vite.config.ts frontend/src
git commit -m "feat(frontend): Vite skeleton, repo input parsing and typed API client" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend UI

**Files:**
- Create: `frontend/src/format.ts`, `frontend/src/components/RepoForm.tsx`, `frontend/src/components/VerdictBanner.tsx`, `frontend/src/components/SignalCard.tsx`, `frontend/src/components/RateLimitNote.tsx`, `frontend/src/index.css`
- Modify: `frontend/src/App.tsx` (replace placeholder), `frontend/src/main.tsx` (add the CSS import)
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `parseRepo` (Task 5); `ApiError`, `evaluateRepo`, `fetchRateLimit` (Task 5); types from `src/types.ts`.
- Produces: the finished page. Accessible names the tests rely on: input labelled "GitHub repository"; submit button named "Check"; verdict headline as an `h2`; each signal label as an `h3`; errors with `role="alert"`.

- [ ] **Step 1: Write the failing App tests**

`frontend/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Evaluation } from "./types";

const RATE_LIMIT = { limit: 60, remaining: 56, reset_at: "2030-03-17T17:46:40Z" };

const EVALUATION: Evaluation = {
  repo: {
    full_name: "acme/widget",
    description: "A widget library",
    html_url: "https://github.com/acme/widget",
    stars: 1200,
  },
  verdict: { level: "medium", headline: "Medium regret risk", reasons: ["license"] },
  signals: [
    {
      id: "activity",
      label: "Recent activity",
      status: "ok",
      value: "Last commit 3 days ago",
      detail: "Code is still changing.",
      evidence_url: "https://github.com/acme/widget/commits",
    },
    {
      id: "license",
      label: "License",
      status: "risk",
      value: "None",
      detail: "No license detected.",
      evidence_url: "https://github.com/acme/widget",
    },
  ],
  meta: { data_as_of: "2026-11-04T10:00:00Z", stale: false, rate_limit: RATE_LIMIT },
};

function stubApi(evaluate: { status: number; body: unknown }) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const reply = String(input).startsWith("/api/rate-limit") ? { status: 200, body: RATE_LIMIT } : evaluate;
    return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderApp() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText(/56 of 60 GitHub requests left/);
  return user;
}

describe("App", () => {
  it("shows the verdict with the worst signal first", async () => {
    const fetchMock = stubApi({ status: 200, body: EVALUATION });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "https://github.com/acme/widget");
    await user.click(screen.getByRole("button", { name: "Check" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Medium regret risk" })).toBeInTheDocument();
    const cardTitles = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(cardTitles).toEqual(["License", "Recent activity"]);
    expect(screen.getByText("Driven by: License")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/evaluate?repo=acme%2Fwidget");
  });

  it("explains when GitHub's hourly limit is used up", async () => {
    stubApi({
      status: 429,
      body: {
        error: "rate_limited",
        message: "GitHub's hourly request limit is used up.",
        reset_at: "2030-03-17T17:46:40Z",
      },
    });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/60 requests an hour is used up/);
  });

  it("warns when the result comes from an old cached copy", async () => {
    stubApi({ status: 200, body: { ...EVALUATION, meta: { ...EVALUATION.meta, stale: true } } });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    expect(await screen.findByText(/Showing cached data from/)).toBeInTheDocument();
  });

  it("rejects text that is not a repository without calling the API", async () => {
    const fetchMock = stubApi({ status: 200, body: EVALUATION });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "not a repo");
    await user.click(screen.getByRole("button", { name: "Check" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/owner\/name/);
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual(["/api/rate-limit"]);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm test -- src/App.test.tsx`
Expected: FAIL, the placeholder App has no rate-limit text or form.

- [ ] **Step 3: Implement formatting helpers and components**

`frontend/src/format.ts`:

```ts
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
```

`frontend/src/components/RepoForm.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { parseRepo } from "../parseRepo";

const EXAMPLES = [
  { repo: "django/django", note: "very active" },
  { repo: "moment/moment", note: "maintenance mode" },
  { repo: "request/request", note: "deprecated" },
  { repo: "atom/atom", note: "archived" },
];

interface Props {
  onSubmit: (fullName: string) => void;
  disabled: boolean;
}

export function RepoForm({ onSubmit, disabled }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const fullName = parseRepo(text);
    if (!fullName) {
      setError("Enter a GitHub repository as owner/name or paste its URL.");
      return;
    }
    setError(null);
    onSubmit(fullName);
  }

  function pickExample(repo: string) {
    setText(repo);
    setError(null);
    onSubmit(repo);
  }

  return (
    <form className="repo-form" onSubmit={submit} noValidate>
      <label htmlFor="repo">GitHub repository</label>
      <div className="repo-form__row">
        <input
          id="repo"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="owner/name or https://github.com/owner/name"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error !== null}
          aria-describedby={error ? "repo-error" : undefined}
        />
        <button type="submit" disabled={disabled}>
          Check
        </button>
      </div>
      {error && (
        <p id="repo-error" className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="examples">
        Try:
        {EXAMPLES.map(({ repo, note }) => (
          <button key={repo} type="button" className="chip" disabled={disabled} onClick={() => pickExample(repo)}>
            {repo} <span className="chip__note">{note}</span>
          </button>
        ))}
      </p>
    </form>
  );
}
```

`frontend/src/components/VerdictBanner.tsx`:

```tsx
import type { Evaluation } from "../types";

export function VerdictBanner({ evaluation }: { evaluation: Evaluation }) {
  const { repo, verdict, signals } = evaluation;
  const labels = new Map(signals.map((signal) => [signal.id, signal.label]));
  const reasonsLead = verdict.level === "low" ? "Worth a look" : "Driven by";

  return (
    <section className={`verdict verdict--${verdict.level}`} aria-labelledby="verdict-title">
      <p className="verdict__repo">
        <a href={repo.html_url} target="_blank" rel="noreferrer">
          {repo.full_name}
        </a>{" "}
        · ★ {repo.stars.toLocaleString("en")}
      </p>
      <h2 id="verdict-title">{verdict.headline}</h2>
      {repo.description && <p className="verdict__description">{repo.description}</p>}
      {verdict.reasons.length > 0 && (
        <p className="verdict__reasons">
          {reasonsLead}: {verdict.reasons.map((id) => labels.get(id) ?? id).join(", ")}
        </p>
      )}
    </section>
  );
}
```

`frontend/src/components/SignalCard.tsx`:

```tsx
import type { Signal, Status } from "../types";

const STATUS_TEXT: Record<Status, string> = {
  ok: "OK",
  watch: "Watch",
  risk: "Risk",
  unknown: "Not enough data",
};

export function SignalCard({ signal }: { signal: Signal }) {
  return (
    <li className={`signal signal--${signal.status}`}>
      <div className="signal__head">
        <h3>{signal.label}</h3>
        <span className="signal__status">{STATUS_TEXT[signal.status]}</span>
      </div>
      <p className="signal__value">{signal.value}</p>
      <p className="signal__detail">{signal.detail}</p>
      <a href={signal.evidence_url} target="_blank" rel="noreferrer">
        Check on GitHub ↗
      </a>
    </li>
  );
}
```

`frontend/src/components/RateLimitNote.tsx`:

```tsx
import { formatTime } from "../format";
import type { RateLimit } from "../types";

export function RateLimitNote({ rateLimit }: { rateLimit: RateLimit | null }) {
  if (!rateLimit) return null;
  return (
    <p className="rate-limit">
      {rateLimit.remaining} of {rateLimit.limit} GitHub requests left · resets at {formatTime(rateLimit.reset_at)} ·
      a new check uses up to 4
    </p>
  );
}
```

- [ ] **Step 4: Implement the App**

`frontend/src/App.tsx` (replace the placeholder):

```tsx
import { useEffect, useState } from "react";
import { ApiError, evaluateRepo, fetchRateLimit } from "./api";
import { RateLimitNote } from "./components/RateLimitNote";
import { RepoForm } from "./components/RepoForm";
import { SignalCard } from "./components/SignalCard";
import { VerdictBanner } from "./components/VerdictBanner";
import { formatDateTime, formatTime } from "./format";
import type { Evaluation, RateLimit, Status } from "./types";

type State =
  | { kind: "idle" }
  | { kind: "loading"; fullName: string }
  | { kind: "done"; evaluation: Evaluation }
  | { kind: "error"; error: ApiError };

const SEVERITY: Record<Status, number> = { risk: 0, watch: 1, unknown: 2, ok: 3 };

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [rateLimit, setRateLimit] = useState<RateLimit | null>(null);

  useEffect(() => {
    fetchRateLimit()
      .then(setRateLimit)
      .catch(() => undefined);
  }, []);

  async function check(fullName: string) {
    setState({ kind: "loading", fullName });
    try {
      const evaluation = await evaluateRepo(fullName);
      setRateLimit(evaluation.meta.rate_limit);
      setState({ kind: "done", evaluation });
    } catch (error) {
      setState({
        kind: "error",
        error: error instanceof ApiError ? error : new ApiError("network", "Something went wrong."),
      });
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Regret Check</h1>
        <p className="tagline">Will we regret adopting this open-source dependency in two years?</p>
      </header>
      <RepoForm onSubmit={check} disabled={state.kind === "loading"} />
      <RateLimitNote rateLimit={rateLimit} />
      {state.kind === "loading" && (
        <p className="status-line" role="status">
          Checking {state.fullName}…
        </p>
      )}
      {state.kind === "error" && <ErrorMessage error={state.error} />}
      {state.kind === "done" && <Result evaluation={state.evaluation} />}
    </main>
  );
}

function Result({ evaluation }: { evaluation: Evaluation }) {
  const signals = [...evaluation.signals].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]);
  return (
    <>
      {evaluation.meta.stale && (
        <p className="notice" role="status">
          Showing cached data from {formatDateTime(evaluation.meta.data_as_of)}: GitHub's hourly limit is used up.
        </p>
      )}
      <VerdictBanner evaluation={evaluation} />
      <ul className="signals">
        {signals.map((signal) => (
          <SignalCard key={signal.id} signal={signal} />
        ))}
      </ul>
    </>
  );
}

function ErrorMessage({ error }: { error: ApiError }) {
  const text =
    error.code === "rate_limited" && error.resetAt
      ? `GitHub's free limit of 60 requests an hour is used up. It resets at ${formatTime(error.resetAt)}. Repositories checked recently still work.`
      : error.message;
  return (
    <p className="error" role="alert">
      {text}
    </p>
  );
}
```

- [ ] **Step 5: Add the styles**

`frontend/src/index.css`:

```css
:root {
  color-scheme: light dark;
  --bg: #f7f7f5;
  --surface: #ffffff;
  --text: #1c1c1a;
  --muted: #5f5f5a;
  --border: #deded8;
  --accent: #2f5bd3;
  --ok: #1f7a3d;
  --ok-bg: #e6f4ea;
  --watch: #8a5a00;
  --watch-bg: #fff4d6;
  --risk: #b42318;
  --risk-bg: #fde8e6;
  --unknown: #5f5f5a;
  --unknown-bg: #efefeb;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615;
    --surface: #1f1f1d;
    --text: #ececea;
    --muted: #a3a39d;
    --border: #34342f;
    --accent: #8aa8ff;
    --ok: #6fd08f;
    --ok-bg: #16301f;
    --watch: #f2c35b;
    --watch-bg: #33280f;
    --risk: #ff8a7a;
    --risk-bg: #3a1714;
    --unknown: #a3a39d;
    --unknown-bg: #2a2a27;
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}

a {
  color: var(--accent);
}

.app {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 16px 64px;
}

h1 {
  margin: 0;
  font-size: 1.75rem;
}

.tagline {
  margin: 4px 0 24px;
  color: var(--muted);
}

.repo-form label {
  display: block;
  margin-bottom: 6px;
  font-weight: 600;
}

.repo-form__row {
  display: flex;
  gap: 8px;
}

.repo-form input {
  flex: 1;
  min-width: 0;
  padding: 10px 12px;
  font: inherit;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.repo-form button[type="submit"] {
  padding: 10px 18px;
  font: inherit;
  font-weight: 600;
  color: #fff;
  background: var(--accent);
  border: 0;
  border-radius: 8px;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: default;
}

.form-error {
  margin: 8px 0 0;
  color: var(--risk);
}

.examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  color: var(--muted);
  font-size: 0.9rem;
}

.chip {
  padding: 4px 10px;
  font: inherit;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  cursor: pointer;
}

.chip__note {
  color: var(--muted);
}

.rate-limit {
  margin: 16px 0 0;
  color: var(--muted);
  font-size: 0.85rem;
}

.status-line {
  margin: 24px 0 0;
}

.notice,
.error {
  margin: 24px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
}

.notice {
  color: var(--watch);
  background: var(--watch-bg);
}

.error {
  color: var(--risk);
  background: var(--risk-bg);
}

.verdict {
  margin: 24px 0 16px;
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 6px solid var(--unknown);
  border-radius: 12px;
}

.verdict--low {
  border-left-color: var(--ok);
}

.verdict--medium {
  border-left-color: var(--watch);
}

.verdict--high {
  border-left-color: var(--risk);
}

.verdict h2 {
  margin: 4px 0;
  font-size: 1.5rem;
}

.verdict__repo,
.verdict__description {
  margin: 0;
  color: var(--muted);
}

.verdict__reasons {
  margin: 8px 0 0;
}

.signals {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.signal {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.signal__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.signal h3 {
  margin: 0;
  font-size: 1rem;
}

.signal__status {
  padding: 2px 10px;
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
  border-radius: 999px;
}

.signal--ok .signal__status {
  color: var(--ok);
  background: var(--ok-bg);
}

.signal--watch .signal__status {
  color: var(--watch);
  background: var(--watch-bg);
}

.signal--risk .signal__status {
  color: var(--risk);
  background: var(--risk-bg);
}

.signal--unknown .signal__status {
  color: var(--unknown);
  background: var(--unknown-bg);
}

.signal__value {
  margin: 8px 0 4px;
  font-weight: 600;
}

.signal__detail {
  margin: 0 0 8px;
  color: var(--muted);
}

@media (max-width: 480px) {
  .repo-form__row {
    flex-direction: column;
  }
}
```

In `frontend/src/main.tsx`, add this line directly below `import App from "./App";`:

```tsx
import "./index.css";
```

- [ ] **Step 6: Run tests, type-check and build**

Run: `cd frontend && npm test && npm run build`
Expected: all tests pass (parseRepo, api, App); build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): report UI with verdict, signals, budget and error states" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: End-to-end check and README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the running backend (Task 4) and frontend (Task 6).
- Produces: `README.md` with the three sections the brief requires, run instructions, and observed example results.

- [ ] **Step 1: Run both servers and check four real repositories**

This spends up to 16 of the 60 hourly GitHub requests. Check the budget first and stop if fewer than 16 remain.

Run:

```bash
cd backend && (.venv/bin/python manage.py runserver 8000 > /tmp/regret-check-runserver.log 2>&1 &) && cd ../frontend && (npm run dev -- --port 5173 --strictPort > /tmp/regret-check-vite.log 2>&1 &) && sleep 5 && curl -s http://127.0.0.1:5173/api/rate-limit && echo
```

Expected: a JSON budget, served through the Vite proxy (proves the proxy works). Then, if `remaining` is at least 16:

```bash
for repo in django/django moment/moment request/request atom/atom; do curl -s "http://127.0.0.1:5173/api/evaluate?repo=$repo" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["repo"]["full_name"], "|", d["verdict"]["headline"], "|", ", ".join(f"{s[\"id\"]}={s[\"status\"]}" for s in d["signals"]))'; done
```

Expected: one line per repo. `atom/atom` must be "High regret risk" with `status=risk`. Write down all four lines for Step 2. If any result looks wrong against the rules in the spec, stop and report it instead of continuing.

Also check `curl -s http://127.0.0.1:5173/ | grep -o "<title>Regret Check</title>"` prints the title. Stop both servers:

```bash
pkill -f "manage.py runserver 8000"; pkill -f "vite --port 5173"
```

- [ ] **Step 2: Write the README**

Create `README.md` with exactly this content, replacing the four `Example results` table rows with the four lines observed in Step 1 (repo, headline, and the signals that were not `ok`):

````markdown
# Regret Check

Will we regret adopting this open-source dependency in two years? Paste a GitHub repository and get an explained risk report built from GitHub's public API.

## What "will we regret this" means

Two years after adopting a library, regret usually comes from one of two places:

1. **We need a fix and nobody is there to make it.** The project was archived, went quiet, depended on one person who left, or stopped answering bug reports.
2. **We can't keep using it the way we do.** No license, or a copyleft / source-available license that doesn't fit a commercial product.

Stars and downloads tell you a library is popular today. They say little about who will fix it in 2028. So the report looks only at maintenance and license.

### Signals

| Signal | Risk when | Watch when |
|---|---|---|
| Archived | the repository is archived | – |
| License | there is no license | copyleft, source-available or custom |
| Recent activity | no commit for over a year | no commit for over 90 days |
| Bus factor | one person wrote ≥ 80% of last year's human commits | ≥ 50% |
| Issue response | > 50% of issues older than two weeks are open with no reply | > 20% |
| Releases | – | no release in a year, or no releases at all |

Bots such as Dependabot and Renovate are excluded from authorship and issue counts. With too little data a signal says "Not enough data" instead of guessing, and it does not count toward the verdict.

### How the verdict is decided

- **High** if the repo is archived or unlicensed, or if two signals are at risk.
- **Medium** if one signal is at risk, or two need watching.
- **Low** otherwise.

**Why flags and not a score.** A 0–100 score needs weights, and I had no data to choose them, so the precision would be fake. Every flag here comes with the reason it matters and a link to the GitHub page that proves it, so the reader can disagree with a specific flag instead of with a number.

**Why these thresholds.** They are starting points chosen to be easy to explain ("no commit in a year"), not fitted to data. Tuning them against dependencies teams actually regretted is the first thing I'd do next.

### Example results

| Repository | Verdict | Flags |
|---|---|---|
| django/django | … | … |
| moment/moment | … | … |
| request/request | … | … |
| atom/atom | … | … |

## Dealing with the 60 requests/hour limit

- **Measured first.** Without a token, a conditional request that returns `304 Not Modified` still counts against the limit, so ETag caching saves nothing. `GET /rate_limit` is free. The design follows from those two facts.
- **One check costs at most 4 requests:** repository, last 100 commits, last 10 releases, last 100 issues. Issues are skipped when the repo has them turned off.
- **Time-based cache.** Every GitHub response is cached per URL. For an hour (`GITHUB_CACHE_TTL_SECONDS`) a repeat check costs nothing.
- **No half-spent checks.** Before a check the backend reads the free budget. If it can't afford the uncached calls, it answers from the cache (even a stale copy, clearly labelled with its age) or refuses with the reset time. It never spends two calls and then fails on the third.
- **Visible budget.** The page shows how many requests are left and when the limit resets.
- **Optional token.** Set `GITHUB_TOKEN` on the server to get 5,000 requests/hour. It never reaches the browser.

## What I deliberately cut

- **Comparing two or three candidates side by side.** Useful, but triples the API cost and doubles the UI.
- **Package-registry data** (npm/PyPI downloads, dependents) and **vulnerability data.** Worth having, but they are other APIs and the brief says GitHub.
- **License-change history.** Catching "MIT last year, BSL now" needs the history of the license file, so several calls per check.
- **Auth, a database, ETag revalidation.** Not needed for the core question. ETags were dropped after measuring that they don't save quota without a token.

## What I'd do next

1. Calibrate thresholds on a list of dependencies people regretted, and on ones they didn't.
2. Measure time to first *maintainer* reply instead of "issue with no comments". That needs comments per issue, so a token.
3. Side-by-side comparison for "which of these should we pick".
4. Add OpenSSF Scorecard and deps.dev for security practices and real-world dependents.

## How I used AI tools

I used Claude Code (Claude Opus 5.5) throughout:

- It read the brief and drafted the clarifying questions; I chose what to ask.
- It proposed three approaches (explained flags, a weighted score, side-by-side comparison) along with the signals and thresholds. I picked the flags approach and approved the design (`docs/superpowers/specs/`).
- It found by measurement that unauthenticated `304`s still count against the limit, which changed the caching design.
- It wrote the implementation plan (`docs/superpowers/plans/`) and generated the code task by task with subagents, with a review after each task.

My part: deciding what to build and what to cut, the final call on signals and thresholds, reviewing the code and the results, and the reasoning in this README.

## Running it locally

Backend (Python 3.12):

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py runserver 8000
```

Frontend (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend on port 8000.

Optional environment variables for the backend: `GITHUB_TOKEN`, `GITHUB_CACHE_TTL_SECONDS` (default 3600), `CACHE_DIR`.

Tests:

```bash
cd backend && .venv/bin/python -m pytest
```

```bash
cd frontend && npm test
```

## Project layout

```
backend/evaluator/signals.py        pure rules: GitHub data → signals → verdict
backend/evaluator/github_client.py  HTTP, cache, rate-limit handling
backend/evaluator/service.py        one evaluation: budget check, fetches, report
backend/evaluator/views.py          GET /api/evaluate?repo=owner/name, GET /api/rate-limit
frontend/src/                       React + TypeScript UI
docs/superpowers/                   design spec and implementation plan
```
````

- [ ] **Step 3: Check the README has no leftover placeholders**

Run: `grep -n "…" README.md`
Expected: no output (all four example rows were filled in).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README with regret definition, cuts, AI use and example results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8 (optional): Single Docker image for deployment

Skip this task if Docker is not available or it takes more than 30 minutes.

**Files:**
- Create: `Dockerfile`, `.dockerignore`
- Modify: `backend/requirements.txt`, `backend/config/settings.py`, `README.md`

**Interfaces:**
- Consumes: the built frontend (`frontend/dist`) and the backend.
- Produces: an image that serves the UI at `/` and the API at `/api/` on `$PORT` (default 8000).

- [ ] **Step 1: Add the runtime dependencies**

Append to `backend/requirements.txt`:

```text
gunicorn>=23
whitenoise>=6.7
```

Run: `cd backend && .venv/bin/pip install -q -r requirements-dev.txt`

- [ ] **Step 2: Serve the built frontend from Django**

In `backend/config/settings.py`, replace the line `MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]` with:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

STATIC_URL = "static/"

# In production the built React app is served from the site root by WhiteNoise.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = str(FRONTEND_DIST)
    WHITENOISE_INDEX_FILE = True
```

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all pass.

- [ ] **Step 3: Write the Dockerfile**

`Dockerfile`:

```dockerfile
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0 \
    DJANGO_ALLOWED_HOSTS=* \
    FRONTEND_DIST=/app/frontend/dist \
    CACHE_DIR=/tmp/regret-check-cache
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2"]
```

`.dockerignore`:

```text
.git
**/.venv
**/__pycache__
**/node_modules
frontend/dist
backend/.cache
```

- [ ] **Step 4: Build and run the image**

Run:

```bash
docker build -t regret-check . && docker run --rm -d -p 8001:8000 --name regret-check regret-check && sleep 4 && curl -s http://127.0.0.1:8001/ | grep -o "<title>Regret Check</title>" && curl -s http://127.0.0.1:8001/api/rate-limit && echo; docker stop regret-check
```

Expected: `<title>Regret Check</title>` and a JSON budget.

- [ ] **Step 5: Document deployment**

In `README.md`, insert this section directly above `## Project layout`:

````markdown
## Deploying

One Docker image serves both the UI and the API:

```bash
docker build -t regret-check .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me regret-check
```

On Render: New → Web Service → this repository → runtime Docker. Set `DJANGO_SECRET_KEY`, and optionally `GITHUB_TOKEN`. Railway and Fly pick up the same Dockerfile. The cache lives in `/tmp`, so it resets on each deploy.
````

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore backend/requirements.txt backend/config/settings.py README.md
git commit -m "build: single Docker image serving UI and API" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
