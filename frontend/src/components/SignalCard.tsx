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
