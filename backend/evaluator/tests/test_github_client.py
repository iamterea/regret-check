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
