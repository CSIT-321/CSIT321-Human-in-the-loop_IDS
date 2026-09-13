/**
 * S13 — the five settings that bound what analyst feedback may do, the settings that are only
 * reported, and the log of every time a guardrail acted.
 *
 * The write path is the point of the screen: a change is refused before it is sent unless it is a
 * change, every value is in range, the floor sits below the threshold and the administrator has said
 * why. The API enforces the same rules and records the reason in the audit trail; the client-side
 * pass exists so a mis-typed floor is answered in the form rather than by a round trip.
 *
 * The five editable settings are shown with the API's own `description` as their help text, because
 * a description maintained in one place cannot drift from the policy it describes.
 */

import { useState, type FormEvent } from "react";

import { ApiError, CLIENT_ERROR, api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState, ErrorState, LoadingState } from "../../components/states";
import { Card, PageHeader, Pill } from "../../components/ui";
import { formatDateTime, formatNumber, humanise } from "../../design/format";
import {
  EDITABLE_SETTINGS,
  EMPTY_SETTINGS,
  changedFields,
  formValues,
  readOnlySettings,
  settingFor,
  updatePayload,
  validateForm,
  withField,
  type FormValues,
  type GuardrailField,
  type GuardrailSetting,
} from "../../features/admin/guardrails";
import { interventionExplanations, shortAlertRef, type AuditEntry } from "../../features/admin/audit";

const INPUT_CLASS =
  "w-40 rounded-sm border border-border bg-raised px-3 py-1.5 font-mono text-sm text-text";
const LABEL_CLASS = "block text-sm font-medium text-text";
const TH_CLASS = "px-3 py-2 font-medium";
const TD_CLASS = "px-3 py-1.5 text-text";

function asApiError(cause: unknown): ApiError {
  return cause instanceof ApiError
    ? cause
    : new ApiError(0, { code: CLIENT_ERROR.unexpected, message: String(cause) });
}

