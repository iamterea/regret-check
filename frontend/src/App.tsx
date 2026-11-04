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
