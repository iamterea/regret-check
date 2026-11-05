# Regret Check

Will we regret adopting this open-source dependency in two years? Paste a GitHub repository, or up to four to compare side by side, and get an explained risk report built from GitHub's public API.

**Demo video (4:35):** [docs/regret-check-demo.mp4](docs/regret-check-demo.mp4), a walkthrough with voice-over, then one decision I'm not certain about.

## What "will we regret this" means

Two years after adopting a library, regret usually comes from one of two places:

1. **We need a fix and nobody is there to make it.** The project was archived, went quiet, depended on one person who left, or stopped answering bug reports.
2. **We can't keep using it the way we do.** No license, or a copyleft / source-available license that doesn't fit a commercial product.

Stars and downloads tell you a library is popular today. They say little about who will fix it in 2028. So the report looks only at maintenance and license.

### Signals

| Signal | Risk when | Watch when |
|---|---|---|
| Archived | the repository is archived | – |
| License | GitHub detects no license (check the LICENSE file yourself) | copyleft, source-available or custom |
| Recent activity | no commit for over a year | no commit for over 90 days |
| Bus factor | one person wrote ≥ 80% of last year's human commits, or all of them however few | ≥ 50% |
| Issue response | > 50% of issues older than two weeks are open with no reply | > 20% |
| Releases | – | no release in a year, or no releases at all |

Bots such as Dependabot and Renovate are excluded from authorship and issue counts. With too little data a signal says "Not enough data" instead of guessing, and it does not count toward the verdict, except bus factor: if every recent commit comes from one person, that already says enough.

### How the verdict is decided

- **High** if the repo is archived or carried by one person, or if two signals are at risk.
- **Medium** if one signal is at risk, or two need watching.
- A license GitHub can't recognise is a risk to check, not a dealbreaker: it often means a non-standard license file, not no license.
- **Low** otherwise.
- When two or more signals lack data, the page says the verdict rests on limited evidence.

**Why one person is a dealbreaker.** Simfoni said the dependency they regret is the one that hangs on a single person: updates slow down or stop. So a project where one person wrote 80% or more of last year's commits, or all of them however few, is high risk, even if it is active today.

**Why flags and not a score.** A 0–100 score needs weights, and I had no data to choose them, so the precision would be fake. Every flag here comes with the reason it matters and a link to the GitHub page that proves it, so the reader can disagree with a specific flag instead of with a number.

**Why these thresholds.** They are starting points chosen to be easy to explain ("no commit in a year"), not fitted to data. Tuning them against dependencies teams actually regretted is the first thing I'd do next.

### Example results (checked 2026-11-04)

| Repository | Verdict | Flags |
|---|---|---|
| django/django | Low regret risk | Issue response (unknown), Releases (watch) |
| moment/moment | Medium regret risk | Bus factor (watch), Issue response (watch) |
| request/request | High regret risk | Recent activity (risk), Bus factor (unknown), Issue response (risk), Releases (watch) |
| atom/atom | High regret risk | Archived (risk), Recent activity (risk), Bus factor (unknown), Issue response (risk), Releases (watch) |

### Example comparison: date libraries (checked 2026-11-04)

| Repository | Verdict | Flags |
|---|---|---|
| iamkun/dayjs | Low regret risk | Bus factor (watch), Issue response (unknown) |
| moment/moment | Medium regret risk | Bus factor (watch), Issue response (watch) |
| moment/luxon | Medium regret risk | Issue response (watch), Releases (watch) |
| date-fns/date-fns | High regret risk | License (risk), Bus factor (risk), Issue response (risk) |

How to read it: date-fns is High because one person wrote 92% of last year's commits and most of its older issues got no reply, which is exactly the single-person regret Simfoni named. Its License flag only means GitHub doesn't recognise its MIT license text. moment comes out Medium even though its maintainers advise against it for new projects: commit and issue signals can't see a deprecation notice.

## Dealing with the 60 requests/hour limit

