"use client";
import { useApi } from "@/lib/api";
import { RoleGate } from "@/lib/auth";
import { inr, modelName } from "@/lib/format";
import { Bars, HBars } from "@/components/Charts";
import { Card, PageHead, Stat, State } from "@/components/ui";

type Ov = {
  totals: { customers: number; transactions: number; eligible_decisions: number; fraud_labeled: number; scored_decisions: number };
  users_by_role: Record<string, number>;
  monthly: { bucket: string; net_spending_minor: string; recognized_income_minor: string }[];
  fraud_monthly: { bucket: string; fraud: number; decisions: number }[];
  fraud_by_channel: { channel: string; fraud: number; decisions: number }[];
  categories: { category: string; gross_minor: string }[];
  purpose_counts: Record<string, number>;
  cluster_sizes: { cluster_id: number; name: string; size: number }[];
  model_summary: { family: string; label: string; ap: number | null; threshold_status: string }[];
  promoted_family: string | null; champion: string | null; alert_states: Record<string, number>;
};
const big = (m: string) => Number(BigInt(m) / 100n);

function OrgInner() {
  const r = useApi<Ov>("/admin/overview");
  return (
    <>
      <PageHead eyebrow="Insights" title="Organization overview">All customers together: spending, synthetic fraud labels, model status and segments.</PageHead>
      <State loading={r.loading} error={r.error}>
        {r.data && (() => {
          const o = r.data;
          return (
            <>
              <div className="stats">
                <Stat tone="blue" label="Customers" value={o.totals.customers.toLocaleString()} sub="synthetic" />
                <Stat label="Ledger transactions" value={o.totals.transactions.toLocaleString()} />
                <Stat label="Fraud-eligible decisions" value={o.totals.eligible_decisions.toLocaleString()} />
                <Stat label="Synthetic fraud labels" value={o.totals.fraud_labeled.toLocaleString()} sub={`${((100 * o.totals.fraud_labeled) / o.totals.eligible_decisions).toFixed(2)}% prevalence`} />
                <Stat label="Scored (test period)" value={o.totals.scored_decisions.toLocaleString()} />
                <Stat tone="coral" label="Promoted model" value={modelName(o.promoted_family)} sub={`Champion: ${modelName(o.champion)}`} />
              </div>
              <div className="grid">
                <Card title="Net spending by month (all customers)"><Bars items={o.monthly.map((m) => ({ label: m.bucket, value: big(m.net_spending_minor), sub: inr(m.net_spending_minor) }))} /></Card>
                <Card title="Recognized income by month (all customers)"><Bars items={o.monthly.map((m) => ({ label: m.bucket, value: big(m.recognized_income_minor), sub: inr(m.recognized_income_minor) }))} /></Card>
                <Card title="Fraud-labeled decisions by month" note="Synthetic labels; one decision per eligible posted digital debit.">
                  <Bars items={o.fraud_monthly.map((m) => ({ label: m.bucket, value: m.fraud, sub: `${m.fraud} of ${m.decisions}` }))} />
                </Card>
              </div>
              <div className="grid">
                <Card title="Gross spending by category"><HBars items={o.categories.map((c) => ({ label: c.category, value: big(c.gross_minor), text: inr(c.gross_minor) }))} /></Card>
                <Card title="Fraud rate by channel" note="Fraud / decisions.">
                  <HBars items={o.fraud_by_channel.map((c) => ({ label: c.channel, value: (100 * c.fraud) / Math.max(c.decisions, 1), text: `${c.fraud}/${c.decisions}` }))} />
                </Card>
                <Card title="Customer segments (KMeans)">
                  {o.cluster_sizes.length ? <HBars items={o.cluster_sizes.map((c) => ({ label: `#${c.cluster_id}`, value: c.size, text: `${c.size} · ${c.name.slice(0, 24)}` }))} /> : <p>No clustering run yet.</p>}
                </Card>
              </div>
              <div className="grid">
                <Card title="Model families (test AP)" note="Exactly three supervised classifiers; AP is the primary metric.">
                  <HBars items={o.model_summary.map((m) => ({ label: m.label.slice(0, 14), value: m.ap ?? 0, text: `${m.ap?.toFixed(3) ?? "n/a"} · ${m.threshold_status}` }))} />
                </Card>
                <Card title="Alert review states"><p className="small">{Object.keys(o.alert_states).length ? Object.entries(o.alert_states).map(([k, v]) => `${k}: ${v}`).join(" · ") : "No alerts have been triaged yet (untouched alerts are open)."}</p></Card>
                <Card title="Transactions by purpose"><HBars items={Object.entries(o.purpose_counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k.slice(0, 16), value: v, text: v.toLocaleString() }))} /></Card>
              </div>
              <p className="muted small">Users: {Object.entries(o.users_by_role).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
            </>
          );
        })()}
      </State>
    </>
  );
}

export default function Org() {
  return <RoleGate allow={["analyst", "admin"]}><OrgInner /></RoleGate>;
}
