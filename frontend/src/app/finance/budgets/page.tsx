"use client";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { MetricCard, Progress, fmt, useFin, type Explain, type Metric } from "@/lib/fin";
import { Card, PageHead, State } from "@/components/ui";

type Row = { category: string; label: string; budget: string; spent: string; remaining: string; used_pct: number | null; status: "ok" | "near" | "over"; explain: Explain };
type R = { month: string; label: string; rows: Row[]; unbudgeted: { category: string; label: string; net: string }[];
  summary: { total_budget: string; total_spent: string; used_pct: number | null; n_over: number; n_near: number; n_ok: number }; explain: Explain };

export default function Budgets() {
  const { cid, month, tick, refresh, explain, isStaff } = useFin();
  const r = useApi<R>(month ? `/finance/budgets?customer_id=${cid}&month=${month}` : null, [tick]);
  const [edit, setEdit] = useState<{ category: string; value: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const d = r.data;
  const save = async () => {
    if (!edit || !month) return;
    setErr(null);
    try { await api("/finance/budgets", { method: "PUT", body: JSON.stringify({ month, category: edit.category, amount: edit.value }) }); setEdit(null); refresh(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not save"); }
  };
  const sum: Metric | null = d ? { key: "budget", label: "Total budget used", kind: "pct", value: d.summary.used_pct, explain: d.explain,
    sub: `${inr(d.summary.total_spent)} of ${inr(d.summary.total_budget)}`, tone: "blue" } : null;
  return (
    <>
      <PageHead eyebrow="My money" title="Budgets">Monthly limits per category with alerts at 80% (amber) and 100% (red). Click a row for the working.</PageHead>
      <State loading={r.loading || !month} error={r.error}>
        {d && sum && (
          <>
            <div className="stats">
              <MetricCard m={sum} />
              <div className="stat"><div className="lab">Over budget</div><div className="big">{d.summary.n_over}</div><div className="sub">categories at or above 100%</div></div>
              <div className="stat"><div className="lab">Near the limit</div><div className="big">{d.summary.n_near}</div><div className="sub">categories between 80% and 100%</div></div>
              <div className="stat"><div className="lab">On track</div><div className="big">{d.summary.n_ok}</div><div className="sub">categories under 80%</div></div>
            </div>
            {err && <p className="note err" role="alert">{err}</p>}
            <Card title={`Budgets · ${d.label}`}>
              <div className="scroll"><table>
                <thead><tr><th>Category</th><th style={{ width: "26%" }}>Used</th><th className="n">Spent</th><th className="n">Budget</th><th className="n">Remaining</th><th>Status</th>{!isStaff && <th />}</tr></thead>
                <tbody>
                  {d.rows.map((x) => (
                    <tr key={x.category}>
                      <td><button className="linkish" onClick={() => explain({ title: `${x.label} budget`, value: fmt("pct", x.used_pct), explain: x.explain })}>{x.label}</button></td>
                      <td><Progress pct={x.used_pct} status={x.status} /><span className="hint">{fmt("pct", x.used_pct)}</span></td>
                      <td className="n">{inr(x.spent)}</td>
                      <td className="n">{edit?.category === x.category ? (
                        <input aria-label={`New budget for ${x.label}`} inputMode="decimal" value={edit.value} onChange={(e) => setEdit({ category: x.category, value: e.target.value })} style={{ width: 100 }} />
                      ) : inr(x.budget)}</td>
                      <td className="n">{inr(x.remaining)}</td>
                      <td><span className={`badge2 ${x.status === "over" ? "bad" : x.status === "near" ? "warn" : "good"}`}>{x.status === "over" ? "Over budget" : x.status === "near" ? "Near limit" : "On track"}</span></td>
                      {!isStaff && <td>{edit?.category === x.category ? <button onClick={save}>Save</button> : <button onClick={() => setEdit({ category: x.category, value: String(Number(x.budget) / 100) })}>Edit</button>}</td>}
                    </tr>))}
                </tbody>
              </table></div>
            </Card>
            {d.unbudgeted.length > 0 && (
              <Card title="Spending without a budget" note="Set a budget for the categories that matter to you.">
                <table><tbody>{d.unbudgeted.map((u) => (
                  <tr key={u.category}><td>{u.label}</td><td className="n">{inr(u.net)}</td>
                    {!isStaff && <td className="n"><button onClick={() => setEdit({ category: u.category, value: String(Math.round(Number(u.net) / 100 / 100) * 100) })}>Set budget</button></td>}</tr>))}</tbody></table>
                {edit && !d.rows.some((x) => x.category === edit.category) && (
                  <p><input aria-label="Budget amount" inputMode="decimal" value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} style={{ width: 120 }} /> <button onClick={save}>Save budget</button> <button onClick={() => setEdit(null)}>Cancel</button></p>)}
              </Card>
            )}
          </>
        )}
      </State>
    </>
  );
}
