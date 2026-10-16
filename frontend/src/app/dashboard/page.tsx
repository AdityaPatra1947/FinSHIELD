"use client";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { Bars, HBars } from "@/components/Charts";
import { Card, CustomerPicker, PageHead, Stat, State, useCid } from "@/components/ui";

type Report = {
  gross_spending_minor: string; expense_credits_minor: string; net_spending_minor: string;
  recognized_income_minor: string; budget_surplus_minor: string; budget_surplus_rate: number | null;
  budget_surplus_rate_reason: string | null; unclassified_outflow_minor: string; unclassified_inflow_minor: string;
  calculation_version: string; net_change_vs_prior_period_percent: number | null; net_change_reason: string | null;
  categories: { category: string; gross_minor: string; credits_minor: string; net_minor: string; gross_share: number | null }[];
  cash: { withdrawals_minor: string; cash_purchases_minor: string; expected_closing_minor: string };
};
type Trend = { items: { bucket: string; net_spending_minor: string; recognized_income_minor: string }[] };

export default function Overview() {
  const [picked, setCid] = useState(1);
  const cid = useCid(picked);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const qs = `customer_id=${cid}${from ? `&start=${from}` : ""}${to ? `&end=${to}` : ""}`;
  const r = useApi<Report>(`/reports/spending?${qs}`);
  const t = useApi<Trend>(`/reports/trends?${qs}`);
  return (
    <>
      <PageHead eyebrow="Workspace" title="Spending overview">
        Income, gross and net spending computed once on the server from the posted ledger. Transfers, cash withdrawals, card repayments and investments never count as spending.
      </PageHead>
      <div className="toolbar">
        <CustomerPicker value={picked} onChange={setCid} />
        <label>From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>To (exclusive)<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <span className="muted small" style={{ alignSelf: "center" }}>Default: last 12 calendar months · Asia/Kolkata · max 366 days</span>
      </div>
      <State loading={r.loading} error={r.error}>
        {r.data && (
          <>
            <div className="stats">
              <Stat tone="blue" label="Net spending" value={inr(r.data.net_spending_minor)}
                sub={r.data.net_change_vs_prior_period_percent == null ? `Vs prior period: Not available (${r.data.net_change_reason})` : `${pct(r.data.net_change_vs_prior_period_percent)} vs prior period`} />
              <Stat label="Recognized income" value={inr(r.data.recognized_income_minor)} />
              <Stat label="Gross spending" value={inr(r.data.gross_spending_minor)} />
              <Stat label="Expense credits" value={inr(r.data.expense_credits_minor)} sub="Refunds and reversals" />
              <Stat tone="coral" label="Budget surplus" value={inr(r.data.budget_surplus_minor)}
                sub={r.data.budget_surplus_rate == null ? `Rate: Not available (${r.data.budget_surplus_rate_reason})` : `${pct(r.data.budget_surplus_rate)} of income`} />
              <Stat label="Unresolved transfers out" value={inr(r.data.unclassified_outflow_minor)} sub="P2P transfers awaiting classification" />
            </div>
            <div className="grid">
              <Card title="Net spending by month" note="Same period scope as the totals above.">
                <State loading={t.loading} error={t.error}>
                  {t.data && <Bars items={t.data.items.map((i) => ({ label: i.bucket, value: Number(BigInt(i.net_spending_minor) / 100n), sub: inr(i.net_spending_minor) }))} />}
                </State>
              </Card>
              <Card title="Net spending by category" note="Negative nets stay visible (coral).">
                <HBars items={r.data.categories.map((c) => ({ label: c.category, value: Number(BigInt(c.net_minor) / 100n), text: inr(c.net_minor) }))} />
              </Card>
              <Card title="Cash wallet" note="Expected balance only: no observed count, so no untracked spending is claimed. Suggestions never post automatically.">
                <div className="hb" style={{ gridTemplateColumns: "1fr auto" }}><span>Withdrawn into wallet</span><span className="tx">{inr(r.data.cash.withdrawals_minor)}</span></div>
                <div className="hb" style={{ gridTemplateColumns: "1fr auto" }}><span>Cash purchases</span><span className="tx">{inr(r.data.cash.cash_purchases_minor)}</span></div>
                <div className="hb" style={{ gridTemplateColumns: "1fr auto", borderTop: "1px solid var(--line)", paddingTop: 10, fontWeight: 700 }}><span>Expected closing cash</span><span className="tx">{inr(r.data.cash.expected_closing_minor)}</span></div>
              </Card>
            </div>
            <p className="muted small">Calculation {r.data.calculation_version}.</p>
          </>
        )}
      </State>
    </>
  );
}
