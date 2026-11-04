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

### Example results (checked 2026-11-04)

| Repository | Verdict | Flags |
|---|---|---|
| django/django | Low regret risk | Issue response (unknown), Releases (watch) |
| moment/moment | Medium regret risk | Bus factor (watch), Issue response (watch) |
| request/request | High regret risk | Recent activity (risk), Bus factor (unknown), Issue response (risk), Releases (watch) |
| atom/atom | High regret risk | Archived (risk), Recent activity (risk), Bus factor (unknown), Issue response (risk), Releases (watch) |

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

Open http://localhost:5173. Vite proxies `/api` to the backend on port 8000. If port 8000 is taken, run the backend on another port and point Vite at it: `API_URL=http://127.0.0.1:8765 npm run dev`.

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
