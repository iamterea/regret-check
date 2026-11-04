# Regret Check — Simfoni's Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold Simfoni's answers into Regret Check: compare up to 4 repositories side by side, and treat dependence on one person as a dealbreaker.

**Architecture:** Backend changes only the bus-factor rule and the verdict's dealbreaker set. Comparison is frontend-only: the UI calls the existing `GET /api/evaluate` once per repository in parallel and renders a table (signals as rows, repositories as columns, lowest risk first). Docs (spec, README) are updated to the answers and re-checked against the live API.

**Tech Stack:** unchanged — Django 5.2 + pytest/responses; React 19 + TypeScript 7 + Vite 8 + Vitest 5 + Testing Library.

Builds on: `docs/superpowers/specs/2026-11-04-regret-check-design.md` and `docs/superpowers/plans/2026-11-04-regret-check.md` (done).

## Design delta (approved 2026-11-04)

Simfoni's answers to the three open questions:

1. **Who and when:** "More for leads or teams exploring packages to use for functionality and want to use only good, maintained ones." → add side-by-side comparison of 2–4 repositories.
2. **What went wrong before:** "The dependency on single person can lead to less updates or sometimes no updates." → bus factor becomes a dealbreaker: `bus_factor` at `risk` makes the verdict `high`; and when every human commit of the last year comes from one person, that is `risk` however few commits there are (before, under 5 commits was `unknown`).
3. **Token:** "Yes, anything is fine here." → deployments set `GITHUB_TOKEN` (already supported). Unauthenticated mode and its rate-limit handling stay.

## Global Constraints

- Python only as `backend/.venv/bin/python`. Tests never touch the real network.
- Signal ids, labels and statuses unchanged: `status`, `license`, `activity`, `bus_factor`, `issues`, `releases`; `ok`, `watch`, `risk`, `unknown`; levels `low`, `medium`, `high`.
- Dealbreakers become exactly `status`, `license`, `bus_factor`.
- Comparison: at most 4 repositories; columns sorted `low`, `medium`, `high`, then failed ones, stable for ties; a failed repository never hides the others.
- UI copy is English; status always shown as a text label, never colour alone; the page must not scroll horizontally at phone width (the table scrolls inside its own container).
- The README section "How I used AI tools" is the author's — never edit it.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (second `-m`). Commit only on branch `feature/regret-check`. Never touch `git stash`.

---

### Task 1: Bus factor as a dealbreaker

**Files:**
- Modify: `backend/evaluator/signals.py` (`bus_factor_signal`, `DEALBREAKERS`)
- Test: `backend/evaluator/tests/test_signals.py`, `backend/evaluator/tests/test_verdict.py`

**Interfaces:**
- Consumes: existing `Signal`, `RISK`, `WATCH`, `OK`, `UNKNOWN`, `MIN_SAMPLE`, `RECENT_WINDOW_DAYS`, `_commit_author`, `_commit_time`, `Counter`, `timedelta` in `signals.py`; test helpers `commits_by(*logins, days_ago=10)`, `make_commit`, `make_repo`, `NOW`.
- Produces: same function signatures; new behaviour only.

- [ ] **Step 1: Write the failing tests**

In `backend/evaluator/tests/test_signals.py`, delete `test_bus_factor_is_unknown_with_too_few_commits` and add in its place:

```python
def test_bus_factor_is_a_risk_when_one_person_wrote_every_recent_commit():
    signal = bus_factor_signal(make_repo(), commits_by("alice", "alice"), NOW)
    assert signal.status == RISK
    assert signal.value == "alice wrote all 2 commits"


def test_bus_factor_wording_for_a_single_commit():
    assert bus_factor_signal(make_repo(), commits_by("alice"), NOW).value == "alice wrote the only commit"


def test_bus_factor_is_unknown_with_few_commits_from_several_people():
    assert bus_factor_signal(make_repo(), commits_by("alice", "alice", "bob"), NOW).status == UNKNOWN


def test_bus_factor_is_unknown_without_recent_human_commits():
    commits = [make_commit(400, "alice"), make_commit(5, "dependabot[bot]", user_type="Bot")]
    assert bus_factor_signal(make_repo(), commits, NOW).status == UNKNOWN
```

In `backend/evaluator/tests/test_verdict.py`, add this case to the `test_verdict_levels` parametrize list, after `({"license": RISK}, "high"),`:

