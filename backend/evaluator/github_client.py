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
