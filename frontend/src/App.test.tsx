import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
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
    stubApi({
      status: 429,
      body: {
        error: "rate_limited",
        message: "GitHub's hourly request limit is used up.",
        reset_at: "2030-03-17T17:46:40Z",
      },
    });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/60 requests an hour is used up/);
  });

  it("warns when the result comes from an old cached copy", async () => {
    stubApi({ status: 200, body: { ...EVALUATION, meta: { ...EVALUATION.meta, stale: true } } });
    const user = await renderApp();

    await user.click(screen.getByRole("button", { name: /django\/django/ }));

    expect(await screen.findByText(/Showing cached data from/)).toBeInTheDocument();
  });

  it("rejects text that is not a repository without calling the API", async () => {
    const fetchMock = stubApi({ status: 200, body: EVALUATION });
    const user = await renderApp();

    await user.type(screen.getByLabelText("GitHub repository"), "not a repo");
    await user.click(screen.getByRole("button", { name: "Check" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/owner\/name/);
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual(["/api/rate-limit"]);
  });
});
