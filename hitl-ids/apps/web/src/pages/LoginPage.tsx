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
  // Hold-to-peek: the password is shown only while the pointer is over the eye — or pressing it,
  // which is how touch and keyboard users hold it — and is masked again the moment that ends.
  const [pointerOverEye, setPointerOverEye] = useState(false);
  const [pressingEye, setPressingEye] = useState(false);
  const passwordVisible = pointerOverEye || pressingEye;
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
            <div className="relative">
              <input
                id="password"
                name="password"
                type={passwordVisible ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-sm border border-border bg-raised px-3 py-2 pr-12 text-text"
              />
              <button
                type="button"
                aria-label="Show password"
                title="Hold to show password"
                onMouseEnter={() => setPointerOverEye(true)}
                onMouseLeave={() => setPointerOverEye(false)}
                onPointerDown={() => setPressingEye(true)}
                onPointerUp={() => setPressingEye(false)}
                onPointerCancel={() => setPressingEye(false)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") setPressingEye(true);
                }}
                onKeyUp={(event) => {
                  if (event.key === "Enter" || event.key === " ") setPressingEye(false);
                }}
                onBlur={() => setPressingEye(false)}
                className="absolute inset-y-0 right-0 my-auto mr-2 flex h-7 w-7 items-center justify-center rounded-sm text-dim hover:text-text"
              >
                {passwordVisible ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
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

/** The eye as it appears while the password is masked — hold it to peek. */
function EyeIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

/** The eye struck through, shown only while the password is actually visible. */
function EyeOffIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
      <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
      <line x1="2" x2="22" y1="2" y2="22" />
    </svg>
  );
}
