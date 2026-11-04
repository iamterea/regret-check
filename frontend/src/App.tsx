import { useEffect, useState } from "react";
import { ApiError, evaluateRepo, fetchRateLimit } from "./api";
import { RateLimitNote } from "./components/RateLimitNote";
import { RepoForm } from "./components/RepoForm";
import { SignalCard } from "./components/SignalCard";
import { VerdictBanner } from "./components/VerdictBanner";
import { formatDateTime, formatTime } from "./format";
import type { Evaluation, RateLimit, Status } from "./types";

type State =
  | { kind: "idle" }
  | { kind: "loading"; fullName: string }
  | { kind: "done"; evaluation: Evaluation }
  | { kind: "error"; error: ApiError };

const SEVERITY: Record<Status, number> = { risk: 0, watch: 1, unknown: 2, ok: 3 };

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [rateLimit, setRateLimit] = useState<RateLimit | null>(null);

  useEffect(() => {
    fetchRateLimit()
      .then(setRateLimit)
      .catch(() => undefined);
  }, []);

  async function check(fullName: string) {
    setState({ kind: "loading", fullName });
    try {
      const evaluation = await evaluateRepo(fullName);
      if (evaluation.meta.rate_limit) setRateLimit(evaluation.meta.rate_limit);
      setState({ kind: "done", evaluation });
    } catch (error) {
      // The budget call is free; refresh it so the note agrees with the error.
      fetchRateLimit().then(setRateLimit).catch(() => undefined);
      setState({
        kind: "error",
        error: error instanceof ApiError ? error : new ApiError("network", "Something went wrong."),
      });
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Regret Check</h1>
        <p className="tagline">Will we regret adopting this open-source dependency in two years?</p>
      </header>
      <RepoForm onSubmit={check} disabled={state.kind === "loading"} />
      <RateLimitNote rateLimit={rateLimit} />
      {state.kind === "loading" && (
        <p className="status-line" role="status">
          Checking {state.fullName}…
        </p>
      )}
      {state.kind === "error" && <ErrorMessage error={state.error} />}
      {state.kind === "done" && <Result evaluation={state.evaluation} />}
    </main>
  );
}

function Result({ evaluation }: { evaluation: Evaluation }) {
  const signals = [...evaluation.signals].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]);
  return (
    <>
      {evaluation.meta.stale && (
        <p className="notice" role="status">
          Showing cached data from {formatDateTime(evaluation.meta.data_as_of)}: fresh data from GitHub wasn't available.
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
