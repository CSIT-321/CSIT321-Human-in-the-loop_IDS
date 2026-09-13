/**
 * Route guards. They shape the demo, they do not secure it: the API is the only enforcement point,
 * and in the demo build even that is a stub.
 */

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { ROLE_META, type Role } from "./roles";
import { useSession } from "./SessionContext";

/** Signed out -> sign-in. Signed in as another role -> that role's home, not an error page. */
export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { session } = useSession();
  const location = useLocation();
  if (session === null) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (session.role !== role) return <Navigate to={ROLE_META[session.role].home} replace />;
  return <>{children}</>;
}

/** `/` and unknown paths: the signed-in role's home, or sign-in. */
export function HomeRedirect() {
  const { session } = useSession();
  return <Navigate to={session === null ? "/login" : ROLE_META[session.role].home} replace />;
}
