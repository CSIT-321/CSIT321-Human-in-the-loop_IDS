/**
 * Load something from the API into a three-state value: loading, error, or success.
 *
 * Every screen renders all three — S11's exit criteria require loading, error and empty states, and a
 * view that only handles success shows a blank panel the first time the API is down in a demo.
 */

import { useCallback, useEffect, useState, type DependencyList } from "react";

import { ApiError, CLIENT_ERROR } from "./client";

export type ApiState<T> =
  | { readonly status: "loading" }
  | { readonly status: "error"; readonly error: ApiError }
  | { readonly status: "success"; readonly data: T };

export type ApiResource<T> = ApiState<T> & { readonly reload: () => void };

export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList): ApiResource<T> {
  const [state, setState] = useState<ApiState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: "success", data });
      },
      (cause: unknown) => {
        if (controller.signal.aborted) return;
        const error =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, { code: CLIENT_ERROR.unexpected, message: String(cause) });
        setState({ status: "error", error });
      },
    );
    return () => controller.abort();
    // `load` is deliberately excluded: callers pass an inline closure, and `deps` names what it reads.
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
