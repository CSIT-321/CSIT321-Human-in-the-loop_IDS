import { describe, expect, it } from "vitest";

import type { components } from "../api/schema";
import { ROLE_META, ROLES, type Role } from "./roles";

// Compile-time: the console's roles are exactly the roles the API issues at sign-in. `npm run build`
// type-checks this file, so a contract change that adds or drops a role fails the build here.
type ContractRole = components["schemas"]["LoginResponse"]["role"];
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
const rolesMatchContract: Equal<Role, ContractRole> = true;

describe("roles", () => {
  it("match the API contract", () => {
    expect(rolesMatchContract).toBe(true);
    expect(Object.keys(ROLE_META).sort()).toEqual([...ROLES].sort());
  });

  it.each(ROLES)("%s lands on a page in its own navigation", (role) => {
    const meta = ROLE_META[role];
    expect(meta.nav.map((item) => item.to)).toContain(meta.home);
  });

  it("send analysts to operational triage and preserve the other role homes", () => {
    // Historical flow analysis remains a deep link, separate from the operational home.
    expect(ROLE_META.security_analyst.home).toBe("/analyst/operations");
    expect(ROLE_META.system_admin.home).toBe("/admin/status");
    expect(ROLE_META.evaluator.home).toBe("/evaluator/scenarios");
  });

  it("shows one primary analyst workspace and secondary intake", () => {
    expect(ROLE_META.security_analyst.nav.map(item => item.label)).toEqual([
      "Analyst Workstation", "Tier 2 Cases", "Triage Memory", "Selective Review", "Dashboard", "Incoming Alerts",
    ]);
    expect(ROLE_META.security_analyst.nav.at(-1)?.to).toBe("/analyst/external-admission");
    expect(ROLE_META.security_analyst.nav.some(item => item.to.endsWith("/workstation") || item.to.endsWith("/v2-triage"))).toBe(false);
    for (const role of ["system_admin", "evaluator"] as const) {
      expect(ROLE_META[role].nav.find(item => item.to.endsWith("/v2-triage"))?.label).toBe("Alert Triage");
      expect(ROLE_META[role].nav.some(item => item.label === "Analyst Workspace")).toBe(false);
    }
  });
});
