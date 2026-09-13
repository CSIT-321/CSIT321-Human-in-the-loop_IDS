/**
 * The signed-in frame every role shares: top bar, left navigation, and the routed page.
 *
 * Mounted only inside `RequireRole`, so a session is always present here. The null check is for the
 * one frame between a sign-out and the router's redirect, where rendering the shell would flash a
 * console with no user in it.
 */

import { Outlet } from "react-router";

import { useSession } from "../../session/SessionContext";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell() {
  const { session } = useSession();

  if (session === null) return null;

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="flex-1 overflow-auto px-6 py-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
