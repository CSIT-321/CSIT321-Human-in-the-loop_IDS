/**
 * The three demo roles and what each one sees (plan step S11, decision D6).
 *
 * The role literals mirror `packages/contracts/models.py::Role`; `roles.test.ts` fails if the
 * generated API schema stops accepting one of them. Each role's `home` is where it lands after
 * sign-in, as the plan's S11 verification names it: analyst -> queue, admin -> system status,
 * evaluator -> scenario list.
 */

export const ROLES = ["security_analyst", "system_admin", "evaluator"] as const;
export type Role = (typeof ROLES)[number];

/** The request header the API's `demo_role_stub` reads. Trusted as sent: S18 replaces it. */
export const ROLE_HEADER = "X-Demo-Role";

export interface NavItem {
  readonly to: string;
  readonly label: string;
}

export interface RoleMeta {
  /** Full name, as the top bar shows it. */
  readonly label: string;
  /** Short name, as the sign-in chips show it. */
  readonly short: string;
  /** Where the role lands after sign-in or a role switch. Always one of `nav`. */
  readonly home: string;
  /** Left navigation, in display order. */
  readonly nav: readonly NavItem[];
}

export const ROLE_META: Readonly<Record<Role, RoleMeta>> = {
  security_analyst: {
    label: "Security Analyst",
    short: "Analyst",
    home: "/analyst/workstation",
    nav: [
      { to: "/analyst/workstation", label: "Workstation" },
      { to: "/analyst/overview", label: "Overview" },
      { to: "/analyst/dashboard", label: "Dashboard" },
      { to: "/analyst/queue", label: "Alert Queue" },
      { to: "/analyst/investigations", label: "Investigations" },
      { to: "/analyst/feedback-impact", label: "Feedback Impact" },
    ],
  },
  system_admin: {
    label: "System Administrator",
    short: "Administrator",
    home: "/admin/status",
    nav: [
      { to: "/admin/status", label: "System Status" },
      { to: "/admin/guardrails", label: "Guardrails" },
      { to: "/admin/audit", label: "Audit Trail" },
    ],
  },
  evaluator: {
    label: "Evaluator",
    short: "Evaluator",
    home: "/evaluator/scenarios",
    nav: [
      { to: "/evaluator/scenarios", label: "Scenarios" },
      { to: "/evaluator/metrics", label: "Detection Metrics" },
    ],
  },
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}
