import type { Status } from "./types";

export const STATUS_TEXT: Record<Status, string> = {
  ok: "OK",
  watch: "Watch",
  risk: "Risk",
  unknown: "Not enough data",
};
