import type { Evaluation, RateLimit } from "./types";

export type ApiErrorCode = "invalid_repo" | "not_found" | "rate_limited" | "github_error" | "network";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly resetAt?: string;

  constructor(code: ApiErrorCode, message: string, resetAt?: string) {
    super(message);
    this.code = code;
    this.resetAt = resetAt;
  }
}

async function getJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ApiError("network", "Could not reach the server. Is the backend running?");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (!body?.error) {
      // For example the dev proxy's empty 502 while Django is stopped.
      throw new ApiError("network", "The server did not answer. Is the backend running?");
    }
    throw new ApiError(
      body?.error ?? "github_error",
      body?.message ?? `Request failed with status ${response.status}.`,
      body?.reset_at,
    );
  }
  return body as T;
}

export function evaluateRepo(fullName: string): Promise<Evaluation> {
  return getJson<Evaluation>(`/api/evaluate?repo=${encodeURIComponent(fullName)}`);
}

export function fetchRateLimit(): Promise<RateLimit> {
  return getJson<RateLimit>("/api/rate-limit");
}
