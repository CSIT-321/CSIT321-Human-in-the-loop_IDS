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
    expect(ROLE_META.security_analyst.home).toBe("/analyst/v2-triage");
    expect(ROLE_META.system_admin.home).toBe("/admin/status");
    expect(ROLE_META.evaluator.home).toBe("/evaluator/scenarios");
  });

  it("puts the analyst operational journey first and historical flow analysis last", () => {
    expect(ROLE_META.security_analyst.nav.map(item => item.label)).toEqual([
      "Incoming Alerts", "Alert Triage", "Tier 2 Cases", "Triage Memory", "Selective Review",
      "Overview", "Dashboard", "Alert Queue", "Investigations", "Feedback Impact", "Legacy Flow Workstation",
    ]);
    expect(ROLE_META.security_analyst.nav.at(-1)?.to).toBe("/analyst/workstation");
    for (const role of ROLES) {
      expect(ROLE_META[role].nav.find(item => item.to.endsWith("/v2-triage"))?.label).toBe("Alert Triage");
      expect(ROLE_META[role].nav.some(item => item.label === "Analyst Workspace")).toBe(false);
    }
  });
});
