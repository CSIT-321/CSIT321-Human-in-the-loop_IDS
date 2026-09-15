import { describe, expect, it } from "vitest";

import { jsonResponse, stubFetch } from "../test/renderApp";
import { api, ApiError, CLIENT_ERROR, setApiToken, unwrap } from "./client";

describe("api client", () => {
  it("sends the signed-in account's bearer token on every request", async () => {
    const seen = stubFetch(() => jsonResponse({ items: [], page: { limit: 50, offset: 0, total: 0 } }));
    setApiToken("evaluator-token");
    await unwrap(api.GET("/api/evaluation/scenarios"));
    expect(seen).toHaveLength(1);
    expect(seen[0]?.headers.get("Authorization")).toBe("Bearer evaluator-token");
  });

  it("sends no Authorization header when signed out", async () => {
    const seen = stubFetch(() => jsonResponse({ items: [], page: { limit: 50, offset: 0, total: 0 } }));
    setApiToken(null);
    await unwrap(api.GET("/api/evaluation/scenarios"));
    expect(seen[0]?.headers.has("Authorization")).toBe(false);
  });

  it("turns the contract's error envelope into an ApiError carrying its code", async () => {
    stubFetch(() =>
      jsonResponse(
        { error: { code: "FORBIDDEN_ROLE", message: "This action requires the system_admin role" } },
        403,
      ),
    );
    const failure = unwrap(api.GET("/api/config/guardrails"));
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 403, code: "FORBIDDEN_ROLE" });
  });

  it("reports an unreachable API as a network error, not a crash", async () => {
    stubFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    await expect(unwrap(api.GET("/api/dashboard/summary"))).rejects.toMatchObject({
      status: 0,
      code: CLIENT_ERROR.network,
    });
  });

  it("refuses a failure that lacks the error envelope rather than guessing at it", async () => {
    stubFetch(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(unwrap(api.GET("/api/dashboard/summary"))).rejects.toMatchObject({
      status: 502,
      code: CLIENT_ERROR.unexpected,
    });
  });
});
