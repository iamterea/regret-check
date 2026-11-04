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
