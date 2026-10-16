"use client";
import { useEffect, useState } from "react";
import { api, useApi } from "@/lib/api";
import { RoleGate } from "@/lib/auth";
import { Card, PageHead, State } from "@/components/ui";

type Job = { id: string; kind: string; status: string; created_at: number; finished_at: number | null; log_tail: string | null; error_code: string | null };
type Promo = { id: number; family: string; run_id: string; reason: string; kind: string; created_at: number };
type Run = { models: { family: string; label: string; threshold: number | null; threshold_status: string; test: { average_precision?: number } }[]; champion: string | null; run_id: string };

const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleString() : "—");

function OpsInner() {
  const [bump, setBump] = useState(0);
  const jobs = useApi<{ items: Job[] }>("/admin/jobs", [bump]);
  const promos = useApi<{ items: Promo[] }>("/ml/promotions", [bump]);
  const run = useApi<Run>("/ml/comparison", [bump]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [reason, setReason] = useState("");
  const active = jobs.data?.items.some((j) => j.status === "running" || j.status === "pending");

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setBump((b) => b + 1), 3000);
    return () => clearInterval(t);
  }, [active]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(null);
    try { await fn(); setMsg({ ok: true, text: ok }); } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" }); }
    setBump((b) => b + 1);
  };
  const current = promos.data?.items[0]?.family ?? null;

  return (
    <>
      <PageHead eyebrow="Administration" title="Operations">Run jobs in a separate process and promote or roll back models. Nothing is ever auto-deployed.</PageHead>
      {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "note" : "note err"}>{msg.text}</p>}
      <Card title="Jobs" note="Jobs run in a separate Python process and survive page reloads. One active job at a time. Training never auto-promotes a model.">
        <p style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button disabled={!!active} onClick={() => act(() => api("/admin/jobs", { method: "POST", body: JSON.stringify({ kind: "train" }) }), "Training job queued (exactly LR / RF / HGB).")}>Retrain 3 models</button>
          <button disabled={!!active} onClick={() => act(() => api("/admin/jobs", { method: "POST", body: JSON.stringify({ kind: "cluster" }) }), "Clustering job queued.")}>Re-run KMeans</button>
          <button disabled={!!active} onClick={() => { if (confirm("Regenerate the whole synthetic dataset? This replaces the ledger (manual entries are lost) and retrains everything.")) act(() => api("/admin/jobs", { method: "POST", body: JSON.stringify({ kind: "regenerate", confirm: true }) }), "Regeneration queued."); }}>Regenerate dataset + retrain</button>
        </p>
        <State loading={jobs.loading && !jobs.data} error={jobs.error}>
          <div className="scroll"><table><thead><tr><th>Kind</th><th>Status</th><th>Created</th><th>Finished</th><th>Log tail</th></tr></thead><tbody>
            {jobs.data?.items.map((j) => (
              <tr key={j.id}><td>{j.kind}</td><td><span className="tag">{j.status}{j.error_code ? ` (${j.error_code})` : ""}</span></td><td>{when(j.created_at)}</td><td>{when(j.finished_at)}</td>
                <td><pre style={{ margin: 0, maxHeight: 90, overflow: "auto", fontSize: 11, whiteSpace: "pre-wrap" }}>{(j.log_tail ?? "").split("\n").slice(-6).join("\n")}</pre></td></tr>))}
            {jobs.data?.items.length === 0 && <tr><td colSpan={5}>No jobs yet.</td></tr>}
          </tbody></table></div>
        </State>
      </Card>
      <Card title="Model promotion" note="Promotion is an audited administrator action. A model with no feasible threshold cannot be promoted; the artifact checksum and feature contract are verified first.">
        <State loading={run.loading && !run.data} error={run.error}>
          <p className="small">Currently promoted: <strong>{current ?? "none"}</strong> · latest run champion: <strong>{run.data?.champion ?? "none"}</strong></p>
          <label>Reason <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why this change?" style={{ width: 280 }} /></label>
          <div className="scroll"><table><thead><tr><th>Model</th><th className="n">Test AP</th><th>Threshold</th><th></th></tr></thead><tbody>
            {run.data?.models.map((m) => (
              <tr key={m.family}><td>{m.label}{m.family === current ? <span className="tag"> active</span> : null}</td>
                <td className="n">{m.test.average_precision?.toFixed(3) ?? "n/a"}</td>
                <td>{m.threshold == null ? "constraints unmet" : m.threshold.toFixed(3)}</td>
                <td><button disabled={m.family === current || m.threshold == null || reason.length < 3}
                  onClick={() => act(() => api(`/ml/models/${m.family}/promote`, { method: "POST", body: JSON.stringify({ reason, expected_current: current }) }), `Promoted ${m.label}.`)}>Promote</button></td></tr>))}
          </tbody></table></div>
          <p><button disabled={(promos.data?.items.length ?? 0) < 2 || reason.length < 3}
            onClick={() => act(() => api("/ml/models/rollback", { method: "POST", body: JSON.stringify({ reason, expected_current: current }) }), "Rolled back to the previous version.")}>Roll back to previous</button></p>
          <h2>History</h2>
          <table><thead><tr><th>When</th><th>Action</th><th>Model</th><th>Reason</th></tr></thead><tbody>
            {promos.data?.items.map((p) => <tr key={p.id}><td>{when(p.created_at)}</td><td>{p.kind}</td><td>{p.family}</td><td>{p.reason}</td></tr>)}
          </tbody></table>
        </State>
      </Card>
    </>
  );
}

export default function Ops() {
  return <RoleGate allow={["admin"]}><OpsInner /></RoleGate>;
}