```python
        ({"bus_factor": RISK}, "high"),
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest evaluator/tests/test_signals.py evaluator/tests/test_verdict.py`
Expected: the two solo tests fail (status `unknown`, not `risk`) and `test_verdict_levels[...bus_factor...]` fails (`medium`, not `high`).

- [ ] **Step 3: Implement**

In `backend/evaluator/signals.py`, replace the whole `bus_factor_signal` function with:

```python
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
        return Signal(
            "bus_factor",
            "Bus factor",
            RISK,
            f"{author} wrote {written}",
            "One person wrote every commit in the last year. If they step away, nobody else knows the code.",
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
```

Replace `DEALBREAKERS = frozenset({"status", "license"})` with:

```python
# Archived, unlicensed, or carried by one person: Simfoni's "single person" regret is a dealbreaker too.
DEALBREAKERS = frozenset({"status", "license", "bus_factor"})
```

- [ ] **Step 4: Run all backend tests**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all pass (88 tests), pristine output.

- [ ] **Step 5: Commit**

```bash
git add backend/evaluator/signals.py backend/evaluator/tests/test_signals.py backend/evaluator/tests/test_verdict.py
git commit -m "feat(backend): one-person projects are a dealbreaker" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Compare up to four repositories

**Files:**
- Create: `frontend/src/status.ts`, `frontend/src/components/ComparisonTable.tsx`
- Modify: `frontend/src/parseRepo.ts` (append), `frontend/src/api.ts` (append), `frontend/src/components/RepoForm.tsx` (replace), `frontend/src/components/SignalCard.tsx` (replace), `frontend/src/components/RateLimitNote.tsx` (one phrase), `frontend/src/App.tsx` (replace), `frontend/src/index.css`
- Test: `frontend/src/parseRepo.test.ts`, `frontend/src/api.test.ts`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `parseRepo(input): string | null`; `ApiError`, `evaluateRepo`, `fetchRateLimit`; types `Evaluation`, `RateLimit`, `Signal`, `Status`, `Level`; components `VerdictBanner`, `RateLimitNote`; `formatTime`, `formatDateTime`. Existing App tests use `stubApi`, `renderApp`, `RATE_LIMIT`, `EVALUATION`.
- Produces:
  - `parseRepo.ts`: `MAX_COMPARE = 4`; `type ParsedRepos = { repos: string[] } | { error: string }`; `parseRepos(input: string): ParsedRepos`.
  - `api.ts`: `type Outcome = { fullName: string; evaluation: Evaluation } | { fullName: string; error: ApiError }`; `evaluateRepos(fullNames: string[]): Promise<Outcome[]>`.
  - `status.ts`: `STATUS_TEXT: Record<Status, string>`.
  - `ComparisonTable({ outcomes, onShowDetails })`.
  - `RepoForm` prop `onSubmit: (fullNames: string[]) => void`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/parseRepo.test.ts` (and change its import line to `import { parseRepo, parseRepos } from "./parseRepo";`):

```ts
describe("parseRepos", () => {
  it("reads one repository", () => {
    expect(parseRepos("django/django")).toEqual({ repos: ["django/django"] });
  });

  it("reads several separated by commas, spaces and new lines", () => {
    expect(parseRepos("moment/moment, https://github.com/date-fns/date-fns\niamkun/dayjs")).toEqual({
      repos: ["moment/moment", "date-fns/date-fns", "iamkun/dayjs"],
    });
  });

  it("drops duplicates, ignoring case", () => {
    expect(parseRepos("a/b A/B https://github.com/a/b")).toEqual({ repos: ["a/b"] });
  });

  it("names the part that is not a repository", () => {
    expect(parseRepos("a/b nope")).toEqual({
      error: '"nope" is not a GitHub repository. Use owner/name or paste its URL.',
    });
  });

  it("asks for input when empty", () => {
    expect(parseRepos("   ")).toEqual({ error: "Enter a GitHub repository as owner/name or paste its URL." });
  });

  it("limits a comparison to four repositories", () => {
    expect(parseRepos("a/a b/b c/c d/d e/e")).toEqual({ error: "Compare at most 4 repositories at a time." });
  });
});
```

Append to the `describe("api", ...)` block in `frontend/src/api.test.ts` (and add `evaluateRepos` to its import from `./api`):

