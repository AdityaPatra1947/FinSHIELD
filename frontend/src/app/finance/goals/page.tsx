"use client";
import { useState, type FormEvent } from "react";
import { api, useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { Progress, useFin, type Explain } from "@/lib/fin";
import { Card, PageHead, State } from "@/components/ui";

type Goal = { goal_id: number; name: string; kind: string; target: string; saved: string; remaining: string; deadline: string; months_left: number;
  monthly_needed: string; progress_pct: number | null; linked: boolean; explain: Explain };

export default function Goals() {
  const { cid, tick, refresh, explain, isStaff } = useFin();
  const r = useApi<{ goals: Goal[] }>(`/finance/goals?customer_id=${cid}`, [tick]);
  const [form, setForm] = useState({ name: "", target: "", saved: "0", deadline: "" });
  const [amt, setAmt] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(null);
    try { await fn(); setMsg({ ok: true, t: ok }); refresh(); } catch (e) { setMsg({ ok: false, t: e instanceof Error ? e.message : "Failed" }); }
  };
  const create = (e: FormEvent) => { e.preventDefault(); run(() => api("/finance/goals", { method: "POST", body: JSON.stringify({ ...form, kind: "custom" }) }), "Goal created."); };
  return (
    <>
      <PageHead eyebrow="My money" title="Goals">Emergency fund, a laptop, a trip: each with a target, a deadline and the monthly saving needed. Click a goal for the working.</PageHead>
      {msg && <p className={`note${msg.ok ? "" : " err"}`} role={msg.ok ? "status" : "alert"}>{msg.t}</p>}
      <State loading={r.loading} error={r.error}>
        <div className="cards">
          {r.data?.goals.map((g) => (
            <div key={g.goal_id} className="cardbtn" style={{ cursor: "default" }}>
              <button className="linkish t" onClick={() => explain({ title: g.name, value: `${g.progress_pct?.toFixed(0)}% done`, explain: g.explain })}>{g.name}</button>
              <div className="big2">{inr(g.saved)} <span className="hint">of {inr(g.target)}</span></div>
              <Progress pct={g.progress_pct} status={(g.progress_pct ?? 0) >= 100 ? "ok" : "ok"} />
              <div className="hint">By {g.deadline} · {g.months_left} months left · save <strong>{inr(g.monthly_needed)}</strong>/month</div>
              {g.linked ? <div className="hint">Linked to your savings account balance.</div> : !isStaff && (
                <p style={{ margin: "10px 0 0", display: "flex", gap: 6 }}>
                  <input aria-label={`Add to ${g.name}`} placeholder="₹ add" inputMode="decimal" value={amt[g.goal_id] ?? ""} onChange={(e) => setAmt({ ...amt, [g.goal_id]: e.target.value })} style={{ width: 110 }} />
                  <button onClick={() => run(() => api(`/finance/goals/${g.goal_id}/contribute`, { method: "POST", body: JSON.stringify({ amount: amt[g.goal_id] }) }), "Contribution added.")}>Add</button>
                </p>)}
            </div>))}
        </div>
      </State>
      {!isStaff && (
        <Card title="New goal">
          <form onSubmit={create} className="formgrid">
            <label>Name<input required maxLength={60} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label>Target (₹)<input required inputMode="decimal" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} /></label>
            <label>Already saved (₹)<input inputMode="decimal" value={form.saved} onChange={(e) => setForm({ ...form, saved: e.target.value })} /></label>
            <label>Deadline<input type="date" required value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} /></label>
            <label>&nbsp;<button type="submit">Create goal</button></label>
          </form>
        </Card>)}
    </>
  );
}
