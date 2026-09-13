/**
 * Send a partial request body where the generated type demands every field.
 *
 * Two of the endpoints S13 uses take bodies whose fields the contract marks optional:
 * `POST /api/detection/run` ("defaults to the committed demo sample") and
 * `PUT /api/config/guardrails` ("every field is optional; omitted settings are left alone"). The API
 * reads them that way — `update_guardrail_config` dumps the body with `exclude_none=True` before it
 * touches a row — but `openapi-typescript` emits every property carrying `default: null` as
 * *required*, so `{}` and `{ criticalAlertFloor, rationale }` do not type-check against the
 * generated body.
 *
 * The narrowing is deliberately confined to this one function. Callers still have their keys and
 * value types checked: the parameter is the contract's own `Partial`, so a mistyped field name or a
 * string where a score belongs is an error at the call site. Only the keys a caller passes reach
 * the wire, which is what "omitted settings are left alone" means.
 */
export function partialBody<T>(body: Partial<T>): T {
  return body as T;
}