- **Measured first.** Without a token, a conditional request that returns `304 Not Modified` still counts against the limit, so ETag caching saves nothing. `GET /rate_limit` is free. The design follows from those two facts.
- **One check costs at most 4 requests:** repository, last 100 commits, last 10 releases, last 100 issues and pull requests (pull requests are filtered out). Issues are skipped when the repo has them turned off. A comparison of four repositories costs up to 16.
- **Time-based cache.** Every GitHub response is cached per URL. For an hour (`GITHUB_CACHE_TTL_SECONDS`) a repeat check costs nothing.
- **No half-spent single checks.** Before a check the backend reads the free budget. If it can't afford the uncached calls, it answers from the cache (even a stale copy up to a week old, clearly labelled with its age) or refuses with the reset time, instead of starting a check it can't finish. If GitHub fails partway (another client on the same IP, an outage), responses already fetched stay cached, so a retry doesn't pay for them again. If the budget endpoint itself is down, it answers from the cache only. In a comparison the checks run in parallel, so near the limit one column can fail after spending some calls; what it fetched stays cached.
- **Visible budget.** The page shows how many requests are left and when the limit resets.
- **Token.** Simfoni confirmed a server-side token is fine: when deployed, set `GITHUB_TOKEN` to get 5,000 requests/hour. It never reaches the browser. Everything above keeps the app usable without one.

## What Simfoni told me

I asked three questions before building. The answers changed the product:

| Question | Answer | What changed |
|---|---|---|
| Who uses this, and when? | Leads or teams exploring packages for some functionality, who want only good, maintained ones. | You can compare up to 4 repositories side by side, lowest risk first. |
| What went wrong with a dependency before? | Dependence on a single person: fewer updates, sometimes none. | Bus factor is a dealbreaker. A project carried by one person is high risk. |
| Is a server-side GitHub token OK? | Yes. | When deployed, set `GITHUB_TOKEN` (5,000 requests/hour). Without it the app still works within 60/hour. |

## Known limitations

- For very busy repositories the newest 100 issues and pull requests can all be under two weeks old, so Issue response shows "Not enough data".
- GitHub's license detection misses some license files, so "Not detected" needs a manual check.
- Deprecation notices (README banners, npm "deprecated") are invisible to the signals.
- A small, finished utility with one maintainer comes out High. That is deliberate: it is the dependency Simfoni said they regret.
- Near the rate limit, a parallel comparison can half-spend one column's calls (see above).

## What I deliberately cut

- **Package-registry data** (npm/PyPI downloads, dependents) and **vulnerability data.** Worth having, but they are other APIs and the brief says GitHub.
- **License-change history.** Catching "MIT last year, BSL now" needs the history of the license file, so several calls per check.
- **Auth, a database, ETag revalidation.** Not needed for the core question. ETags were dropped after measuring that they don't save quota without a token.

## What I'd do next

1. Calibrate thresholds on a list of dependencies people regretted, and on ones they didn't.
2. Measure time to first *maintainer* reply instead of "issue with no comments". That needs comments per issue, so a token.
3. Read deprecation notices (README banners, npm "deprecated" field), so a project like moment that asks you not to use it is flagged.
4. When GitHub can't recognise a license, look for a LICENSE or COPYING file (one extra request) so a truly unlicensed repository becomes a dealbreaker again.
5. Add OpenSSF Scorecard and deps.dev for security practices and real-world dependents.

## How I used AI tools

I used Claude Code (Claude Opus 5.5, with Sonnet and Haiku subagents) for the whole project, from reading the brief to reviewing the final results. The split was simple: Claude did the exploring, drafting and code generation, I made the decisions.

Concretely:

