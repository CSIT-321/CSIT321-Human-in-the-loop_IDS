import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView } from "../../components/states";
import { Card, PageHeader } from "../../components/ui";

const roles = [
  ["Security Analyst", "Operational alert handling: Workstation, Verdict, Memory evidence, and Tier 2 investigation."],
  ["System Administrator", "System governance: workspaces, policies, users, and evaluation/audit."],
  ["Evaluator", "Read-only evaluation and assessment access."],
] as const;

export function UsersPage() {
  const resource = useApi(signal => unwrap(api.GET("/api/admin/users", { signal })), []);
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Users & Access" subtitle="Read-only visibility of current product accounts and roles." />
    <Card title="Current accounts"><ApiView resource={resource}>{data => <div className="grid min-w-0 gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
      {data.items.map(user => <article className="min-w-0 space-y-1 rounded-sm border border-border bg-raised p-3 text-sm" key={user.username}>
        <h3 className="break-words font-semibold">{user.displayName}</h3>
        <p className="break-all font-mono text-xs">{user.username}</p>
        <p className="break-words">Role: {user.role.replaceAll("_", " ")}</p>
        <p>Status: {user.status}</p>
        <p className="break-words text-muted">Last login: {user.lastLogin ?? "Not available"}</p>
      </article>)}
      {data.items.length === 0 && <p className="text-muted">No accounts available.</p>}
    </div>}</ApiView></Card>
    <Card title="Product roles"><div className="grid min-w-0 gap-3 p-4 md:grid-cols-3">{roles.map(([role, purpose]) =>
      <section className="min-w-0 space-y-1" key={role}><h3 className="font-semibold">{role}</h3><p className="text-sm text-muted">{purpose}</p></section>)}</div></Card>
    <p className="text-xs text-muted">This phase provides account visibility only. Authentication and permissions are unchanged.</p>
  </div>;
}
