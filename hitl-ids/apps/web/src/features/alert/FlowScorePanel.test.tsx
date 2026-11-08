import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, stubFetch } from "../../test/renderApp";
import { FLOW_REF as REF, adjustment, detail as detailFor, event } from "../../test/flowPanelFixture";
import { FlowScorePanel } from "./FlowScorePanel";

// C5 (decision Q6, layout approved 2026-11-08): a read-only "Flow & Score" tab for flow alerts. One alert ref serves both
// APIs: a flow alert's operational ref is its legacy alert_ref (measured, analysis/phase-c/c5_fields.py).
const detail = detailFor();

afterEach(() => vi.unstubAllGlobals());

function serve(overrides: Record<string, unknown> = {}) {
  return stubFetch(request => {
    const path = new URL(request.url).pathname;
    if (request.method !== "GET") return jsonResponse({ error: { code: "READ_ONLY", message: "no writes" } }, 500);
    if (path in overrides) return overrides[path] as Response;
    if (path === `/api/alerts/${REF}`) return jsonResponse(detail);
    if (path === `/api/alerts/${REF}/score-adjustment`) return jsonResponse(adjustment);
    if (path === `/api/alerts/${REF}/feedback-history`) return jsonResponse({ alertRef: REF, events: [event], effective: event });
    return jsonResponse({ error: { code: "NOT_FOUND", message: path } }, 404);
  });
}

describe("C5 Flow & Score tab", () => {
  it("shows the 7 approved cards from 3 read-only GETs on the same ref", async () => {
    const requests = serve();
    render(<FlowScorePanel alertRef={REF} />);
    const panel = await screen.findByRole("region", { name: "Flow and score" });
    expect(await within(panel).findByText("Score adjustment")).toBeVisible();            // 1 score chain
    const band = within(panel).getByText("Score and band").closest("section") ?? panel;
    expect(within(band as HTMLElement).getByText("Operational score")).toBeVisible();    // 2 operational score
    expect(within(panel).getByText("18.218.11.51:51178")).toBeVisible();                  // 3 flow
    expect(within(panel).getByText("All flow features (2)")).toBeVisible();               //   features folded
    expect(within(panel).getByText("Queue band")).toBeVisible();                          // 4 queue band
    expect(within(panel).getByText("Fusion scheme")).toBeVisible();                       // 5 fusion scheme
    expect(within(panel).getByText("DDoS · port 80 · tcp")).toBeVisible();                // 6 family
    expect(within(panel).getByText("Same DDoS source as alert f742e96c.")).toBeVisible(); // 7 feedback history
    expect(requests.every(r => r.method === "GET")).toBe(true);
    expect(new Set(requests.map(r => new URL(r.url).pathname))).toEqual(new Set([
      `/api/alerts/${REF}`, `/api/alerts/${REF}/score-adjustment`, `/api/alerts/${REF}/feedback-history`]));
  });

  it("has no verdict control: verdicts go through the one Analyst Verdict form", async () => {
    serve();
    render(<FlowScorePanel alertRef={REF} />);
    const panel = await screen.findByRole("region", { name: "Flow and score" });
    await within(panel).findByText("Score adjustment");
    expect(within(panel).queryByRole("button", { name: /record|submit|verdict/i })).toBeNull();
    expect(within(panel).queryByRole("textbox")).toBeNull();
  });

  it("keeps the other cards when one GET fails, and says which part failed", async () => {
    serve({ [`/api/alerts/${REF}/feedback-history`]: jsonResponse({ error: { code: "DB", message: "history unavailable" } }, 503) });
    render(<FlowScorePanel alertRef={REF} />);
    const panel = await screen.findByRole("region", { name: "Flow and score" });
    expect(await within(panel).findByText("18.218.11.51:51178")).toBeVisible();
    expect(await within(panel).findByText(/history unavailable/)).toBeVisible();
  });
});
