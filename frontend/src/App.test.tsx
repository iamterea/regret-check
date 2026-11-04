import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { formatTime } from "./format";
import type { Evaluation } from "./types";

const RATE_LIMIT = { limit: 60, remaining: 56, reset_at: "2030-03-17T17:46:40Z" };

const EVALUATION: Evaluation = {
  repo: {
    full_name: "acme/widget",
    description: "A widget library",
    html_url: "https://github.com/acme/widget",
    stars: 1200,
  },
  verdict: { level: "medium", headline: "Medium regret risk", reasons: ["license"] },
  signals: [
    {
      id: "activity",
      label: "Recent activity",
      status: "ok",
      value: "Last commit 3 days ago",
      detail: "Code is still changing.",
      evidence_url: "https://github.com/acme/widget/commits",
    },
    {
      id: "license",
      label: "License",
      status: "risk",
      value: "None",
      detail: "No license detected.",
      evidence_url: "https://github.com/acme/widget",
    },
  ],
  meta: { data_as_of: "2026-11-04T10:00:00Z", stale: false, rate_limit: RATE_LIMIT },
};

function stubApi(evaluate: { status: number; body: unknown }) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const reply = String(input).startsWith("/api/rate-limit") ? { status: 200, body: RATE_LIMIT } : evaluate;
    return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function stubCompareApi(replies: Record<string, { status: number; body: unknown }>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const reply =
      url.pathname === "/api/rate-limit" ? { status: 200, body: RATE_LIMIT } : replies[url.searchParams.get("repo") ?? ""];
    return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderApp() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText(/56 of 60 GitHub requests left/);
  return user;
}

describe("App", () => {
  it("shows the verdict with the worst signal first", async () => {
    const fetchMock = stubApi({ status: 200, body: EVALUATION });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "https://github.com/acme/widget");
    await user.click(screen.getByRole("button", { name: "Check" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Medium regret risk" })).toBeInTheDocument();
    const cardTitles = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(cardTitles).toEqual(["License", "Recent activity"]);
    expect(screen.getByText("Driven by: License")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/evaluate?repo=acme%2Fwidget");
  });

  it("explains when GitHub's hourly limit is used up", async () => {
    const fetchMock = stubApi({
      status: 429,
      body: {
        error: "rate_limited",
        message: "Not enough GitHub requests left for a new check.",
        reset_at: "2030-03-17T17:46:40Z",
      },
    });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Not enough GitHub requests left for a new check (one needs up to 4).");
    expect(alert).toHaveTextContent(formatTime("2030-03-17T17:46:40Z"));
    const rateLimitCalls = fetchMock.mock.calls.filter(([input]) => String(input).startsWith("/api/rate-limit"));
    expect(rateLimitCalls).toHaveLength(2);
  });

  it("warns when the result comes from an old cached copy", async () => {
    stubApi({ status: 200, body: { ...EVALUATION, meta: { ...EVALUATION.meta, stale: true } } });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    expect(await screen.findByText(/Showing cached data from/)).toHaveTextContent(
      "fresh data from GitHub wasn't available.",
    );
  });

  it("says so when two signals lack data", async () => {
    const unknown = (id: string, label: string) => ({ ...EVALUATION.signals[0], id, label, status: "unknown" as const });
    const evaluation = { ...EVALUATION, signals: [...EVALUATION.signals, unknown("issues", "Issue response"), unknown("releases", "Releases")] };
    stubApi({ status: 200, body: evaluation });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    expect(await screen.findByText(/Limited evidence: Issue response, Releases had too little data/)).toBeInTheDocument();
  });

  it("shows no limited-evidence caveat when signals have data", async () => {
    stubApi({ status: 200, body: EVALUATION });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    await screen.findByRole("heading", { level: 2, name: "Medium regret risk" });
    expect(screen.queryByText(/Limited evidence/)).not.toBeInTheDocument();
  });

  it("rejects text that is not a repository without calling the API", async () => {
    const fetchMock = stubApi({ status: 200, body: EVALUATION });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "not a repo");
    await user.click(screen.getByRole("button", { name: "Check" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/owner\/name/);
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual(["/api/rate-limit"]);
  });

  it("compares several repositories with the lowest risk first", async () => {
    const gadget: Evaluation = {
      ...EVALUATION,
      repo: { ...EVALUATION.repo, full_name: "acme/gadget", html_url: "https://github.com/acme/gadget" },
      verdict: { level: "low", headline: "Low regret risk", reasons: [] },
      signals: EVALUATION.signals.map((signal) => ({ ...signal, status: "ok" as const })),
    };
    const fetchMock = stubCompareApi({
      "acme/widget": { status: 200, body: EVALUATION },
      "acme/gadget": { status: 200, body: gadget },
      "acme/ghost": {
        status: 404,
        body: { error: "not_found", message: "acme/ghost does not exist or is private." },
      },
    });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "acme/widget, acme/ghost acme/gadget");
    await user.click(screen.getByRole("button", { name: "Check" }));

    await screen.findByRole("table");
    const repoHeaders = screen.getAllByRole("columnheader").slice(1);
    expect(repoHeaders.map((header) => header.querySelector(".comparison__repo")?.textContent)).toEqual([
      "acme/gadget",
      "acme/widget",
      "acme/ghost",
    ]);
    expect(screen.getByText("acme/ghost does not exist or is private.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith("/api/rate-limit"))).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Show details for acme/widget" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Medium regret risk" })).toBeInTheDocument();
  });
});
