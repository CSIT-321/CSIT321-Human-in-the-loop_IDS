import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView } from "../../components/states";
import { Card, PageHeader } from "../../components/ui";

const roles = [
  ["Security Analyst", "Operational alert handling, Tier 1 review, and Tier 2 / Senior Analyst investigation through Tier 2 Cases."],
  ["System Administrator", "System governance, Operational Workspace, Users & Access, Final V3.1 Evaluation, and Current HITL Audit."],
] as const;

const roleName = (role: string) => role === "system_admin" ? "System Administrator" : "Security Analyst";

export function UsersPage() {
  const resource = useApi(signal => unwrap(api.GET("/api/admin/users", { signal })), []);
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Users & Access" subtitle="Read-only visibility of current product accounts and roles." />
    <Card title="Current product users"><ApiView resource={resource}>{data => <div className="overflow-x-auto p-4">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead><tr className="border-b border-border text-muted"><th className="p-2">Username</th><th className="p-2">Name</th><th className="p-2">Role</th><th className="p-2">Status</th><th className="p-2">Last Login</th></tr></thead>
        <tbody>{data.items.filter(user => user.role === "security_analyst" || user.role === "system_admin").map(user => <tr className="border-b border-border" key={user.username}>
          <td className="break-all p-2 font-mono text-xs">{user.username}</td><td className="p-2">{user.displayName}</td>
          <td className="p-2">{roleName(user.role)}</td><td className="p-2 capitalize">{user.status}</td>
          <td className="p-2 text-muted">{user.lastLogin ?? "Not available"}</td>
        </tr>)}</tbody>
      </table>
      {!data.items.some(user => user.role === "security_analyst" || user.role === "system_admin") && <p className="p-2 text-muted">No product users available.</p>}
    </div>}</ApiView></Card>
    <Card title="Product roles"><div className="grid min-w-0 gap-3 p-4 md:grid-cols-2">{roles.map(([role, purpose]) =>
      <section className="min-w-0 space-y-1" key={role}><h3 className="font-semibold">{role}</h3><p className="text-sm text-muted">{purpose}</p></section>)}</div></Card>
    <p className="text-xs text-muted">This phase provides account visibility only. Authentication and permissions are unchanged.</p>
  </div>;
}
