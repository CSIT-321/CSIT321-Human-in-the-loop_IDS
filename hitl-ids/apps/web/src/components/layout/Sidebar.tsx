/**
 * The role's own navigation, and only that: an analyst never sees an admin link, so a demo that
 * switches roles visibly changes what the console offers.
 */

import { NavLink } from "react-router";

import { ROLE_META } from "../../session/roles";
import { useSession } from "../../session/SessionContext";

export function Sidebar() {
  const { session } = useSession();

  if (session === null) return null;

  return (
    <nav
      aria-label="Main"
      data-print-hidden="true"
      className="w-52 shrink-0 border-r border-border bg-surface py-3"
    >
      <p aria-hidden className="label-mono px-4 pb-2 text-dim">
        {ROLE_META[session.role].label}
      </p>
      <ul>
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
    </nav>
  );
}
