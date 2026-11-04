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


@responses.activate
def test_budget_check_counts_the_issues_call_before_it_knows_issues_are_disabled(memory_cache):
    mock_rate_limit(remaining=3)
    responses.add(responses.GET, f"{API}/repos/acme/widget", json=make_repo(has_issues=False))

    with pytest.raises(RateLimited):
        evaluate("acme/widget", make_client(memory_cache, FakeClock()), NOW)

    assert [call.request.url for call in responses.calls] == [f"{API}/rate_limit"]
