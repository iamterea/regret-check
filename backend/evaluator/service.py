"""One evaluation: check the budget, fetch what is needed, build the report."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .github_client import GitHubClient, GitHubError, RateLimited
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
    # /rate_limit is free but can fail on its own. A fully cached evaluation needs no
    # requests, so an unreadable budget only means "answer from the cache".
    try:
        budget = client.rate_limit()
    except GitHubError:
        budget = None
    # An upper bound: the issues call is counted even for repos with issues disabled, because
    # that is only known after the repo call. Over-counting can refuse at exactly 3 remaining;
    # under-counting could spend calls and then fail.
    needed = sum(not client.is_fresh(path, params) for path, params in endpoints.values())
    # Not enough budget for the uncached calls: answer from the cache or not at all,
    # rather than spend half the calls and then fail.
    offline = budget is None or needed > budget.remaining

    def fetch(name: str):
        path, params = endpoints[name]
        if not offline:
            return client.get(path, params)
        data = client.cached(path, params)
        if data is None:
            if budget is None:
                raise GitHubError("GitHub's rate limit could not be read and nothing is cached")
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
            "rate_limit": None
            if budget is None
            else {
                "limit": budget.limit,
                "remaining": max(budget.remaining - client.requests_made, 0),
                "reset_at": iso(budget.reset_at),
            },
        },
    }
