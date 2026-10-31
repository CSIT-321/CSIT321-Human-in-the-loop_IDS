import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { jsonResponse, renderApp, stubFetch } from "../../test/renderApp";
const session = {username:"g.ang",displayName:"Analyst",role:"security_analyst" as const,token:"test"};
function stub() { stubFetch(req => req.url.includes("/metrics") ? jsonResponse({mustReviewCount:3,recommendedReviewCount:2,noImmediateReviewCount:4,conflictTriggeredRecallCount:1,sampledOverrideCount:0,dataBasis:"Local decisions"}) : jsonResponse({items:[],page:{total:0}})); }
it("lands on the operational dashboard with grouped navigation and no legacy fusion metrics", async()=>{
  stub(); const {router}=renderApp("/analyst",{session});
  expect(await screen.findByRole("heading",{name:"Dashboard"})).toBeVisible();
  expect(router.state.location.pathname).toBe("/analyst/dashboard");
  expect(await screen.findByText("Needs Human Review")).toBeVisible();
  const nav=screen.getByRole("navigation",{name:"Main"});
  for(const name of ["Operations","Learning & Automation","Insights","Legacy"]) expect(within(nav).getByRole("region",{name})).toBeInTheDocument();
  for(const label of ["Signature override","Model only","Corroborated","Nothing flagged it"]) expect(screen.queryByText(label)).not.toBeInTheDocument();
  expect(screen.getByText("No Immediate Review is not a human verdict.")).toBeVisible();
});
it("persists sidebar and theme preferences across remount",async()=>{
  localStorage.removeItem("hitl.sidebar.collapsed");localStorage.removeItem("hitl.theme");stub();
  const first=renderApp("/analyst/dashboard",{session});
  await userEvent.click(screen.getByRole("button",{name:"Collapse sidebar"}));
  await userEvent.click(screen.getByRole("button",{name:"Switch to Light theme"}));
  expect(localStorage.getItem("hitl.sidebar.collapsed")).toBe("true");expect(document.documentElement.dataset.theme).toBe("light");
  first.unmount();renderApp("/analyst/dashboard",{session});
  expect(screen.getByRole("button",{name:"Expand sidebar"})).toHaveAttribute("aria-expanded","false");
  expect(screen.getByRole("button",{name:"Switch to Dark theme"})).toBeVisible();
});
it("keeps legacy analytics intentionally accessible and redirects overview",async()=>{
  stub(); const first=renderApp("/analyst/analytics",{session});
  expect(screen.getByRole("link",{name:"Open legacy detector analytics"})).toHaveAttribute("href","/analyst/legacy-analytics");
  first.unmount();const {router}=renderApp("/analyst/overview",{session});
  expect(await screen.findByRole("heading",{name:"Dashboard"})).toBeVisible();expect(router.state.location.pathname).toBe("/analyst/dashboard");
});
