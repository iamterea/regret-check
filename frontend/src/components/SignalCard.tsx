import type { Signal, Status } from "../types";

const STATUS_TEXT: Record<Status, string> = {
  ok: "OK",
  watch: "Watch",
  risk: "Risk",
  unknown: "Not enough data",
};

export function SignalCard({ signal }: { signal: Signal }) {
  return (
    <li className={`signal signal--${signal.status}`}>
      <div className="signal__head">
        <h3>{signal.label}</h3>
        <span className="signal__status">{STATUS_TEXT[signal.status]}</span>
      </div>
      <p className="signal__value">{signal.value}</p>
      <p className="signal__detail">{signal.detail}</p>
      <a href={signal.evidence_url} target="_blank" rel="noreferrer">
        Check on GitHub ↗
      </a>
    </li>
  );
}
