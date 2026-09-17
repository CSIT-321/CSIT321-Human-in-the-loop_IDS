/**
 * The signed-in frame every role shares: top bar, left navigation, and the routed page.
 *
 * Mounted only inside `RequireRole`, so a session is always present here. The null check is for the
 * one frame between a sign-out and the router's redirect, where rendering the shell would flash a
 * console with no user in it.
 */

import { useCallback, useState } from "react";
import { Outlet } from "react-router";

import { useSession } from "../../session/SessionContext";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export const SIDEBAR_COLLAPSED_STORAGE_KEY = "hitl-ids-sidebar-collapsed";

function readSidebarPreference(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function AppShell() {
  const { session } = useSession();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarPreference);

  const changeSidebarCollapsed = useCallback((collapsed: boolean) => {
    setSidebarCollapsed(collapsed);
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(collapsed));
    } catch {
      // Storage may be unavailable; the in-memory layout remains usable.
    }
  }, []);

  if (session === null) return null;

  return (
    <div className="flex h-full flex-col bg-bg">
      <TopBar />
      <div className="flex min-h-0 min-w-0 flex-1">
        <Sidebar collapsed={sidebarCollapsed} onCollapsedChange={changeSidebarCollapsed} />
        <main className="min-w-0 flex-1 overflow-auto px-6 py-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
