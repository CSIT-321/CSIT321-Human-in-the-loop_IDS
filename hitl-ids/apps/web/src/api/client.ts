/**
 * The typed API client (plan step S11).
 *
 * `schema.d.ts` is GENERATED from `apps/api/openapi.json` — the S10a contract — by `npm run gen:api`,
 * and `npm run check:api` fails if it is stale. Never edit it by hand: a hand-edited client is a
 * second copy of the contract, free to drift.
 *
 * Every non-2xx response carries the contract's one error envelope, so there is exactly one error
 * path: `unwrap` either returns the typed body or throws an `ApiError`.
 */

import createClient, { type Middleware } from "openapi-fetch";

import { ROLE_HEADER, type Role } from "../session/roles";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/**
 * The error body as it actually arrives. The generated `ErrorBody` marks `detail` required because the
 * contract gives it a default, but the API renders errors with `exclude_none` (`apps/api/deps.py`), so
 * a body with no detail omits the key. Every other response serialises its defaults, so this is the
 * one place the generated type has to be loosened.
 */
export type ErrorBody = Omit<Schemas["ErrorBody"], "detail"> & {
  detail?: Schemas["ErrorBody"]["detail"];
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Schemas["ErrorBody"]["detail"];

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.detail = body.detail ?? null;
  }
}

/** Codes the client itself raises; every other code comes from the API. */
export const CLIENT_ERROR = { network: "NETWORK_UNREACHABLE", unexpected: "UNEXPECTED_RESPONSE" } as const;

// The role travels on every request. It is held here, set synchronously by the session, rather than
// read from React state: a child component's first fetch runs before its parent's effects do.
let currentRole: Role | null = null;

export function setApiRole(role: Role | null): void {
  currentRole = role;
}

const roleHeader: Middleware = {
  onRequest({ request }) {
    if (currentRole !== null) request.headers.set(ROLE_HEADER, currentRole);
    return request;
  },
};

function defaultBaseUrl(): string {
  const configured: unknown = import.meta.env.VITE_API_BASE_URL;
  if (typeof configured === "string" && configured !== "") return configured;
  // Same origin: the Vite dev server proxies /api to uvicorn.
  return typeof window === "undefined" ? "http://localhost" : window.location.origin;
}

// `fetch` is looked up per call, not captured at import, so a test's stubbed global is the one used.
export const api = createClient<paths>({
  baseUrl: defaultBaseUrl(),
  fetch: (request) => globalThis.fetch(request),
});
api.use(roleHeader);

function isErrorResponse(value: unknown): value is { error: ErrorBody } {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const body: unknown = value.error;
  return (
    typeof body === "object" &&
    body !== null &&
    "code" in body &&
    typeof body.code === "string" &&
    "message" in body &&
    typeof body.message === "string"
  );
}

interface ClientResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/**
 * Await an `api.GET/POST/PUT` call and return its typed body, or throw `ApiError`.
 *
 *     const summary = await unwrap(api.GET("/api/dashboard/summary", { signal }));
 */
export async function unwrap<T>(call: Promise<ClientResult<T>>): Promise<T> {
  let result: ClientResult<T>;
  try {
    result = await call;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, {
      code: CLIENT_ERROR.network,
      message: "Cannot reach the API. Is it running? python -m uvicorn apps.api.main:app",
    });
  }
  const { data, error, response } = result;
  if (response.ok && data !== undefined) return data;
  if (isErrorResponse(error)) throw new ApiError(response.status, error.error);
  throw new ApiError(response.status, {
    code: CLIENT_ERROR.unexpected,
    message: `The API answered ${response.status} ${response.statusText} without the contract's error envelope`,
  });
}
