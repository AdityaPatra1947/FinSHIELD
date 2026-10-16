"use client";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { ExplainLink, fmt, useFin, type Explain } from "@/lib/fin";
import { Line } from "@/components/FinCharts";
import { Card, PageHead, State } from "@/components/ui";

type R = {
  anomalies: { items: { id: number; when: string; category: string; merchant: string | null; amount: string; typical: string; times_typical: number | null; score: number }[]; explain: Explain };
  forecast: { label: string; amount: string; fixed: string; variable: string; explain: Explain };
  budget_overshoot: { items: { category: string; label: string; budget: string; spent: string; projected: string; will_overshoot: boolean }[]; explain: Explain };
  category_trends: { category: string; label: string; net: string; vs_prev_pct: number | null; vs_prev_reason: string | null; explain: Explain }[];
  savings_series: { label: string; rate: number | null }[];
};

export default function Insights() {
  const { cid, month, tick, explain } = useFin();
  const r = useApi<R>(month ? `/finance/insights?customer_id=${cid}&month=${month}` : null, [tick]);
  const d = r.data;
  return (
    <>
      <PageHead eyebrow="My money" title="Insights">A forecast for next month, budgets you are on pace to break, and purchases that look unusual for you. Simple, transparent rules; click for the working.</PageHead>
      <State loading={r.loading || !month} error={r.error}>
        {d && (
          <>
            <div className="stats">
              <button className="stat stat-btn blue" onClick={() => explain({ title: `Forecast: ${d.forecast.label}`, value: inr(d.forecast.amount), explain: d.forecast.explain })}>
                <div className="lab">Forecast spending · {d.forecast.label}<span className="info">i</span></div><div className="big num">{inr(d.forecast.amount)}</div>
                <div className="sub">fixed {inr(d.forecast.fixed)} + variable {inr(d.forecast.variable)}</div></button>
              <button className="stat stat-btn" onClick={() => explain({ title: "Budget overshoot prediction", explain: d.budget_overshoot.explain })}>
                <div className="lab">Budgets at risk<span className="info">i</span></div><div className="big">{d.budget_overshoot.items.filter((x) => x.will_overshoot).length}</div><div className="sub">on pace to exceed their limit</div></button>
              <button className="stat stat-btn coral" onClick={() => explain({ title: "Unusual purchases", explain: d.anomalies.explain })}>
                <div className="lab">Unusual purchases<span className="info">i</span></div><div className="big">{d.anomalies.items.length}</div><div className="sub">in the last 90 days</div></button>
            </div>
            <div className="grid">
              <Card title="Savings rate over time"><Line unit="pct" color="#3f8f7a" pts={d.savings_series.map((s) => ({ label: s.label, v: s.rate }))} /></Card>
              <Card title="Budgets on pace to overshoot" note="Projected month-end = spent so far ÷ days elapsed × days in month.">
                <table><thead><tr><th>Category</th><th className="n">Budget</th><th className="n">Projected</th><th /></tr></thead><tbody>
                  {d.budget_overshoot.items.slice(0, 8).map((b) => (
                    <tr key={b.category}><td>{b.label}</td><td className="n">{inr(b.budget)}</td><td className="n">{inr(b.projected)}</td>
                      <td><span className={`badge2 ${b.will_overshoot ? "bad" : "good"}`}>{b.will_overshoot ? "will overshoot" : "on track"}</span></td></tr>))}
                </tbody></table>
                <p><ExplainLink title="Budget overshoot prediction" explain={d.budget_overshoot.explain}>How is this predicted?</ExplainLink></p>
              </Card>
            </div>
            <Card title="Unusual purchases (last 90 days)" note="Compared with your own history in the same category. A prompt to double-check, not an accusation.">
              {d.anomalies.items.length === 0 ? <p>Nothing unusual. All recent purchases are within your normal range.</p> : (
                <div className="scroll"><table><thead><tr><th>Date</th><th>Where</th><th>Category</th><th className="n">Amount</th><th className="n">Typical</th><th className="n">× typical</th></tr></thead>
                  <tbody>{d.anomalies.items.map((a) => (
                    <tr key={a.id}><td>{a.when}</td><td>{a.merchant ?? "—"}</td><td>{a.category}</td><td className="n"><strong>{inr(a.amount)}</strong></td><td className="n">{inr(a.typical)}</td>
                      <td className="n">{a.times_typical == null ? "—" : `${a.times_typical}×`}</td></tr>))}</tbody></table></div>)}
              <p><ExplainLink title="Unusual purchases" explain={d.anomalies.explain}>How are these found?</ExplainLink></p>
            </Card>
            <Card title="Biggest categories this month vs last month">
              <table><tbody>{d.category_trends.map((c) => (
                <tr key={c.category} className="row-btn" tabIndex={0} onClick={() => explain({ title: c.label, value: inr(c.net), explain: c.explain })}>
                  <td>{c.label}</td><td className="n"><strong>{inr(c.net)}</strong></td>
                  <td className="n">{c.vs_prev_pct == null ? <span className="hint">{c.vs_prev_reason}</span> : <span className={c.vs_prev_pct > 0 ? "amt-out" : "amt-in"}>{c.vs_prev_pct > 0 ? "▲" : "▼"} {fmt("pct", Math.abs(c.vs_prev_pct))}</span>}</td></tr>))}</tbody></table>
            </Card>
          </>
        )}
      </State>
    </>
  );
}