```ts
  it("evaluates several repositories and keeps each failure with its repository", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("ghost")
          ? {
              ok: false,
              status: 404,
              json: async () => ({ error: "not_found", message: "acme/ghost does not exist or is private." }),
            }
          : { ok: true, status: 200, json: async () => ({ repo: { full_name: "acme/widget" } }) },
      ),
    );
    const outcomes = await evaluateRepos(["acme/widget", "acme/ghost"]);
    expect(outcomes[0]).toMatchObject({ fullName: "acme/widget", evaluation: { repo: { full_name: "acme/widget" } } });
    expect(outcomes[1]).toMatchObject({ fullName: "acme/ghost", error: { code: "not_found" } });
  });
```

In `frontend/src/App.test.tsx`, add this helper below `stubApi`:

```tsx
function stubCompareApi(replies: Record<string, { status: number; body: unknown }>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const reply =
      url.pathname === "/api/rate-limit" ? { status: 200, body: RATE_LIMIT } : replies[url.searchParams.get("repo") ?? ""];
    return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
```

and this test inside `describe("App", ...)`:

```tsx
  it("compares several repositories with the lowest risk first", async () => {
    const gadget: Evaluation = {
      ...EVALUATION,
      repo: { ...EVALUATION.repo, full_name: "acme/gadget", html_url: "https://github.com/acme/gadget" },
      verdict: { level: "low", headline: "Low regret risk", reasons: [] },
      signals: EVALUATION.signals.map((signal) => ({ ...signal, status: "ok" as const })),
    };
    const fetchMock = stubCompareApi({
      "acme/widget": { status: 200, body: EVALUATION },
      "acme/gadget": { status: 200, body: gadget },
      "acme/ghost": {
        status: 404,
        body: { error: "not_found", message: "acme/ghost does not exist or is private." },
      },
    });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "acme/widget, acme/ghost acme/gadget");
    await user.click(screen.getByRole("button", { name: "Check" }));

    await screen.findByRole("table");
    const repoHeaders = screen.getAllByRole("columnheader").slice(1);
    expect(repoHeaders.map((header) => header.querySelector(".comparison__repo")?.textContent)).toEqual([
      "acme/gadget",
      "acme/widget",
      "acme/ghost",
    ]);
    expect(screen.getByText("acme/ghost does not exist or is private.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith("/api/rate-limit"))).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Show details for acme/widget" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Medium regret risk" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `parseRepos` and `evaluateRepos` are not exported; the App comparison test finds no table.

- [ ] **Step 3: Parsing and API helpers**

Append to `frontend/src/parseRepo.ts`:

```ts
export const MAX_COMPARE = 4;

export type ParsedRepos = { repos: string[] } | { error: string };

/** One or more repositories separated by spaces, commas or new lines → unique "owner/name" list, or an error to show. */
export function parseRepos(input: string): ParsedRepos {
  const parts = input.split(/[\s,]+/).filter(Boolean);
  if (parts.length === 0) return { error: "Enter a GitHub repository as owner/name or paste its URL." };
  const repos: string[] = [];
  for (const part of parts) {
    const repo = parseRepo(part);
    if (!repo) return { error: `"${part}" is not a GitHub repository. Use owner/name or paste its URL.` };
    if (!repos.some((seen) => seen.toLowerCase() === repo.toLowerCase())) repos.push(repo);
  }
  if (repos.length > MAX_COMPARE) return { error: `Compare at most ${MAX_COMPARE} repositories at a time.` };
  return { repos };
}
```

Append to `frontend/src/api.ts`:

```ts
export type Outcome = { fullName: string; evaluation: Evaluation } | { fullName: string; error: ApiError };

/** Evaluate several repositories in parallel; one failure does not hide the others. */
export function evaluateRepos(fullNames: string[]): Promise<Outcome[]> {
  return Promise.all(
    fullNames.map((fullName) =>
      evaluateRepo(fullName).then(
        (evaluation): Outcome => ({ fullName, evaluation }),
        (error: unknown): Outcome => ({
          fullName,
          error: error instanceof ApiError ? error : new ApiError("network", "Something went wrong."),
        }),
      ),
    ),
  );
}
```

`frontend/src/status.ts`:

```ts
import type { Status } from "./types";

export const STATUS_TEXT: Record<Status, string> = {
  ok: "OK",
  watch: "Watch",
  risk: "Risk",
  unknown: "Not enough data",
};
```

- [ ] **Step 4: Components**

`frontend/src/components/SignalCard.tsx` (replace the whole file):

```tsx
import { STATUS_TEXT } from "../status";
import type { Signal } from "../types";

