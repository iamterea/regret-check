import { describe, expect, it, vi } from "vitest";
import { ApiError, evaluateRepo, evaluateRepos, fetchRateLimit } from "./api";

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async (_url: string) => ({ ok: status < 400, status, json: async () => body }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api", () => {
  it("requests the encoded repository", async () => {
    const fetchMock = stubFetch(200, { signals: [] });
    await evaluateRepo("acme/widget");
    expect(fetchMock).toHaveBeenCalledWith("/api/evaluate?repo=acme%2Fwidget");
  });

  it("turns a 429 into a rate_limited error with the reset time", async () => {
    stubFetch(429, { error: "rate_limited", message: "Limit used up.", reset_at: "2030-03-17T17:46:40Z" });
    await expect(evaluateRepo("acme/widget")).rejects.toMatchObject({
      code: "rate_limited",
      message: "Limit used up.",
      resetAt: "2030-03-17T17:46:40Z",
    });
  });

  it("explains an empty error response, as when the backend is down", async () => {
    stubFetch(502, null);
    await expect(evaluateRepo("acme/widget")).rejects.toMatchObject({
      code: "network",
      message: "The server did not answer. Is the backend running?",
    });
  });

  it("reports a network failure as an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const failure = evaluateRepo("acme/widget");
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ code: "network" });
  });

  it("reads the rate limit", async () => {
    stubFetch(200, { limit: 60, remaining: 12, reset_at: "2030-03-17T17:46:40Z" });
    await expect(fetchRateLimit()).resolves.toEqual({ limit: 60, remaining: 12, reset_at: "2030-03-17T17:46:40Z" });
  });

  it("evaluates several repositories and keeps each failure with its repository", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("ghost")
          ? {
              ok: false,
              status: 404,
              json: async () => ({ error: "not_found", message: "acme/ghost does not exist or is private." }),
            }
          : { ok: true, status: 200, json: async () => ({ repo: { full_name: "acme/widget" } }) },
      ),
    );
    const outcomes = await evaluateRepos(["acme/widget", "acme/ghost"]);
    expect(outcomes[0]).toMatchObject({ fullName: "acme/widget", evaluation: { repo: { full_name: "acme/widget" } } });
    expect(outcomes[1]).toMatchObject({ fullName: "acme/ghost", error: { code: "not_found" } });
  });
});
