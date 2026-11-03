/**
 * Routing for the three role paths (plan steps S11-S14).
 *
 * `routes` is exported so tests mount the real route table in a memory router, rather than a copy of
 * it that could disagree. Each page lives in its own file under `pages/<role>/`, so the three role
 * paths can be built in parallel without editing this table.
 */

import { useState } from "react";
import { createBrowserRouter, RouterProvider, type RouteObject, Navigate, useLocation, Link } from "react-router";
import { flushSync } from "react-dom";

import { AppShell } from "./components/layout/AppShell";
import { AuditPage } from "./pages/admin/AuditPage";
import { GuardrailsPage } from "./pages/admin/GuardrailsPage";
import { IpSecurityReportPage } from "./pages/admin/IpSecurityReportPage";
import { StatusPage } from "./pages/admin/StatusPage";
import { WorkspacesPage } from "./pages/admin/WorkspacesPage";
import { OverviewPage } from "./pages/admin/OverviewPage";
import { GovernancePage } from "./pages/admin/GovernancePage";
import { UsersPage } from "./pages/admin/UsersPage";
import { EvaluationAuditPage } from "./pages/admin/EvaluationAuditPage";
import { CurrentAuditPage } from "./pages/admin/CurrentAuditPage";
import { FinalV31Page, FinalV31DetailPage } from "./pages/evaluator/FinalV31Page";
import { MetricsPage } from "./pages/evaluator/MetricsPage";
import { RunPage } from "./pages/evaluator/RunPage";
import { ScenariosPage } from "./pages/evaluator/ScenariosPage";
import { LoginPage } from "./pages/LoginPage";
import { V2RoutingPage } from "./pages/analyst/V2RoutingPage";
import { TriageMemoryPage } from "./pages/analyst/TriageMemoryPage";
import { SelectiveReviewPage } from "./pages/analyst/SelectiveReviewPage";
import { ExternalAdmissionPage } from "./pages/analyst/ExternalAdmissionPage";
import { Tier2CasesPage, Tier2CaseDetailPage } from "./pages/analyst/Tier2CasesPage";
import { HomeRedirect, RequireRole } from "./session/guards";
import { SessionProvider } from "./session/SessionContext";

function WorkstationRedirect() {
  const location=useLocation();
  const previous=new URLSearchParams(location.search);
  const query=new URLSearchParams();
  // Only the supported current alert identity survives the compatibility URL.
  if(previous.has('alertRef'))query.set('alertRef',previous.get('alertRef')!);
  return <Navigate replace to={'/analyst/operations'+(query.size?'?'+query.toString():'')}/>;
}
function AnalystNotFound() {
  return <div className="p-6"><h1>Page not found</h1><Link to="/analyst/operations">Open Analyst Workstation</Link></div>;
}

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/analyst",
    element: (
      <RequireRole role="security_analyst">
        <AppShell />
      </RequireRole>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: "workstation", element: <WorkstationRedirect /> },
      { path: "operations", element: <></> },
      { path: "selective-review", element: <SelectiveReviewPage /> },
      { path: "triage-memory", element: <TriageMemoryPage /> },
      { path: "tier2-cases", element: <Tier2CasesPage /> },
      { path: "tier2-cases/:caseRef", element: <Tier2CaseDetailPage /> },
      { path: "external-admission", element: <ExternalAdmissionPage /> },
      { path: "v2-triage", element: <WorkstationRedirect /> },
      { path: "*", element: <AnalystNotFound /> },
    ],
  },
  {
    path: "/admin",
    element: (
      <RequireRole role="system_admin">
        <AppShell />
      </RequireRole>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: "overview", element: <OverviewPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "workspaces", element: <WorkspacesPage /> },
      { path: "governance", element: <GovernancePage /> },
      { path: "users", element: <UsersPage /> },
      { path: "evaluation", element: <EvaluationAuditPage /> },
      { path: "evaluation/audit", element: <CurrentAuditPage /> },
      { path: "evaluation/final-v3-1", element: <FinalV31Page /> },
      { path: "evaluation/final-v3-1/records/:index", element: <FinalV31DetailPage /> },
      { path: "selective-review", element: <SelectiveReviewPage /> },
      { path: "triage-memory", element: <TriageMemoryPage /> },
      { path: "tier2-cases", element: <Tier2CasesPage /> },
      { path: "tier2-cases/:caseRef", element: <Tier2CaseDetailPage /> },
      { path: "external-admission", element: <ExternalAdmissionPage /> },
      { path: "v2-triage", element: <V2RoutingPage /> },
      { path: "guardrails", element: <GuardrailsPage /> },
      { path: "audit", element: <AuditPage /> },
      { path: "reports/ip", element: <IpSecurityReportPage /> },
    ],
  },
  {
    path: "/evaluator",
    element: (
      <RequireRole role="evaluator">
        <AppShell />
      </RequireRole>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: "scenarios", element: <ScenariosPage /> },
      { path: "final-v3-1", element: <FinalV31Page /> },
      { path: "final-v3-1/records/:index", element: <FinalV31DetailPage /> },
      { path: "selective-review", element: <SelectiveReviewPage /> },
      { path: "triage-memory", element: <TriageMemoryPage /> },
      { path: "tier2-cases", element: <Tier2CasesPage /> },
      { path: "tier2-cases/:caseRef", element: <Tier2CaseDetailPage /> },
      { path: "external-admission", element: <ExternalAdmissionPage /> },
      { path: "v2-triage", element: <V2RoutingPage /> },
      { path: "runs/:runId", element: <RunPage /> },
      { path: "metrics", element: <MetricsPage /> },
    ],
  },
  { path: "*", element: <HomeRedirect /> },
];

export function App() {
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <SessionProvider>
      <RouterProvider router={router} flushSync={callback => { flushSync(callback); return undefined; }} />
    </SessionProvider>
  );
}