export function SignalCard({ signal }: { signal: Signal }) {
  return (
    <li className="signal">
      <div className="signal__head">
        <h3>{signal.label}</h3>
        <span className={`status status--${signal.status}`}>{STATUS_TEXT[signal.status]}</span>
      </div>
      <p className="signal__value">{signal.value}</p>
      <p className="signal__detail">{signal.detail}</p>
      <a href={signal.evidence_url} target="_blank" rel="noreferrer">
        Check on GitHub ↗
      </a>
    </li>
  );
}
```

`frontend/src/components/ComparisonTable.tsx`:

```tsx
import type { Outcome } from "../api";
import { STATUS_TEXT } from "../status";
import type { Level, Signal } from "../types";

const LEVEL_ORDER: Record<Level, number> = { low: 0, medium: 1, high: 2 };

interface Props {
  outcomes: Outcome[];
  onShowDetails: (fullName: string) => void;
}

function rank(outcome: Outcome): number {
  return "evaluation" in outcome ? LEVEL_ORDER[outcome.evaluation.verdict.level] : 3;
}

export function ComparisonTable({ outcomes, onShowDetails }: Props) {
  const columns = [...outcomes].sort((a, b) => rank(a) - rank(b));
  const rows = columns.flatMap((column) => ("evaluation" in column ? [column.evaluation.signals] : []))[0] ?? [];

  return (
    <div className="comparison" role="region" aria-labelledby="comparison-title" tabIndex={0}>
      <table>
        <caption id="comparison-title">Side by side, lowest regret risk first</caption>
        <thead>
          <tr>
            <th scope="col">Signal</th>
            {columns.map((column) => (
              <th key={column.fullName} scope="col">
                <span className="comparison__repo">{column.fullName}</span>
                {"evaluation" in column && (
                  <>
                    <span className="comparison__stars">★ {column.evaluation.repo.stars.toLocaleString("en")}</span>
                    <button
                      type="button"
                      className="link-button"
                      aria-label={`Show details for ${column.fullName}`}
                      onClick={() => onShowDetails(column.fullName)}
                    >
                      Details
                    </button>
                  </>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Verdict</th>
            {columns.map((column) => (
              <td key={column.fullName}>
                {"evaluation" in column ? (
                  <span className={`level level--${column.evaluation.verdict.level}`}>
                    {column.evaluation.verdict.headline}
                  </span>
                ) : (
                  <span className="comparison__error">{column.error.message}</span>
                )}
              </td>
            ))}
          </tr>
          {rows.map((row) => (
            <tr key={row.id}>
              <th scope="row">{row.label}</th>
              {columns.map((column) => (
                <td key={column.fullName}>
                  <SignalCell
                    signal={
                      "evaluation" in column
                        ? column.evaluation.signals.find((signal) => signal.id === row.id)
                        : undefined
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SignalCell({ signal }: { signal: Signal | undefined }) {
  if (!signal) return <>—</>;
  return (
    <>
      <span className={`status status--${signal.status}`}>{STATUS_TEXT[signal.status]}</span>
      <span className="comparison__value">{signal.value}</span>
    </>
  );
}
```

`frontend/src/components/RepoForm.tsx` (replace the whole file):

```tsx
import { useState, type FormEvent } from "react";
import { MAX_COMPARE, parseRepos } from "../parseRepo";

const EXAMPLES = [
  { repo: "django/django", note: "very active" },
  { repo: "moment/moment", note: "maintenance mode" },
  { repo: "request/request", note: "deprecated" },
  { repo: "atom/atom", note: "archived" },
];

const COMPARE_EXAMPLE = ["moment/moment", "date-fns/date-fns", "iamkun/dayjs", "moment/luxon"];

interface Props {
  onSubmit: (fullNames: string[]) => void;
  disabled: boolean;
}

export function RepoForm({ onSubmit, disabled }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseRepos(text);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError(null);
    onSubmit(parsed.repos);
  }

  function pick(repos: string[]) {
    setText(repos.join(", "));
    setError(null);
    onSubmit(repos);
  }

  return (
    <form className="repo-form" onSubmit={submit} noValidate>
      <label htmlFor="repo">GitHub repository</label>
      <div className="repo-form__row">
        <input
          id="repo"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="owner/name, or several to compare"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error !== null}
          aria-describedby={error ? "repo-hint repo-error" : "repo-hint"}
        />
        <button type="submit" disabled={disabled}>
          Check
        </button>
      </div>
      <p id="repo-hint" className="form-hint">
        One repository, or up to {MAX_COMPARE} separated by spaces or commas to compare them side by side.
      </p>
      {error && (
        <p id="repo-error" className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="examples">
        Try:
        {EXAMPLES.map(({ repo, note }) => (
          <button key={repo} type="button" className="chip" disabled={disabled} onClick={() => pick([repo])}>
            {repo} <span className="chip__note">{note}</span>
          </button>
        ))}
        <button type="button" className="chip chip--compare" disabled={disabled} onClick={() => pick(COMPARE_EXAMPLE)}>
          Compare date libraries <span className="chip__note">4 repos</span>
        </button>
      </p>
    </form>
  );
}
```

In `frontend/src/components/RateLimitNote.tsx`, replace the phrase `a new check uses up to 4` with `each repository checked uses up to 4`.

- [ ] **Step 5: App**

`frontend/src/App.tsx` (replace the whole file; this keeps every behaviour the current file has — null budget guard, budget refresh after an error, rate-limit and stale copy — and adds comparison):

```tsx
import { useEffect, useState } from "react";
import { ApiError, evaluateRepo, evaluateRepos, fetchRateLimit, type Outcome } from "./api";
import { ComparisonTable } from "./components/ComparisonTable";
import { RateLimitNote } from "./components/RateLimitNote";
import { RepoForm } from "./components/RepoForm";
import { SignalCard } from "./components/SignalCard";
import { VerdictBanner } from "./components/VerdictBanner";
import { formatDateTime, formatTime } from "./format";
import type { Evaluation, RateLimit, Status } from "./types";

type State =
  | { kind: "idle" }
  | { kind: "loading"; fullNames: string[] }
  | { kind: "done"; evaluation: Evaluation }
  | { kind: "error"; error: ApiError }
  | { kind: "compared"; outcomes: Outcome[]; selected: string | null };

const SEVERITY: Record<Status, number> = { risk: 0, watch: 1, unknown: 2, ok: 3 };

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [rateLimit, setRateLimit] = useState<RateLimit | null>(null);

  // The budget endpoint is free, so refresh it whenever the page needs a current number.
  function refreshRateLimit() {
    fetchRateLimit()
      .then(setRateLimit)
      .catch(() => undefined);
  }

  useEffect(() => {
    refreshRateLimit();
  }, []);

  async function check(fullName: string) {
    setState({ kind: "loading", fullNames: [fullName] });
    try {
      const evaluation = await evaluateRepo(fullName);
      if (evaluation.meta.rate_limit) setRateLimit(evaluation.meta.rate_limit);
      setState({ kind: "done", evaluation });
    } catch (error) {
      refreshRateLimit();
      setState({
        kind: "error",
        error: error instanceof ApiError ? error : new ApiError("network", "Something went wrong."),
      });
    }
  }

  async function compare(fullNames: string[]) {
    setState({ kind: "loading", fullNames });
    const outcomes = await evaluateRepos(fullNames);
    refreshRateLimit();
    setState({ kind: "compared", outcomes, selected: null });
  }

  function submit(fullNames: string[]) {
    if (fullNames.length === 1) void check(fullNames[0]);
    else void compare(fullNames);
  }

  return (
    <main className="app">
      <header>
        <h1>Regret Check</h1>
        <p className="tagline">Will we regret adopting this open-source dependency in two years?</p>
      </header>
      <RepoForm onSubmit={submit} disabled={state.kind === "loading"} />
      <RateLimitNote rateLimit={rateLimit} />
      {state.kind === "loading" && (
        <p className="status-line" role="status">
          Checking {state.fullNames.join(", ")}…
        </p>
      )}
      {state.kind === "error" && <ErrorMessage error={state.error} />}
      {state.kind === "done" && <Result evaluation={state.evaluation} />}
      {state.kind === "compared" && (
        <Comparison
          outcomes={state.outcomes}
          selected={state.selected}
          onSelect={(fullName) => setState({ kind: "compared", outcomes: state.outcomes, selected: fullName })}
        />
      )}
    </main>
  );
}

function Comparison({
  outcomes,
  selected,
  onSelect,
}: {
  outcomes: Outcome[];
  selected: string | null;
  onSelect: (fullName: string) => void;
}) {
  const chosen = outcomes.find((outcome) => outcome.fullName === selected);
  return (
    <>
      <ComparisonTable outcomes={outcomes} onShowDetails={onSelect} />
      {chosen && "evaluation" in chosen && <Result evaluation={chosen.evaluation} />}
    </>
  );
}

function Result({ evaluation }: { evaluation: Evaluation }) {
  const signals = [...evaluation.signals].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]);
  return (
    <>
      {evaluation.meta.stale && (
        <p className="notice" role="status">
          Showing cached data from {formatDateTime(evaluation.meta.data_as_of)}: fresh data from GitHub wasn't
          available.
        </p>
      )}
      <VerdictBanner evaluation={evaluation} />
      <ul className="signals">
        {signals.map((signal) => (
          <SignalCard key={signal.id} signal={signal} />
        ))}
      </ul>
    </>
  );
}

function ErrorMessage({ error }: { error: ApiError }) {
  const text =
    error.code === "rate_limited" && error.resetAt
      ? `Not enough GitHub requests left for a new check (one needs up to 4). The limit resets at ${formatTime(error.resetAt)}. Repositories checked recently still work.`
      : error.message;
  return (
    <p className="error" role="alert">
      {text}
    </p>
  );
}
```

Before replacing, diff the current `App.tsx` against this text: if the current file has any behaviour this version lacks, stop and report it (NEEDS_CONTEXT) instead of dropping it.

- [ ] **Step 6: Styles**

In `frontend/src/index.css`, replace the five rules `.signal__status { … }`, `.signal--ok .signal__status { … }`, `.signal--watch .signal__status { … }`, `.signal--risk .signal__status { … }`, `.signal--unknown .signal__status { … }` with:

```css
.status {
  display: inline-block;
  padding: 2px 10px;
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
  border-radius: 999px;
}

.status--ok {
  color: var(--ok);
  background: var(--ok-bg);
}

.status--watch {
  color: var(--watch);
  background: var(--watch-bg);
}

.status--risk {
  color: var(--risk);
  background: var(--risk-bg);
}

.status--unknown {
  color: var(--unknown);
  background: var(--unknown-bg);
}
```

and append at the end of the file (before the `@media (max-width: 480px)` block if it is last, otherwise at the end):

```css
.form-hint {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 0.85rem;
}

.chip--compare {
  border-style: dashed;
}

.link-button {
  padding: 0;
  font: inherit;
  color: var(--accent);
  background: none;
  border: 0;
  text-decoration: underline;
  cursor: pointer;
}

.comparison {
  margin: 24px 0 16px;
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.comparison table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.comparison caption {
  padding: 12px 16px 0;
  font-weight: 600;
  text-align: left;
}

.comparison th,
.comparison td {
  padding: 10px 16px;
  text-align: left;
  vertical-align: top;
  border-top: 1px solid var(--border);
}

.comparison thead th {
  border-top: 0;
}

.comparison tbody th {
  color: var(--muted);
  font-weight: 600;
  white-space: nowrap;
}

.comparison__repo,
.comparison__stars,
.comparison__value {
  display: block;
}

.comparison__repo {
  font-weight: 600;
}

.comparison__stars {
  color: var(--muted);
  font-weight: 400;
}

.comparison__value {
  margin-top: 4px;
}

.comparison__error {
  color: var(--risk);
}

.level {
  font-weight: 700;
}

.level--low {
  color: var(--ok);
}

.level--medium {
  color: var(--watch);
}

.level--high {
  color: var(--risk);
}
```

- [ ] **Step 7: Run tests, type-check and build**

Run: `cd frontend && npm test && npm run build`
Expected: all pass (31 tests), no warnings, `tsc` clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): compare up to four repositories side by side" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Docs and live check

**Files:**
- Modify: `docs/superpowers/specs/2026-11-04-regret-check-design.md`, `README.md`

**Interfaces:**
- Consumes: Tasks 1–2; the running app.
- Produces: spec and README that match the code and Simfoni's answers, with observed results.

- [ ] **Step 1: Live check through the API**

Backend on a free port (8000 may be taken locally): `cd backend && .venv/bin/python manage.py runserver 8765 --noreload` in the background. Read `curl -s http://127.0.0.1:8765/api/rate-limit`; stop if fewer than 16 requests remain. Then:

```bash
for repo in moment/moment date-fns/date-fns iamkun/dayjs moment/luxon; do curl -s "http://127.0.0.1:8765/api/evaluate?repo=$repo" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["repo"]["full_name"], "|", d["verdict"]["headline"], "|", ", ".join(f"{s[\"label\"]}: {s[\"status\"]} ({s[\"value\"]})" for s in d["signals"]))'; done
```

Record the four lines. Stop the server (`pkill -f "runserver 8765"`).

- [ ] **Step 2: Update the spec**

In `docs/superpowers/specs/2026-11-04-regret-check-design.md`:
- Status line: `Status: implemented on branch feature/regret-check; updated 2026-11-04 with Simfoni's answers.`
- Replace the "Working assumptions" section with a section `## Answers from Simfoni (2026-11-04)` that quotes the three answers (from this plan's Design delta) and states, for each, what changed: comparison of up to 4 repositories; bus factor as a dealbreaker with the solo rule; deployments set `GITHUB_TOKEN`.
- In "Approach", replace the rejected-comparison sentence so it says comparison was first cut for scope and added after Simfoni said the users are leads and teams choosing between packages.
- In the signals table, the `bus_factor` rule becomes: among non-bot commits from the last 365 days in the newest 100 commits: one author only (at least 1 commit) → `risk`; otherwise fewer than 5 → `unknown`; top author share ≥ 80% `risk`, ≥ 50% `watch`, else `ok`.
- In "Verdict", the dealbreakers are `status`, `license` and `bus_factor`.
- In "Frontend", add: the input also takes up to 4 repositories separated by spaces, commas or new lines; 2–4 repositories render a comparison table (signals as rows, repositories as columns, lowest risk first, failed ones last with their error); "Details" under a column shows that repository's full report; a "Compare date libraries" example chip (moment, date-fns, dayjs, luxon).
- In "Deliberately cut", remove side-by-side comparison.
- Replace the "Open questions" section body with: `Answered — see "Answers from Simfoni".`

- [ ] **Step 3: Update the README**

In `README.md` (never touch "How I used AI tools"):
- Signals table, Bus factor row: Risk when → `one person wrote ≥ 80% of last year's human commits, or all of them however few`.
- "How the verdict is decided", first bullet → `**High** if the repo is archived, unlicensed or carried by one person, or if two signals are at risk.`
- Under the verdict bullets add one paragraph: `**Why one person is a dealbreaker.** Simfoni said the dependency they regret is the one that hangs on a single person: updates slow down or stop. So a project whose recent commits all come from one person is high risk, even if it is active today.`
- Replace the whole "Working assumptions" section with:

```markdown
## What Simfoni told me

I asked three questions before building. The answers changed the product:

| Question | Answer | What changed |
|---|---|---|
| Who uses this, and when? | Leads or teams exploring packages for some functionality, who want only good, maintained ones. | You can compare up to 4 repositories side by side, lowest risk first. |
| What went wrong with a dependency before? | Dependence on a single person: fewer updates, sometimes none. | Bus factor is a dealbreaker. A project carried by one person is high risk. |
| Is a server-side GitHub token OK? | Yes. | Deployments set `GITHUB_TOKEN` (5,000 requests/hour). Without it the app still works within 60/hour. |

Known limitation: for very busy repositories the newest 100 issues and pull requests can all be under two weeks old, so Issue response shows "Not enough data".
```

- Add a section directly after "### Example results (checked 2026-11-04)" and its table:

```markdown
### Example comparison: date libraries (checked 2026-11-04)

| Repository | Verdict | Flags |
|---|---|---|
```

with one row per repository from Step 1, in the order the UI shows them (lowest risk first; ties keep input order: moment, date-fns, dayjs, luxon); Flags lists non-`ok` signals as `label (status)` or `none`.
- If any of the four single-repository rows in "Example results" would change under the new bus-factor rule, say so in your report (do not re-run them).
- "What I deliberately cut": delete the "Comparing two or three candidates side by side" bullet.
- "What I'd do next": delete the side-by-side comparison item and renumber.
- In "Dealing with the 60 requests/hour limit", "Optional token" bullet → `**Token.** Simfoni confirmed a server-side token is fine: set GITHUB_TOKEN when deploying to get 5,000 requests/hour. It never reaches the browser. Everything above keeps the app usable without one.`
- In "Project layout", add the line `frontend/src/components/ComparisonTable.tsx  side-by-side comparison` in the same aligned style.

Run: `grep -n "…" README.md` → no output.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-11-04-regret-check-design.md
git commit -m "docs: fold in Simfoni's answers and the date-library comparison" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
