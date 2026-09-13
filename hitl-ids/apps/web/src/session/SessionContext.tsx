/**
 * Who is signed in, and as which role. **A demo stub, and named as one** — nothing here is
 * authentication. The API trusts `X-Demo-Role` as sent (`apps/api/deps.py::demo_role_stub`); real
 * JWT, bcrypt and RBAC are S18.
 *
 * The session survives a reload (sessionStorage), because S12's end-to-end check is "refresh, and the
 * adjusted score persists" — a refresh that signed the analyst out would break it for the wrong reason.
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { setApiRole } from "../api/client";
import { isRole, type Role } from "./roles";

export interface Session {
  readonly username: string;
  readonly role: Role;
}

export const SESSION_STORAGE_KEY = "hitl-ids.session.v1";

function readStored(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "username" in parsed &&
      typeof parsed.username === "string" &&
      "role" in parsed &&
      isRole(parsed.role)
    ) {
      return { username: parsed.username, role: parsed.role };
    }
  } catch {
    // Unreadable storage is treated as signed out, never as a default role.
  }
  return null;
}

function store(session: Session | null): void {
  setApiRole(session?.role ?? null);
  try {
    if (session === null) window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    else window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage may be blocked; the session still holds for this page's lifetime.
  }
}

export interface SessionApi {
  readonly session: Session | null;
  readonly signIn: (username: string, role: Role) => void;
  readonly switchRole: (role: Role) => void;
  readonly signOut: () => void;
}

const SessionContext = createContext<SessionApi | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const stored = readStored();
    setApiRole(stored?.role ?? null);
    return stored;
  });

  const update = useCallback((next: Session | null) => {
    store(next);
    setSession(next);
  }, []);

  const signIn = useCallback(
    (username: string, role: Role) => update({ username: username.trim() || "demo", role }),
    [update],
  );
  const switchRole = useCallback(
    (role: Role) => update(session === null ? null : { ...session, role }),
    [session, update],
  );
  const signOut = useCallback(() => update(null), [update]);

  const value = useMemo(
    () => ({ session, signIn, switchRole, signOut }),
    [session, signIn, switchRole, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionApi {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
