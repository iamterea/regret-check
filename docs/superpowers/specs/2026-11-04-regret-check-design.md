# Regret Check — design

Date: 2026-11-04
Status: implemented on branch feature/regret-check; updated 2026-11-04 with Simfoni's answers.

## Problem

A team is about to adopt an open-source dependency. Today the decision is a gut feel after scrolling the GitHub page. The question to answer is not "does it work today" but "will we regret this in two years".

Constraints from the brief: React + TypeScript frontend, Python + Django backend, GitHub public API as the data source, unauthenticated limit of 60 requests/hour, one-evening scope. Assessed on product judgment first, implementation quality second. Completeness is not assessed.

## Answers from Simfoni (2026-11-04)

1. **Who and when:** "More for leads or teams exploring packages to use for functionality and want to use only good, maintained ones." Changed: the tool compares 2–4 repositories side by side, lowest risk first.
2. **What went wrong before:** "The dependency on single person can lead to less updates or sometimes no updates." Changed: `bus_factor` is a dealbreaker (`risk` makes the verdict `high`), and when every human commit of the last year comes from one person that is `risk` however few commits there are (before, under 5 commits was `unknown`).
3. **Token:** "Yes, anything is fine here." Changed: when deployed, set `GITHUB_TOKEN` (already supported; `render.yaml` asks for it). Unauthenticated mode and its rate-limit handling stay.

## Approach

A risk report made of explained flags, not a score. Each signal has a status (`ok`, `watch`, `risk`, `unknown`), a short value, a plain-English explanation of why it matters, and a link to the GitHub page that proves it. A small rule set turns the flags into a verdict.

Rejected: a weighted 0–100 score (the weights would be invented, and "why 73?" has no honest answer).

Side-by-side comparison was first cut for scope and added after Simfoni said the users are leads and teams choosing between packages.

## Signals

All windows are relative to "now" at evaluation time.

| id | Label | Rule | Source |
|---|---|---|---|
| `status` | Archived | `archived` → `risk` (dealbreaker); otherwise `ok` | repo |
| `license` | License | none detected → `risk` with value "Not detected" (not a dealbreaker); SPDX id in the permissive list → `ok`; anything else (copyleft, source-available, `NOASSERTION`) → `watch` with "check it fits a commercial product" | repo |
| `activity` | Recent activity | age of the newest commit on the default branch: ≤ 90 days `ok`, ≤ 365 days `watch`, > 365 days `risk`. The explanation notes that small "finished" libraries can be legitimately quiet. | commits |
| `bus_factor` | Bus factor | among non-bot commits from the last 365 days in the newest 100 commits: one author only (at least 1 commit) → `risk`, and with fewer than 5 commits the detail says the evidence is thin; otherwise fewer than 5 such commits → `unknown`; top author share ≥ 80% `risk`, ≥ 50% `watch`, else `ok` (dealbreaker). | commits |
| `issues` | Issue response | among non-bot issues (PRs excluded) in the newest 100, those created ≥ 14 days ago: share that are still open with zero comments. ≤ 20% `ok`, ≤ 50% `watch`, > 50% `risk`. Fewer than 5 such issues, or issues disabled on the repo → `unknown`. | issues |
| `releases` | Releases | newest non-draft release: ≤ 365 days `ok`; older, or no releases → `watch` (never `risk`: some projects ship only tags or registry versions). | releases |

Permissive SPDX ids: `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `0BSD`, `Unlicense`, `Zlib`, `BSL-1.0`, `CC0-1.0`, `PSF-2.0`, `Python-2.0`.

A commit or issue author is a bot when the GitHub user's `type` is `Bot` or the login/name ends with `[bot]`.

### Verdict

- `high` if any dealbreaker (`status` or `bus_factor`) is `risk`, or if two or more signals are `risk`.
- `medium` if exactly one signal is `risk`, or two or more are `watch`.
- `low` otherwise.
- `unknown` signals do not count.
- `license` is not a dealbreaker: GitHub's detection misses some license files, so "Not detected" is a risk to verify by hand, not proof of no license.

The verdict carries a headline ("Low regret risk", "Medium regret risk", "High regret risk") and `reasons`: the ids of `risk` signals, then the ids of `watch` signals, each group in signal-table order.

## Rate limit handling

Measured on 2026-11-04 against the live API: an unauthenticated conditional request that returns `304` **still** decrements `X-RateLimit-Remaining`, so ETag revalidation saves no quota without a token. `GET /rate_limit` does not decrement it. The design follows from that:

- **Cost:** one evaluation makes at most 4 requests (repo, commits, releases, issues; issues is skipped when the repo has issues disabled). That is about 15 fresh evaluations per hour.
- **Fresh cache:** each GitHub response is cached by URL. Within `GITHUB_CACHE_TTL_SECONDS` (default 3600) it is served with no request at all.
- **Budget pre-check:** before fetching, the backend reads `/rate_limit` (free) and counts the requests it may need (URLs without a fresh cache entry; the issues call is counted even when the repo turns out to have issues disabled, since that is only known after fetching the repo). If the budget is short, the evaluation runs offline: every URL must come from the cache (fresh or stale), otherwise the API returns `429` with the reset time. An evaluation never spends half its calls and then fails.
- **Stale fallback:** cache entries are kept for 7 days. If GitHub reports the limit exhausted mid-evaluation (another client on the same IP), the older cached copy is used. Any stale copy marks the whole response `stale`. With no copy, the API returns `429` with the reset time.
- **Visible budget:** the UI shows the remaining requests and the reset time, from a free `/api/rate-limit` call on load and from every evaluation response.

## Architecture

```
backend/                 Django 5.2, no database
  config/                settings, urls, wsgi
  evaluator/
    github_client.py     HTTP to api.github.com, per-URL cache, rate-limit errors
    signals.py           pure functions: raw API data + now → signals, verdict
    service.py           orchestrates one evaluation: budget check, 4 fetches, signals
    views.py             GET /api/evaluate?repo=owner/name, GET /api/rate-limit
