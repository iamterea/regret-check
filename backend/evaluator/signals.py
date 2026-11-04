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
            "Not detected",
            "GitHub didn't recognise a license here. Check the repository's LICENSE file or its package page "
            "before adopting: with no license at all you have no right to use the code.",
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
    counts = Counter(authors)
    if len(counts) == 1:
        # One person behind every recent commit is the regret Simfoni named, however few commits there are.
        author, total = counts.most_common(1)[0]
        written = "the only commit" if total == 1 else f"all {total} commits"
        detail = "One person wrote every commit in the last year. If they step away, nobody else knows the code."
        if total < MIN_SAMPLE:
            detail += f" Only {total} {'commit' if total == 1 else 'commits'} in the last year, so the evidence is thin."
        return Signal(
            "bus_factor",
            "Bus factor",
            RISK,
            f"{author} wrote {written}",
            detail,
            url,
        )
    if len(authors) < MIN_SAMPLE:
        return Signal(
            "bus_factor",
            "Bus factor",
            UNKNOWN,
            f"{len(authors)} human commits in the last year",
            "Too few commits in the last year to tell who maintains it.",
            url,
        )
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


# Archived, or carried by one person (Simfoni's regret). A license GitHub can't recognise is a risk to verify,
# not a dealbreaker: it often means a non-standard license file.
DEALBREAKERS = frozenset({"status", "bus_factor"})
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
