/**
 * The role's own navigation, and only that: an analyst never sees an admin link, so a demo that
 * switches roles visibly changes what the console offers.
 */

import { useState } from "react";
import { NavLink } from "react-router";

import { ROLE_META } from "../../session/roles";
import { useSession } from "../../session/SessionContext";

export function Sidebar() {
  const { session } = useSession();
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("hitl-ids.sidebar-collapsed") === "true"; } catch { return false; }
  });

  if (session === null) return null;

  return (
    <nav
      aria-label="Main"
      data-print-hidden="true"
      className={`sidebar shrink-0 overflow-y-auto border-r border-border bg-surface py-3 ${collapsed ? "w-16" : "w-52"}`}
    >
      <div className="flex items-center justify-between gap-1 px-3 pb-2">
        {!collapsed && <p aria-hidden className="label-mono text-dim">{ROLE_META[session.role].label}</p>}
        <button type="button" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed} aria-controls="main-navigation-items"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="rounded-sm border border-border px-2 py-1 text-xs hover:bg-raised"
          onClick={() => setCollapsed(previous => {
            const next = !previous;
            try { localStorage.setItem("hitl-ids.sidebar-collapsed", String(next)); } catch { /* Storage may be disabled. */ }
            return next;
          })}><span aria-hidden>{collapsed ? "»" : "«"}</span></button>
      </div>
      <ul id="main-navigation-items">
        {ROLE_META[session.role].nav.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              aria-label={item.label}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                `relative block border-l-2 py-2 pl-4 pr-3 text-[13px] transition-colors ${
                  isActive
                    ? "border-primary bg-raised font-medium text-text"
                    : "border-transparent text-muted hover:bg-raised/60 hover:text-text"
                }`
              }
            >
              {collapsed ? <span aria-hidden className="font-mono text-xs">{item.label.split(/\s+/).map(word => word[0]).join("").slice(0, 3)}</span> : item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
