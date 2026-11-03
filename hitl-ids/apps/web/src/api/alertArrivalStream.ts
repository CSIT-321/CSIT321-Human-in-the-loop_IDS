/** Fetch-based SSE so the bearer token stays in an Authorization header. */
export type ArrivalEvent = { eventId: string; workspaceId: string; operationalAlertRef: string; timestamp: string };

export async function readAlertArrivals(token: string, signal: AbortSignal, handlers: {
  connected: (workspaceId: string | null) => void;
  arrived: (event: ArrivalEvent) => void;
  workspaceChanged: (workspaceId: string) => void;
}): Promise<void> {
  const base = import.meta.env.VITE_API_BASE_URL || window.location.origin;
  const response = await fetch(`${base}/api/v2/alerts/stream`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    cache: "no-store", signal,
  });
  if (response.status === 401) throw new Error("UNAUTHORIZED");
  if (!response.ok || !response.body || !response.headers.get("content-type")?.includes("text/event-stream"))
    throw new Error(`Stream unavailable (${response.status})`);
  handlers.connected(response.headers.get("X-Operational-Workspace"));
  const reader = response.body.getReader();
  const cancel = () => { void reader.cancel(); };
  signal.addEventListener("abort", cancel, { once: true });
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = block.match(/^event: (.+)$/m)?.[1];
        const raw = block.match(/^data: (.+)$/m)?.[1];
        if (!event || !raw) continue;
        let payload: unknown;
        try { payload = JSON.parse(raw); } catch { continue; }
        if (!payload || typeof payload !== "object") continue;
        if (event === "alert_arrived") {
          const item = payload as Partial<ArrivalEvent>;
          if (typeof item.eventId === "string" && typeof item.workspaceId === "string" &&
              typeof item.operationalAlertRef === "string" && typeof item.timestamp === "string")
            handlers.arrived(item as ArrivalEvent);
        } else if (event === "workspace_changed") {
          const item = payload as { workspaceId?: unknown };
          if (typeof item.workspaceId === "string") handlers.workspaceChanged(item.workspaceId);
        }
      }
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => undefined);
  }
}
