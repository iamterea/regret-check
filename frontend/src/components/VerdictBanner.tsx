import type { Evaluation } from "../types";

export function VerdictBanner({ evaluation }: { evaluation: Evaluation }) {
  const { repo, verdict, signals } = evaluation;
  const labels = new Map(signals.map((signal) => [signal.id, signal.label]));
  const unknownLabels = signals.filter((signal) => signal.status === "unknown").map((signal) => signal.label);
  const reasonsLead = verdict.level === "low" ? "Worth a look" : "Driven by";

  return (
    <section className={`verdict verdict--${verdict.level}`} aria-labelledby="verdict-title">
      <p className="verdict__repo">
        <a href={repo.html_url} target="_blank" rel="noreferrer">
          {repo.full_name}
        </a>{" "}
        · ★ {repo.stars.toLocaleString("en")}
      </p>
      <h2 id="verdict-title">{verdict.headline}</h2>
      {repo.description && <p className="verdict__description">{repo.description}</p>}
      {verdict.reasons.length > 0 && (
        <p className="verdict__reasons">
          {reasonsLead}: {verdict.reasons.map((id) => labels.get(id) ?? id).join(", ")}
        </p>
      )}
      {unknownLabels.length >= 2 && (
        <p className="verdict__caveat">
          Limited evidence: {unknownLabels.join(", ")} had too little data, so this verdict rests on fewer signals.
        </p>
      )}
    </section>
  );
}
