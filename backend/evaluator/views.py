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
        return _error(429, "rate_limited", "Not enough GitHub requests left for a new check.", reset_at=iso(exc.reset_at))
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
