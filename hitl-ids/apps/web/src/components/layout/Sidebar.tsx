import { useState } from "react";
import { NavLink } from "react-router";
import { ROLE_META } from "../../session/roles";
import { useSession } from "../../session/SessionContext";
export function Sidebar() {
  const { session } = useSession();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("hitl.sidebar.collapsed") === "true");
  const [mobileOpen, setMobileOpen] = useState(false);
  if (!session) return null;
  const items = ROLE_META[session.role].nav;
  const groups = [...new Set(items.map(item => item.group ?? ROLE_META[session.role].label))];
  return <nav aria-label="Main" data-print-hidden="true" className={`sidebar ${collapsed ? "is-collapsed" : ""}`}>
    <button className="mobile-menu" aria-expanded={mobileOpen} aria-controls="main-navigation" onClick={() => setMobileOpen(!mobileOpen)}>☰ Navigation</button>
    <button className="sidebar-toggle" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={() => {
      localStorage.setItem("hitl.sidebar.collapsed", String(!collapsed)); setCollapsed(!collapsed);
    }}>{collapsed ? "»" : "«"}<span className="nav-label"> Collapse sidebar</span></button>
    <div id="main-navigation" className={mobileOpen ? "mobile-open" : ""}>
      {groups.map(group => <section key={group} aria-label={group}>
        <h2 className="nav-group">{group}</h2>
        <ul>{items.filter(item => (item.group ?? ROLE_META[session.role].label) === group).map(item => <li key={item.to}>
          <NavLink to={item.to} title={item.label} aria-label={item.label} onClick={() => setMobileOpen(false)} className={({isActive}) => `nav-item ${isActive ? "active" : ""}`}>
            <span aria-hidden className="nav-icon">{item.icon ?? "◇"}</span><span className="nav-label">{item.label}</span>
          </NavLink>
        </li>)}</ul>
      </section>)}
    </div>
  </nav>;
}
