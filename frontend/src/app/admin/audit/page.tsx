"use client";
import { useApi } from "@/lib/api";
import { RoleGate } from "@/lib/auth";
import { PageHead, State } from "@/components/ui";

type E = { id: number; actor: string | null; action: string; object_type: string | null; object_id: string | null; details: Record<string, unknown>; occurred_at: number };

function AuditInner() {
  const r = useApi<{ items: E[] }>("/admin/audit?limit=200");
  return (
    <>
      <PageHead eyebrow="Administration" title="Audit log">Append-only record of sign-ins, user changes, transactions, alert triage, jobs and model promotion. Latest 200 events.</PageHead>

      <State loading={r.loading} error={r.error}>
        <div className="card scroll"><table><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Object</th><th>Details</th></tr></thead><tbody>
          {r.data?.items.map((e) => (
            <tr key={e.id}><td>{new Date(e.occurred_at * 1000).toLocaleString()}</td><td>{e.actor ?? "—"}</td><td>{e.action}</td>
              <td>{e.object_type ? `${e.object_type} ${e.object_id ?? ""}` : "—"}</td><td className="small">{JSON.stringify(e.details)}</td></tr>))}
        </tbody></table></div>
      </State>
    </>
  );
}

export default function Audit() {
  return <RoleGate allow={["admin"]}><AuditInner /></RoleGate>;
}
