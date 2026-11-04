import { formatTime } from "../format";
import type { RateLimit } from "../types";

export function RateLimitNote({ rateLimit }: { rateLimit: RateLimit | null }) {
  if (!rateLimit) return null;
  return (
    <p className="rate-limit">
      {rateLimit.remaining} of {rateLimit.limit} GitHub requests left · resets at {formatTime(rateLimit.reset_at)} ·
      each repository checked uses up to 4
    </p>
  );
}