/** The five limits, their current values, and the reason a change has to carry. */
function FeedbackLimitsCard({
  settings,
  onSaved,
}: {
  settings: readonly GuardrailSetting[];
  onSaved: (settings: readonly GuardrailSetting[]) => void;
}) {
  const [baseline, setBaseline] = useState<FormValues>(() => formValues(settings));
  const [values, setValues] = useState<FormValues>(() => formValues(settings));
  const [rationale, setRationale] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  function edit(field: GuardrailField, value: string) {
    setValues((current) => withField(current, field, value));
    setProblems([]);
    setSaved(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateForm(values, baseline, rationale);
    setProblems(found);
    setSaved(false);
    if (found.length > 0) return;

    setSaving(true);
    setError(null);
    try {
      const response = await unwrap(
        api.PUT("/api/config/guardrails", {
          body: updatePayload(changedFields(values, baseline), rationale.trim()),
        }),
      );
      const next = response.settings ?? EMPTY_SETTINGS;
      const nextValues = formValues(next);
      setBaseline(nextValues);
      setValues(nextValues);
      setRationale("");
      setSaved(true);
      onSaved(next);
    } catch (cause) {
      setError(asApiError(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card
      title="Feedback limits"
      subtitle="Only an administrator can change these, and every change records why."
    >
      <form onSubmit={submit} noValidate className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {EDITABLE_SETTINGS.map((setting) => {
            const help = settingFor(settings, setting.key)?.description ?? null;
            const inputId = `guardrail-${setting.field}`;
            const helpId = `${inputId}-help`;
            return (
              <div key={setting.field} className="space-y-1">
                <label htmlFor={inputId} className={LABEL_CLASS}>
                  {setting.label}
                </label>
                <input
                  id={inputId}
                  type="number"
                  step="0.01"
                  value={values[setting.field]}
                  aria-describedby={help === null ? undefined : helpId}
                  onChange={(event) => edit(setting.field, event.target.value)}
                  className={INPUT_CLASS}
                />
                {help !== null && (
                  <p id={helpId} className="text-xs text-dim">
                    {help}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        <div className="space-y-1">
          <label htmlFor="guardrail-rationale" className={LABEL_CLASS}>
            Reason for this change
          </label>
          <textarea
            id="guardrail-rationale"
            rows={3}
            value={rationale}
            onChange={(event) => {
              setRationale(event.target.value);
              setProblems([]);
              setSaved(false);
            }}
            className="w-full rounded-sm border border-border bg-raised px-3 py-2 text-sm text-text"
          />
          <p className="text-xs text-dim">Recorded in the audit trail with the change itself.</p>
        </div>

        {problems.length > 0 && (
          <div
            role="alert"
            className="rounded-sm border border-danger/40 bg-danger-dim/40 p-3 text-sm text-danger"
          >
            <ul className="list-disc space-y-1 pl-5">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </div>
        )}

        {error !== null && <ErrorState error={error} />}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-sm border border-accent bg-accent-dim px-3 py-1.5 text-sm font-medium text-accent disabled:opacity-50"
          >
            Save changes
          </button>
          {saved && (
            <p role="status" className="text-sm text-ok">
              Saved. The change and its reason are in the audit trail.
            </p>
          )}
        </div>
      </form>
    </Card>
  );
}

/** Everything that is not one of the five: reported so the screen is not a partial picture. */
function OtherSettingsCard({ settings }: { settings: readonly GuardrailSetting[] }) {
  const others = readOnlySettings(settings);

  return (
    <Card
      title="Other settings"
      subtitle="Read-only here: the pipeline enforces these, and feedback does not move them."
    >
      {others.length === 0 ? (
        <EmptyState title="No other settings are configured" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th scope="col" className={TH_CLASS}>
                  Setting
                </th>
                <th scope="col" className={TH_CLASS}>
                  Value
                </th>
                <th scope="col" className={TH_CLASS}>
                  Description
                </th>
                <th scope="col" className={TH_CLASS}>
                  Updated
                </th>
              </tr>
            </thead>
            <tbody>
              {others.map((entry) => (
                <tr key={entry.configKey} className="border-t border-border">
                  <th scope="row" className={`${TD_CLASS} text-left font-normal`}>
                    {humanise(entry.configKey)}
                  </th>
                  <td className={`${TD_CLASS} font-mono tabular-nums`}>
                    {formatNumber(entry.configValue)}
                  </td>
                  <td className={`${TD_CLASS} text-muted`}>{entry.description ?? "—"}</td>
                  <td className={`${TD_CLASS} text-muted`}>
                    {entry.updatedAt === null ? "—" : formatDateTime(entry.updatedAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

const GUARDRAIL_EVENTS = ["GUARDRAIL_INTERVENTION", "GUARDRAIL_REJECTION"] as const;

const EVENT_PILL: Record<(typeof GUARDRAIL_EVENTS)[number], { readonly tone: "warn" | "danger"; readonly label: string }> = {
  GUARDRAIL_INTERVENTION: { tone: "warn", label: "Capped" },
  GUARDRAIL_REJECTION: { tone: "danger", label: "Refused" },
};

function eventPill(eventType: AuditEntry["eventType"]) {
  if (eventType !== "GUARDRAIL_INTERVENTION" && eventType !== "GUARDRAIL_REJECTION") return null;
  const meta = EVENT_PILL[eventType];
  return <Pill tone={meta.tone}>{meta.label}</Pill>;
}

function GuardrailLogCard() {
  const log = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/audit-log", {
          params: { query: { eventType: [...GUARDRAIL_EVENTS], limit: 50 } },
          signal,
        }),
      ),
    [],
  );

  return (
    <Card
      title="Guardrail log"
      subtitle="Every verdict a guardrail capped or refused, newest first."
    >
      <ApiView
        resource={log}
        isEmpty={(data) => data.items.length === 0}
        empty={
          <EmptyState
            title="No guardrail has acted yet."
            hint="Guardrail actions appear here when an analyst verdict is capped or refused."
          />
        }
      >
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-muted">
                  <th scope="col" className={TH_CLASS}>
                    When
                  </th>
                  <th scope="col" className={TH_CLASS}>
                    Event
                  </th>
                  <th scope="col" className={TH_CLASS}>
                    Alert
                  </th>
                  <th scope="col" className={TH_CLASS}>
                    Explanation
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((entry) => {
                  const explanations = interventionExplanations(entry.details);
                  return (
                    <tr key={entry.eventId} className="border-t border-border align-top">
                      <td className={`${TD_CLASS} whitespace-nowrap text-muted`}>
                        {formatDateTime(entry.createdAt)}
                      </td>
                      <td className={TD_CLASS}>{eventPill(entry.eventType)}</td>
                      <td className={`${TD_CLASS} font-mono`}>{shortAlertRef(entry.alertRef)}</td>
                      <td className={TD_CLASS}>
                        {explanations.length === 0 ? (
                          "—"
                        ) : (
                          <ul className="space-y-1">
                            {explanations.map((explanation) => (
                              <li key={explanation}>{explanation}</li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ApiView>
    </Card>
  );
}

export function GuardrailsPage() {
  const config = useApi((signal) => unwrap(api.GET("/api/config/guardrails", { signal })), []);
  const [saved, setSaved] = useState<readonly GuardrailSetting[] | null>(null);

  const fetched = config.status === "success" ? config.data.settings ?? EMPTY_SETTINGS : null;
  const settings = saved ?? fetched;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Guardrails"
        subtitle="The limits on what analyst feedback may do. Only an administrator can change them, and every change records why."
      />
      {settings === null ? (
        config.status === "error" ? (
          <ErrorState error={config.error} onRetry={config.reload} />
        ) : (
          <LoadingState label="Reading the guardrail settings…" />
        )
      ) : (
        <>
          <FeedbackLimitsCard settings={settings} onSaved={setSaved} />
          <OtherSettingsCard settings={settings} />
        </>
      )}
      <GuardrailLogCard />
    </div>
  );
}
