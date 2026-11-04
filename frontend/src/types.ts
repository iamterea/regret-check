export type Status = "ok" | "watch" | "risk" | "unknown";
export type Level = "low" | "medium" | "high";

export interface Signal {
  id: string;
  label: string;
  status: Status;
  value: string;
  detail: string;
  evidence_url: string;
}

export interface RateLimit {
  limit: number;
  remaining: number;
  reset_at: string;
}

export interface Evaluation {
  repo: { full_name: string; description: string; html_url: string; stars: number };
  verdict: { level: Level; headline: string; reasons: string[] };
  signals: Signal[];
  meta: { data_as_of: string; stale: boolean; rate_limit: RateLimit };
}
