import { useRef, useState } from "react";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ErrorState } from "../../components/states";

type Work = Schemas["WorkView"];
type Note = Schemas["Note"];
const button = "rounded-sm border border-border bg-raised px-2.5 py-1.5 text-xs hover:border-border-strong disabled:opacity-40";
const MAX = 2000;

/** C6 (decision Q7 option A; layout approved 2026-11-08): append-only Tier 1 notes on the V2 alert.
 *  Everyone with read access reads them. Only the claim owner (work.isOwner, In Review) sees the add form;
 *  the server and the database refuse anyone else. */
export function AlertNotes({ alertRef, work }: { alertRef: string; work: Work | null | undefined }) {
  const resource = useApi(signal => unwrap(api.GET("/api/v2/alerts/{alertRef}/notes", {
    signal, params: { path: { alertRef } },
  })), [alertRef]);
  const [added, setAdded] = useState<Note[]>([]);
  const owner = Boolean(work && work.status === "in_review" && work.isOwner);
  const loaded = resource.status === "success" && Array.isArray(resource.data) ? resource.data : [];
  const notes = [...loaded, ...added.filter(note => !loaded.some(row => row.id === note.id))];

  return <section aria-label="Investigation notes section" className="min-w-0 space-y-2">
    <h3 className="label-mono">Investigation notes</h3>
    {resource.status === "loading" && <p className="text-sm text-muted">Loading notes…</p>}
    {resource.status === "error" && <ErrorState error={resource.error} onRetry={resource.reload} />}
    {resource.status === "success" && (notes.length === 0
      ? <p className="text-sm text-muted">No notes yet.</p>
      : <ul aria-label="Investigation notes" className="divide-y divide-border rounded-sm border border-border">
        {notes.map(note => <li key={note.id} className="min-w-0 space-y-1 p-2 text-sm">
          <p className="text-xs"><strong>{note.actorName}</strong>{" "}
            <time className="text-muted" dateTime={note.createdAt}>{note.createdAt.slice(0, 16).replace("T", " ")}</time></p>
          <p className="whitespace-pre-wrap break-words">{note.body}</p>
        </li>)}
      </ul>)}
    {owner
      ? <AddNote alertRef={alertRef} onAdded={note => setAdded(rows => [...rows, note])} />
      : <p className="text-xs text-muted">Only the analyst who owns this alert can add a note.</p>}
  </section>;
}

function AddNote({ alertRef, onAdded }: { alertRef: string; onAdded: (note: Note) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<{ requestId: string; body: string } | null>(null);
  const body = text.trim();
  const ready = !busy && body !== "" && body.length <= MAX;

  async function submit() {
    if (!ready) return;
    // Same request id for a retry of the same text; the server replays it instead of adding twice.
    if (!pending.current || pending.current.body !== body) pending.current = { requestId: crypto.randomUUID(), body };
    setBusy(true); setError("");
    try {
      const result = await unwrap(api.POST("/api/v2/alerts/{alertRef}/notes", {
        params: { path: { alertRef } }, body: { requestId: pending.current.requestId, body },
      }));
      pending.current = null; setText("");
      onAdded(result.note);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The note could not be confirmed.");
    } finally { setBusy(false); }
  }

  return <div className="space-y-1">
    <label className="block">
      <span className="sr-only">New note</span>
      <textarea className="w-full min-w-0 rounded-sm border border-border bg-raised p-1.5 text-sm" rows={2} value={text}
        placeholder="Add a note (you own this alert)" onChange={event => setText(event.target.value)} />
    </label>
    {error && <p role="alert" className="break-words text-xs text-warn">{error}</p>}
    <div className="flex items-center gap-2">
      <button type="button" className={button} disabled={!ready} onClick={() => void submit()}>Add note</button>
      <span className={"text-xs " + (body.length > MAX ? "text-warn" : "text-muted")}>{body.length > MAX ? `${body.length} / ${MAX}` : ""}</span>
      <span className="text-xs text-muted">Notes cannot be edited or deleted.</span>
    </div>
  </div>;
}