- **The brief.** Claude read the task and drafted a list of clarifying questions. I went through it, dropped the ones that didn't matter for this scope and picked what to actually ask.
- **The approach.** Claude proposed three ways to present the result: explained flags, a single weighted score, and a side-by-side comparison, each with suggested signals and thresholds. I went with flags, because a list of concrete reasons is easier to trust and easier to argue with than one number. I approved the design in `docs/superpowers/specs/`.
- **The rate-limit surprise.** While measuring GitHub API behaviour, Claude found that unauthenticated `304` responses still count against the request limit. That's not obvious from the docs and it changed the caching design: conditional requests alone don't save budget without a token, so the cache ended up built around a TTL and a request budget instead of ETags.
- **Plan and code.** Claude wrote the implementation plan (`docs/superpowers/plans/`) as a sequence of small tasks, then generated the code task by task with subagents. Each task got a review pass against the plan and spec before the next one started, which kept the code close to the design.

My part was everything that needed judgement rather than generation: what to build and what to cut, the final call on signals and thresholds, reviewing the code and how it behaves on real repositories, and the reasoning in this README. Where Claude and I disagreed, what shipped is what I chose.

## Running it locally

Two parts: a Django backend that talks to GitHub and a React frontend that renders the report. In development they run as separate processes.

Backend (Python 3.12):

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py runserver 8000
```

Frontend (Node 22.12+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies everything under `/api` to the backend on port 8000, so the frontend doesn't need to know the backend address. If 8000 is taken, run the backend elsewhere and point Vite at it:

```bash
API_URL=http://127.0.0.1:8765 npm run dev
```

Optional backend environment variables:

- `GITHUB_TOKEN`: without it you get the unauthenticated limit of 60 requests per hour, about 15 fresh checks (cached ones are free). Enough to try it out; a team using it day to day should set a token.
- `GITHUB_CACHE_TTL_SECONDS`: how long GitHub responses are reused. Default 3600.
- `CACHE_DIR`: where cache files go. Defaults to `backend/.cache`; the Docker image uses `/tmp/regret-check-cache`.

Tests:

```bash
cd backend && .venv/bin/python -m pytest
```

```bash
cd frontend && npm test
```

Backend tests cover the signal rules, the cache and rate-limit handling with mocked GitHub responses (hand-built payloads served by the `responses` library), so they don't need network access. Frontend tests cover report rendering and error states.

## Deploying

For deployment both parts go into one Docker image: the frontend is built to static files and served by the same process that exposes the API. One container, one port.

```bash
docker build -t regret-check .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me regret-check
```

On Render: New → Blueprint → this repository. Render reads `render.yaml`, generates `DJANGO_SECRET_KEY` itself and asks for `GITHUB_TOKEN`. A fine-grained token with read-only access to public repositories is enough; the app never writes to GitHub. Railway and Fly work off the same Dockerfile.

Two things about the hosted version. The cache lives in `/tmp`, so it resets on every deploy and the first evaluations afterwards are slower. And Render's free instances sleep when idle, so the first request after a pause takes a while. Neither affects correctness, only speed.

## Project layout

```
backend/evaluator/signals.py                 pure rules: GitHub data → signals → verdict
backend/evaluator/github_client.py           HTTP, cache, rate-limit handling
backend/evaluator/service.py                 one evaluation: budget check, fetches, report
backend/evaluator/views.py                   GET /api/evaluate?repo=owner/name, GET /api/rate-limit
frontend/src/                                React + TypeScript UI
frontend/src/components/ComparisonTable.tsx  side-by-side comparison
frontend/src/errors.ts                       shared error wording
docs/superpowers/                            design spec and implementation plan
```

The backend split is deliberate. `signals.py` has no I/O, just functions from fetched data to signals and a verdict, so it's easy to test and holds most of the product logic. `github_client.py` is the only place that talks HTTP to GitHub, caches responses and reads rate-limit headers. `service.py` ties them together for one evaluation and is the one place that knows which endpoints are called. To change what counts as a warning sign, touch `signals.py`; to change which GitHub endpoints are used, `service.py`; for HTTP, caching or rate limits, `github_client.py`.
