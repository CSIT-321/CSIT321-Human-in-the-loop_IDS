/**
 * Sign-in. Real since S18a: the username and password go to `POST /api/auth/login`, and the
 * account that answers — including its role — is the session. There is no role picker: a view
 * belongs to the account signed into it.
 */

import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";

import { unwrap, api, ApiError } from "../api/client";
import { ROLE_META } from "../session/roles";
import { useSession, type Session } from "../session/SessionContext";

export function LoginPage() {
  const { session, signIn } = useSession();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (session !== null) return <Navigate to={ROLE_META[session.role].home} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const account = await unwrap(api.POST("/api/auth/login", {
        body: { username: username.trim(), password },
      }));
      const next: Session = {
        username: account.username,
        displayName: account.displayName,
        role: account.role,
        token: account.token,
      };
      signIn(next);
      void navigate(ROLE_META[next.role].home, { replace: true });
    } catch (cause) {
      // The API's envelope message is safe to display as written ("Invalid username or password",
      // "Cannot reach the API. …"); anything else is unexpected but still worth showing.
      setError(cause instanceof ApiError ? cause.message : "Sign-in failed. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 bg-bg p-6">
      <div className="w-full max-w-md rounded-sm border border-border bg-surface p-6">
        <span aria-hidden className="block h-8 w-8 rounded-sm bg-accent" />
        <h1 className="mt-4 text-2xl font-semibold text-text">IDS Console</h1>
        <p className="mt-1 text-sm text-muted">Human-in-the-loop intrusion detection</p>

        <form className="mt-6 space-y-4" onSubmit={submit}>
          <div className="space-y-1">
            <label htmlFor="username" className="block text-sm text-muted">
              Username
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              placeholder="e.g. g.ang"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-sm border border-border bg-raised px-3 py-2 text-text placeholder:text-dim"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="block text-sm text-muted">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-sm border border-border bg-raised px-3 py-2 text-text"
            />
          </div>

          {error !== null && (
            <p role="alert" className="rounded-sm border border-danger/40 bg-danger-dim px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={pending || username.trim() === "" || password === ""}
            className="w-full rounded-sm bg-primary px-3 py-2 font-semibold text-white hover:bg-primary-hover disabled:opacity-50"
          >
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>

      <p className="w-full max-w-md text-xs italic text-dim">
        One account per view: the role you get is the role of the account you sign in as.
      </p>
    </div>
  );
}
