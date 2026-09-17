/**
 * The workstation's top bar: identity and data provenance on the left; the UTC clock, the signed-in
 * account and sign-out on the right.
 *
 * "Recorded flows" replaces the reference design's LIVE feed badge: this console scores recorded lab
 * traffic (CSE-CIC-IDS2018), and a live indicator would be a claim the system cannot make.
 *
 * There is no role switch. Since S18a the view belongs to the account signed in; to see another
 * view, sign out and sign in as that account.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { useSession } from "../../session/SessionContext";

/** "g.ang" -> "GA": the initials an avatar shows, ignoring anything that is not a letter or digit. */
function initials(username: string): string {
  const letters = username.replace(/[^a-zA-Z0-9]/g, "").slice(0, 2).toUpperCase();
  return letters === "" ? "?" : letters;
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <time dateTime={now.toISOString()} className="hidden font-mono text-xs tabular-nums text-muted sm:inline">
      {now.toISOString().slice(11, 19)} UTC
    </time>
  );
}

export function TopBar() {
  const { session, signOut } = useSession();
  const navigate = useNavigate();

  if (session === null) return null;

  return (
    <header
      data-print-hidden="true"
      className="flex h-12 w-full shrink-0 items-center justify-between gap-4 border-b border-border bg-bg px-4"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span aria-hidden className="grid h-6 w-6 place-items-center rounded-sm border border-primary/60 bg-accent-dim">
          <span className="h-2 w-2 rounded-full bg-primary" />
        </span>
        <span className="font-mono text-[13px] font-semibold tracking-wider text-text">IDS CONSOLE</span>
        <span aria-hidden className="h-4 w-px bg-border" />
        <span className="hidden truncate text-xs text-muted md:inline">Human-in-the-loop triage</span>
        <span
          className="hidden items-center gap-1.5 rounded-sm border border-border bg-surface px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider text-muted lg:inline-flex"
          title="Scores recorded CSE-CIC-IDS2018 flows; nothing here is a live feed"
        >
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-dim" />
          Recorded flows
        </span>
      </div>
      <div className="flex items-center gap-3">
        <Clock />
        <span
          aria-hidden
          title={session.username}
          className="flex h-7 w-7 items-center justify-center rounded-sm border border-border bg-raised font-mono text-[11px] font-semibold text-accent"
        >
          {initials(session.username)}
        </span>
        <span className="sr-only">{session.username}</span>
        <span className="hidden truncate text-xs text-muted lg:inline">{session.displayName}</span>
        <button
          type="button"
          onClick={() => {
            signOut();
            void navigate("/login", { replace: true });
          }}
          className="rounded-sm border border-border bg-raised px-2.5 py-1 text-xs text-text hover:border-border-strong hover:bg-surface"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
