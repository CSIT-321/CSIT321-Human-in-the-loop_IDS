import { afterEach, expect, it, vi } from "vitest";
import { readAlertArrivals } from "./alertArrivalStream";

afterEach(() => vi.unstubAllGlobals());

it("parses only arrival and workspace events; uses bearer header and ignores heartbeat", async () => {
  const encoder = new TextEncoder();
  const arrived = vi.fn(); const changed = vi.fn(); const connected = vi.fn();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(": heartbeat\n\nevent: alert_arr"));
      controller.enqueue(encoder.encode('ived\nid: v3-1-replay:51\ndata: {"eventId":"v3-1-replay:51","workspaceId":"v3-1-replay","operationalAlertRef":"new-ref","timestamp":"now"}\n\nevent: workspace_changed\ndata: {"workspaceId":"operational"}\n\n'));
      controller.close();
    },
  });
  const fetcher = vi.fn(async (_url: string, _init: RequestInit) => new Response(stream, { headers: {
    "Content-Type": "text/event-stream", "X-Operational-Workspace": "v3-1-replay",
  } }));
  vi.stubGlobal("fetch", fetcher);
  await readAlertArrivals("secret", new AbortController().signal, { arrived, workspaceChanged: changed, connected });
  expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/api/v2/alerts/stream"),
    expect.objectContaining({ headers: { Authorization: "Bearer secret", Accept: "text/event-stream" } }));
  expect(String(fetcher.mock.calls[0]?.[0])).not.toContain("secret");
  expect(connected).toHaveBeenCalledWith("v3-1-replay");
  expect(arrived).toHaveBeenCalledOnce();
  expect(arrived).toHaveBeenCalledWith({ eventId: "v3-1-replay:51", workspaceId: "v3-1-replay",
    operationalAlertRef: "new-ref", timestamp: "now" });
  expect(changed).toHaveBeenCalledWith("operational");
});
