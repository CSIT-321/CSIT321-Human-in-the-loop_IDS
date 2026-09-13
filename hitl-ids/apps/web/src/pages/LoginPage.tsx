/**
 * Sign-in. **A demo stub, and labelled as one on the page.**
 *
 * The role chips are the whole of "authentication" in the demo build: `signIn` records a session and
 * the API trusts the role it is sent. The password field exists so the wireframe matches the real
 * design, and its value is never stored, sent or logged — nothing outside this controlled input
 * reads it. S18 adds JWT, bcrypt and role-based access control.
 */

import { useState } from "react";
import { Navigate, useNavigate } from "react-router";

import { ROLES, ROLE_META, type Role } from "../session/roles";
import { useSession } from "../session/SessionContext";

export function LoginPage() {
  const { session, signIn } = useSession();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("security_analyst");

  if (session !== null) return <Navigate to={ROLE_META[session.role].home} replace />;

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 bg-bg p-6">
      <div className="w-full max-w-md rounded-sm border border-border bg-surface p-6">
        <span aria-hidden className="block h-8 w-8 rounded-sm bg-accent" />
        <h1 className="mt-4 text-2xl font-semibold text-text">IDS Console</h1>
        <p className="mt-1 text-sm text-muted">Human-in-the-loop intrusion detection</p>

        <form
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            signIn(username, role);
            void navigate(ROLE_META[role].home, { replace: true });
          }}
        >
          <div className="space-y-1">
            <label htmlFor="username" className="block text-sm text-muted">
              Username
            </label>
            <input
              id="username"
              name="username"
              type="text"
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
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-sm border border-border bg-raised px-3 py-2 text-text placeholder:text-dim"
            />
          </div>

          <div className="space-y-2">
            <span className="block text-sm text-muted">Sign in as</span>
            <div role="radiogroup" aria-label="Sign in as" className="flex flex-wrap gap-2">
              {ROLES.map((option) => {
                const selected = option === role;
                return (
                  <button
                    key={option}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setRole(option)}
                    className={`rounded-sm px-3 py-1.5 text-sm ${
                      selected
                        ? "border border-accent bg-accent-dim text-accent"
                        : "border border-transparent bg-raised text-muted"
                    }`}
                  >
                    {ROLE_META[option].short}
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="submit"
            className="w-full rounded-sm bg-primary px-3 py-2 font-semibold text-white hover:bg-primary-hover"
          >
            Sign in
          </button>
        </form>
      </div>

      <div className="w-full max-w-md rounded-sm border border-stub/40 bg-stub-bg p-4 text-sm">
        <p className="font-semibold text-stub">Demo build</p>
        <p className="mt-1 text-text">Authentication is a stub: the role you pick is trusted as sent.</p>
      </div>

      <p className="w-full max-w-md text-xs italic text-dim">
        Real sign-in (JWT, bcrypt, role-based access control) is scheduled after the demo gate.
      </p>
    </div>
  );
}
