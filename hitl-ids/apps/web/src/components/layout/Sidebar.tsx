/**
 * The role's own navigation, and only that: an analyst never sees an admin link, so a demo that
 * switches roles visibly changes what the console offers.
 */

import { NavLink } from "react-router";

import { ROLE_META } from "../../session/roles";
import { useSession } from "../../session/SessionContext";

interface SidebarProps {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

export function Sidebar({ collapsed, onCollapsedChange }: SidebarProps) {
  const { session } = useSession();

  if (session === null) return null;

  return (
    <nav
      aria-label="Main"
      data-collapsed={collapsed ? "true" : "false"}
      className={`${collapsed ? "w-14" : "w-52"} shrink-0 overflow-hidden border-r border-border bg-surface py-3 transition-[width] duration-150`}
    >
      <div className={`flex pb-2 ${collapsed ? "justify-center px-1" : "items-center justify-between px-3"}`}>
        {!collapsed && (
          <p aria-hidden className="label-mono min-w-0 truncate pl-1 text-dim">
            {ROLE_META[session.role].label}
          </p>
        )}
        <button
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          aria-controls="main-navigation-links"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => onCollapsedChange(!collapsed)}
          className="flex h-8 w-8 shrink-0 items-center justify-center border border-border bg-bg text-base text-muted transition-colors hover:bg-raised hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden="true">{collapsed ? <>&rsaquo;</> : <>&lsaquo;</>}</span>
        </button>
      </div>
      {!collapsed && (
        <ul id="main-navigation-links">
          {ROLE_META[session.role].nav.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `relative block border-l-2 py-2 pl-4 pr-3 text-[13px] transition-colors ${
                    isActive
                      ? "border-primary bg-raised font-medium text-text"
                      : "border-transparent text-muted hover:bg-raised/60 hover:text-text"
                  }`
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
