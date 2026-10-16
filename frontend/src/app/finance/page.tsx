"use client";
import Link from "next/link";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { ExplainLink, MetricCard, Progress, SplitBar, fmt, useFin, type Explain, type Metric } from "@/lib/fin";
import { Line, PairBars } from "@/components/FinCharts";
import { Card, PageHead, State } from "@/components/ui";

type Cat = { category: string; label: string; group: string; need_want: string | null; gross: string; credits: string; net: string; share_of_gross: number | null;
  count: number; vs_prev_pct: number | null; vs_prev_reason: string | null; vs_last_year_pct: number | null; vs_last_year_reason: string | null; explain: Explain };
type Ov = { month_label: string; metrics: Metric[]; split: Record<"needs" | "wants" | "savings", { amount: string; pct: number | null; benchmark: number }>;
  categories: Cat[]; series: { label: string; income: string | null; expenses: string | null; savings_rate: number | null; net_worth: string | null }[];
  budget_summary: { n_over: number; n_near: number; n_ok: number; total_budget: string; total_spent: string; used_pct: number | null };
  to_classify: { count: number; amount: string }; bracket: { label: string; emphasis: string[]; situation: string } };

const SIMPLE = ["net_spending", "money_left", "savings_rate", "safe_to_spend", "emergency_cover"];
const ADV = ["income", "gross_spending", "refunds", "net_spending", "money_left", "savings_rate", "burn_rate", "runway", "emergency_cover", "dti", "net_worth", "safe_to_spend"];

function CategoryExtra({ category }: { category: string }) {
  const { cid, month } = useFin();
  const r = useApi<{ subcategories: { label: string; net: string; count: number }[]; merchants: { merchant: string; total: string; count: number }[] }>(
    `/finance/category?customer_id=${cid}&month=${month}&category=${category}`);
  return (
    <>
      <h3>Inside this category</h3>
      <State loading={r.loading} error={r.error}>
        <table><thead><tr><th>Subcategory</th><th className="n">Net</th><th className="n">Count</th></tr></thead><tbody>
          {r.data?.subcategories.map((s) => <tr key={s.label}><td>{s.label}</td><td className="n">{inr(s.net)}</td><td className="n">{s.count}</td></tr>)}
        </tbody></table>
        <h3>Top places</h3>
        <table><tbody>{r.data?.merchants.map((m) => <tr key={m.merchant}><td>{m.merchant}</td><td className="n">{inr(m.total)}</td></tr>)}</tbody></table>
      </State>
    </>
  );
}

function Delta({ v, reason }: { v: number | null; reason: string | null }) {
  if (v === null) return <span className="hint" title={reason ?? undefined}>n/a</span>;
  return <span className={v > 0 ? "amt-out" : "amt-in"}>{v > 0 ? "▲" : "▼"} {Math.abs(v).toFixed(0)}%</span>;
}

