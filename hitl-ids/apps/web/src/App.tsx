/**
 * Routing for the three role paths (plan steps S11-S14).
 *
 * `routes` is exported so tests mount the real route table in a memory router, rather than a copy of
 * it that could disagree. Each page lives in its own file under `pages/<role>/`, so the three role
 * paths can be built in parallel without editing this table.
 */

import { useState } from "react";
import { createBrowserRouter, Navigate, useLocation, RouterProvider, type RouteObject } from "react-router";

import { AppShell } from "./components/layout/AppShell";
import { AuditPage } from "./pages/admin/AuditPage";
import { GuardrailsPage } from "./pages/admin/GuardrailsPage";
import { IpSecurityReportPage } from "./pages/admin/IpSecurityReportPage";
import { StatusPage } from "./pages/admin/StatusPage";
import { AlertDetailPage } from "./pages/analyst/AlertDetailPage";
import { LegacyAnalyticsPage } from "./pages/analyst/LegacyAnalyticsPage";
import { OverviewPage } from "./pages/analyst/OverviewPage";
import { AnalyticsPage } from "./pages/analyst/AnalyticsPage";
import { DashboardPage } from "./pages/analyst/DashboardPage";
import { FeedbackImpactPage } from "./pages/analyst/FeedbackImpactPage";
import { InvestigationsPage } from "./pages/analyst/InvestigationsPage";
import { IpEntityPage } from "./pages/analyst/IpEntityPage";
import { QueuePage } from "./pages/analyst/QueuePage";
import { WorkstationPage } from "./pages/analyst/WorkstationPage";
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

function AnalystAlias({to}: {to:string}) { const {search} = useLocation(); return <Navigate to={to+search} replace/>; }

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
      { path: "workstation", element: <WorkstationPage /> },
      { path: "selective-review", element: <SelectiveReviewPage /> },
      { path: "triage-memory", element: <TriageMemoryPage /> },
      { path: "tier2-cases", element: <Tier2CasesPage /> },
      { path: "tier2-cases/:caseRef", element: <Tier2CaseDetailPage /> },
      { path: "external-admission", element: <AnalystAlias to="/analyst/inbox" /> },
      { path: "v2-triage", element: <AnalystAlias to="/analyst/workspace" /> },
      { path: "overview", element: <Navigate to="/analyst/dashboard" replace /> },
      { path: "inbox", element: <ExternalAdmissionPage /> },
      { path: "workspace", element: <V2RoutingPage /> },
      { path: "analytics", element: <AnalyticsPage /> },
      { path: "legacy-overview", element: <OverviewPage /> },
      { path: "legacy-analytics", element: <LegacyAnalyticsPage /> },
      { path: "entities/ip/:ip", element: <IpEntityPage /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "queue", element: <QueuePage /> },
      { path: "alerts/:alertRef", element: <AlertDetailPage /> },
      { path: "investigations", element: <InvestigationsPage /> },
      { path: "feedback-impact", element: <FeedbackImpactPage /> },
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
      { path: "status", element: <StatusPage /> },
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
      <RouterProvider router={router} />
    </SessionProvider>
  );
}
