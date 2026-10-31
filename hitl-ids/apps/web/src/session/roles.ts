/**
 * The three demo roles and what each one sees (plan step S11, decision D6).
 *
 * The role literals mirror `packages/contracts/models.py::Role`; `roles.test.ts` fails if the
 * generated API schema stops accepting one of them. Each role's `home` is where its account lands
 * after sign-in, as the plan's S11 verification names it: analyst -> queue, admin -> system status,
 * evaluator -> scenario list. Since S18a the role is a property of the signed-in account, not a
 * header a client sends.
 */

export const ROLES = ["security_analyst", "system_admin", "evaluator"] as const;
export type Role = (typeof ROLES)[number];

export interface NavItem {
  readonly to: string;
  readonly label: string;
  readonly group?: string;
  readonly icon?: string;
}

export interface RoleMeta {
  /** Full name, as the top bar shows it. */
  readonly label: string;
  /** Short name, as the account picker on the sign-in page once showed it. */
  readonly short: string;
  /** Where the account lands after sign-in. Always one of `nav`. */
  readonly home: string;
  /** Left navigation, in display order. */
  readonly nav: readonly NavItem[];
}

export const ROLE_META: Readonly<Record<Role, RoleMeta>> = {
  security_analyst: {
    label: "Security Analyst",
    short: "Analyst",
    home: "/analyst/dashboard",
    nav: [
      { to: "/analyst/dashboard", label: "Dashboard", group: "Operations", icon: "◫" },
      { to: "/analyst/inbox", label: "Incoming Alerts", group: "Operations", icon: "⇥" },
      { to: "/analyst/workspace", label: "Analyst Workspace", group: "Operations", icon: "⌕" },
      { to: "/analyst/tier2-cases", label: "Tier 2 Cases", group: "Operations", icon: "▣" },
      { to: "/analyst/triage-memory", label: "Triage Memory", group: "Learning & Automation", icon: "◇" },
      { to: "/analyst/selective-review", label: "Selective Review", group: "Learning & Automation", icon: "✓" },
      { to: "/analyst/analytics", label: "Analytics", group: "Insights", icon: "▥" },
      { to: "/analyst/workstation", label: "Legacy Workstation", group: "Legacy", icon: "▤" },
    ],
  },
  system_admin: {
    label: "System Administrator",
    short: "Administrator",
    home: "/admin/status",
    nav: [
      { to: "/admin/status", label: "System Status" },
      { to: "/admin/tier2-cases", label: "Tier 2 Cases" },
      { to: "/admin/triage-memory", label: "Triage Memory" },
      { to: "/admin/selective-review", label: "Selective Review" },
      { to: "/admin/external-admission", label: "Incoming Alerts" },
      { to: "/admin/v2-triage", label: "Analyst Workspace" },
      { to: "/admin/guardrails", label: "Guardrails" },
      { to: "/admin/audit", label: "Audit Trail" },
      { to: "/admin/reports/ip", label: "IP Security Report" },
    ],
  },
  evaluator: {
    label: "Evaluator",
    short: "Evaluator",
    home: "/evaluator/scenarios",
    nav: [
      { to: "/evaluator/scenarios", label: "Scenarios" },
      { to: "/evaluator/tier2-cases", label: "Tier 2 Cases" },
      { to: "/evaluator/triage-memory", label: "Triage Memory" },
      { to: "/evaluator/selective-review", label: "Selective Review" },
      { to: "/evaluator/external-admission", label: "Incoming Alerts" },
      { to: "/evaluator/v2-triage", label: "Analyst Workspace" },
      { to: "/evaluator/metrics", label: "Detection Metrics" },
    ],
  },
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}