export default function Overview() {
  const { cid, month, mode, tick, explain } = useFin();
  const r = useApi<Ov>(month ? `/finance/overview?customer_id=${cid}&month=${month}` : null, [tick]);
  const d = r.data;
  const keys = mode === "simple" ? SIMPLE : ADV;
  return (
    <>
      <PageHead eyebrow="My money" title="Overview">
        Click any number to see exactly how it is calculated, what goes in, and how to read it.
      </PageHead>
      <State loading={r.loading || !month} error={r.error}>
        {d && (
          <>
            {d.to_classify.count > 0 && (
              <p className="note">
                <strong>{d.to_classify.count} payments to other people ({inr(d.to_classify.amount)}) need a category.</strong> Until you classify them they are not
                counted as spending. <Link href="/finance/transactions?review=1">Review them →</Link>
              </p>
            )}
            <div className="stats">{keys.map((k) => { const m = d.metrics.find((x) => x.key === k); return m ? <MetricCard key={k} m={m} /> : null; })}</div>

            <div className="grid">
              <Card title={`Where ${d.month_label} went (needs / wants / savings)`}>
                <SplitBar parts={[
                  { label: "Needs", pct: d.split.needs.pct, color: "#226192" },
                  { label: "Wants", pct: d.split.wants.pct, color: "#EF8557" },
                  { label: "Savings", pct: d.split.savings.pct, color: "#3f8f7a" }]} />
                <p className="hint">Rule of thumb: 50% needs · 30% wants · 20% savings. Yours: {fmt("pct", d.split.needs.pct)} · {fmt("pct", d.split.wants.pct)} · {fmt("pct", d.split.savings.pct)}.</p>
                <p><ExplainLink title="Needs / wants / savings" value={inr(d.split.savings.amount)} explain={d.metrics.find((m) => m.key === "needs_wants_savings")!.explain}>How is this calculated?</ExplainLink></p>
              </Card>
              <Card title="Budgets this month">
                <Progress pct={d.budget_summary.used_pct} status={d.budget_summary.n_over ? "over" : d.budget_summary.n_near ? "near" : "ok"} />
                <p className="hint">{inr(d.budget_summary.total_spent)} of {inr(d.budget_summary.total_budget)} used · {d.budget_summary.n_over} over · {d.budget_summary.n_near} near the limit.</p>
                <Link href="/finance/budgets">Open budgets →</Link>
              </Card>
              {mode === "advanced" && (
                <Card title="Income vs expenses (12 months)">
                  <PairBars aName="Income" bName="Net spending" pts={d.series.map((s) => ({ label: s.label, a: s.income == null ? null : Number(s.income) / 100, b: s.expenses == null ? null : Number(s.expenses) / 100 }))} />
                </Card>
              )}
              {mode === "advanced" && (
                <Card title="Savings rate trend" note="(income − expenses) ÷ income each month">
                  <Line unit="pct" color="#3f8f7a" pts={d.series.map((s) => ({ label: s.label, v: s.savings_rate }))} />
                </Card>
              )}
              {mode === "advanced" && (
                <Card title="Net worth trend" note="assets − liabilities at each month end">
                  <Line pts={d.series.map((s) => ({ label: s.label, v: s.net_worth == null ? null : Number(s.net_worth) / 100 }))} />
                </Card>
              )}
            </div>

            <Card title={`Spending by category · ${d.month_label}`} note="Click a row to see the working, subcategories and top places.">
              <div className="scroll"><table>
                <thead><tr><th>Category</th><th>Type</th><th className="n">Gross</th><th className="n">Refunds</th><th className="n">Net</th><th className="n">Share</th>
                  <th className="n">vs last month</th><th className="n">vs last year</th></tr></thead>
                <tbody>
                  {d.categories.slice(0, mode === "simple" ? 6 : 99).map((c) => (
                    <tr key={c.category} className="row-btn" tabIndex={0}
                      onClick={() => explain({ title: c.label, value: inr(c.net), explain: c.explain, extra: <CategoryExtra category={c.category} /> })}
                      onKeyDown={(e) => e.key === "Enter" && explain({ title: c.label, value: inr(c.net), explain: c.explain, extra: <CategoryExtra category={c.category} /> })}>
                      <td><strong>{c.label}</strong></td>
                      <td>{c.need_want && <span className={`badge2 ${c.need_want === "need" || c.need_want === "financial" ? "need" : "want"}`}>{c.need_want === "financial" ? "need" : c.need_want}</span>}</td>
                      <td className="n">{inr(c.gross)}</td><td className="n">{inr(c.credits)}</td><td className="n"><strong>{inr(c.net)}</strong></td>
                      <td className="n">{c.share_of_gross == null ? "—" : `${c.share_of_gross.toFixed(0)}%`}</td>
                      <td className="n"><Delta v={c.vs_prev_pct} reason={c.vs_prev_reason} /></td>
                      <td className="n"><Delta v={c.vs_last_year_pct} reason={c.vs_last_year_reason} /></td>
                    </tr>))}
                </tbody>
              </table></div>
            </Card>
            {mode === "advanced" && d.bracket && (
              <Card title={`What matters at your income level (${d.bracket.label})`}>
                <p>{d.bracket.situation}</p>
                <div className="pills">{d.bracket.emphasis.map((e) => <span key={e} className="badge2">{e}</span>)}</div>
              </Card>
            )}
          </>
        )}
      </State>
    </>
  );
}
