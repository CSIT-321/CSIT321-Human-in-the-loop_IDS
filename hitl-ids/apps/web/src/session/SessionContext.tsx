/**
 * Who is signed in. Since S18a this is a real account: the API issued the token at sign-in, the
 * role travels inside it, and every request carries it as `Authorization: Bearer …`. There is no
 * way to switch role without signing in as a different account.
 *
 * The session survives a reload (sessionStorage), because S12's end-to-end check is "refresh, and
 * the adjusted score persists" — a refresh that signed the analyst out would break it for the wrong
 * reason. A session stored before S18a fails validation and reads as signed out.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { setApiToken, setApiUnauthorizedHandler } from "../api/client";
import { isRole, type Role } from "./roles";

export interface Session {
  readonly username: string;
  readonly displayName: string;
  readonly role: Role;
  readonly token: string;
}

export const SESSION_STORAGE_KEY = "hitl-ids.session.v1";

function isSession(parsed: unknown): parsed is Session {
  if (typeof parsed !== "object" || parsed === null) return false;
  const candidate = parsed as Record<string, unknown>;
  return (
    typeof candidate.username === "string" &&
    typeof candidate.displayName === "string" &&
    typeof candidate.token === "string" &&
    candidate.token !== "" &&
    "role" in candidate &&
    isRole(candidate.role)
  );
}

function readStored(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (isSession(parsed)) return parsed;
  } catch {
    // Unreadable storage is treated as signed out, never as a default account.
  }
  return null;
}

function store(session: Session | null): void {
  setApiToken(session?.token ?? null);
  try {
    if (session === null) window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    else window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage may be blocked; the session still holds for this page's lifetime.
  }
}

export interface SessionApi {
  readonly session: Session | null;
  readonly signIn: (session: Session) => void;
  readonly signOut: () => void;
}

const SessionContext = createContext<SessionApi | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const stored = readStored();
    setApiToken(stored?.token ?? null);
    return stored;
  });

  const update = useCallback((next: Session | null) => {
    store(next);
    setSession(next);
  }, []);

  const signIn = useCallback((next: Session) => update(next), [update]);
  const signOut = useCallback(() => update(null), [update]);

  // A 401 from the API (expired or revoked sign-in) ends the session here, wherever it happened.
  // `update` is stable, so the handler is registered once.
  useEffect(() => {
    setApiUnauthorizedHandler(() => update(null));
    return () => setApiUnauthorizedHandler(null);
  }, [update]);

  const value = useMemo(
    () => ({ session, signIn, signOut }),
    [session, signIn, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionApi {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
