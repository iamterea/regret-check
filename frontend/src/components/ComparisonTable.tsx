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