frontend/                Vite + React + TypeScript
  src/parseRepo.ts       "owner/name" or any github.com URL → owner/name
  src/api.ts             typed fetch wrappers, typed errors
  src/errors.ts          describeError: shared wording for failed checks
  src/status.ts          status labels (text, never colour alone)
  src/components/        RepoForm, VerdictBanner, SignalCard, RateLimitNote, ComparisonTable
  src/App.tsx            idle / loading / result / error / compared states
```

Units and boundaries:

- `github_client` knows HTTP, caching and GitHub's rate-limit headers. It knows nothing about signals.
- `signals` is pure: dicts in, dataclasses out, `now` passed in. No I/O, so it is tested with plain fixtures.
- `service` is the only place that knows which endpoints an evaluation needs.
- `views` validate input and map exceptions to HTTP status codes.

Cache: Django's `FileBasedCache` (shared across gunicorn workers on one host). Tests use `LocMemCache`.

### API contract

`GET /api/evaluate?repo=owner/name` → `200`

```json
{
  "repo": {"full_name": "psf/requests", "description": "...", "html_url": "https://github.com/psf/requests", "stars": 52000},
  "verdict": {"level": "low", "headline": "Low regret risk", "reasons": []},
  "signals": [
    {"id": "activity", "label": "Recent activity", "status": "ok", "value": "3 days ago", "detail": "...", "evidence_url": "https://github.com/psf/requests/commits"}
  ],
  "meta": {"data_as_of": "2026-11-04T10:00:00Z", "stale": false, "rate_limit": {"limit": 60, "remaining": 52, "reset_at": "2026-11-04T10:42:00Z"}}
}
```

`data_as_of` is when the oldest GitHub response used in the report was fetched (it differs from now when cached copies were used). `meta.rate_limit` is `null` when GitHub's `/rate_limit` endpoint could not be read; the evaluation then answers from the cache only.

Errors (all JSON `{"error": <code>, "message": <text>}`):

| Status | `error` | When |
|---|---|---|
| 400 | `invalid_repo` | `repo` missing or not `owner/name` |
| 404 | `not_found` | GitHub says the repo does not exist or is private |
| 429 | `rate_limited` | budget too low and no usable cache; body adds `reset_at` |
| 502 | `github_error` | any other GitHub failure with no usable cache |

`GET /api/rate-limit` → `200 {"limit": 60, "remaining": 52, "reset_at": "..."}`.

## Frontend

- One input that accepts `owner/name`, `https://github.com/owner/name`, `github.com/owner/name`, with or without `.git`, a trailing slash or extra path (`/tree/main`).
- Example chips that show the range of verdicts: `atom/atom` (archived), `request/request` (deprecated but not archived: only the activity signal catches it), `moment/moment` (maintenance mode), `django/django` (healthy).
- Result: verdict banner, then one card per signal, worst status first. Status is shown as a text label plus colour, never colour alone.
- Rate-limit note: "41 of 60 GitHub requests left · resets at 14:32 · each repository checked uses up to 4". A `stale` result shows "Showing cached data from <time>: fresh data from GitHub wasn't available."
- The input also takes up to 4 repositories separated by spaces, commas or new lines. 2–4 repositories render a comparison table (signals as rows, repositories as columns, lowest risk first, failed ones last with their error). "Details" under a column shows that repository's full report. A "Compare date libraries" example chip loads moment, date-fns, dayjs and luxon.
- Comparison details: a stale column is labelled "Cached <time>"; a failed column shows the same wording as the single-check error (a rate-limited one includes the reset time); successful columns link GitHub's own name for the repository. The selected column's button reads "Showing details" (`aria-pressed`), and focus moves to the "Details: <repo>" heading above its report.
- Cost: a comparison of four repositories costs up to 16 requests. The checks run in parallel, so near the limit one column can fail after spending some calls; what it fetched stays cached.
- Error states: invalid input (inline, before any request), not found, rate limited (with reset time), GitHub error.

## Error handling

- Input is validated on the client (fast feedback) and again on the server (`^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$`).
- Rate limit is detected as status `429`, or `403` with `X-RateLimit-Remaining: 0`.
- A missing optional field from GitHub (no license, empty commit list, no releases) yields a defined signal status, never a 500.

## Testing

- Backend, pytest + `responses` (no real network): signal rules at each threshold boundary, verdict rules, client cache/stale/rate-limit paths, view status codes.
- Frontend, vitest + Testing Library: `parseRepo` cases, `App` happy path and rate-limited path with `fetch` mocked, and comparison tests (ordering, failed/stale/rate-limited columns, details focus).
- One manual end-to-end run against the real API with the four example repos, and a live run of the date-library comparison (see the README).

## Deliberately cut

Package-registry data (npm/PyPI downloads, dependents); vulnerability/CVE data; license-change history; auth and a database; ETag revalidation (no quota benefit without a token, measured).

## Deployment

One Docker image: a Node stage builds the frontend, a Python stage serves the API and the built files with WhiteNoise via gunicorn (2 workers × 4 threads, so a 4-repository comparison runs in parallel). `render.yaml` is a Render Blueprint: it generates `DJANGO_SECRET_KEY` and asks for `GITHUB_TOKEN`. The same Dockerfile works on Railway or Fly. Built and checked locally on 2026-11-05; not deployed yet.

## Open questions

Answered — see "Answers from Simfoni".
