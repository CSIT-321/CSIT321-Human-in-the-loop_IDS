/**
 * Mount the real route table at a path, optionally already signed in, with `fetch` stubbed.
 *
 *     const { router } = renderApp("/", { session: { username: "g.ang", role: "evaluator" } });
 */

import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { routes } from "../App";
import { SESSION_STORAGE_KEY, SessionProvider, type Session } from "../session/SessionContext";

export type FetchHandler = (request: Request) => Response | Promise<Response>;

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Replace `fetch`. Returns the list of requests seen, so a test can assert on headers such as
 * `Authorization`.
 */
export function stubFetch(handler: FetchHandler): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(input, init);
      seen.push(request);
      return handler(request);
    }),
  );
  return seen;
}

export function renderApp(path: string, options: { session?: Session } = {}) {
  if (options.session !== undefined) {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(options.session));
  }
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const utils = render(
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>,
  );
  return { ...utils, router };
}
