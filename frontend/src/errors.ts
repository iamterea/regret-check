import type { ApiError } from "./api";
import { formatTime } from "./format";

/** The sentence shown for a failed check, in the error banner and in a failed comparison column. */
export function describeError(error: ApiError): string {
  return error.code === "rate_limited" && error.resetAt
    ? `Not enough GitHub requests left for a new check (one needs up to 4). The limit resets at ${formatTime(error.resetAt)}. Repositories checked recently still work.`
    : error.message;
}
