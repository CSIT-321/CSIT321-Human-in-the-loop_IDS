/**
 * Routing for the three role paths (plan steps S11-S14).
 *
 * `routes` is exported so tests mount the real route table in a memory router, rather than a copy of
 * it that could disagree. Each page lives in its own file under `pages/<role>/`, so the three role
 * paths can be built in parallel without editing this table.
 */

import { useState } from "react";
import { createBrowserRouter, RouterProvider, type RouteObject } from "react-router";

import { AppShell } from "./components/layout/AppShell";
import { AuditPage } from "./pages/admin/AuditPage";
import { GuardrailsPage } from "./pages/admin/GuardrailsPage";
import { StatusPage } from "./pages/admin/StatusPage";
import { AlertDetailPage } from "./pages/analyst/AlertDetailPage";
import { DashboardPage } from "./pages/analyst/DashboardPage";
import { FeedbackImpactPage } from "./pages/analyst/FeedbackImpactPage";
import { InvestigationsPage } from "./pages/analyst/InvestigationsPage";
import { QueuePage } from "./pages/analyst/QueuePage";
import { WorkstationPage } from "./pages/analyst/WorkstationPage";
import { MetricsPage } from "./pages/evaluator/MetricsPage";
import { RunPage } from "./pages/evaluator/RunPage";
import { ScenariosPage } from "./pages/evaluator/ScenariosPage";
import { LoginPage } from "./pages/LoginPage";
import { HomeRedirect, RequireRole } from "./session/guards";
import { SessionProvider } from "./session/SessionContext";

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
      { path: "guardrails", element: <GuardrailsPage /> },
      { path: "audit", element: <AuditPage /> },
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
