/**
 * Keep the last successful value of a resource across a refetch (plan S12).
 *
 * `useApi` returns to `loading` on every dependency change, which is right for a first load and wrong
 * for a refresh: the alert detail re-reads three resources after a verdict is recorded, and the verdict
 * form holds its outcome in its own state. Replacing the page with a spinner would unmount that form
 * and lose the guardrail's sentence the moment the analyst earned it.
 */

import { useEffect, useState } from "react";

import type { ApiResource } from "../../api/useApi";

export function useLastGood<T>(resource: ApiResource<T>): T | null {
  const data = resource.status === "success" ? resource.data : null;
  const [last, setLast] = useState<T | null>(null);

  useEffect(() => {
    if (data !== null) setLast(data);
  }, [data]);

  return data ?? last;
}
