"use client";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { MetricCard, useFin, type Explain, type Metric } from "@/lib/fin";
import { PairBars } from "@/components/FinCharts";
import { Card, PageHead, State } from "@/components/ui";

type R = { metrics: Metric[]; by_month: { label: string; net: string; gross: string }[];
  types: { income_type: string; label: string; class: string; net: string; gross: string; deductions: string; count: number; explain: Explain }[];
  profile: { income_profile?: string } };
const PROFILE: Record<string, string> = { salaried: "Salaried", freelancer: "Freelancer / consultant", business: "Business owner", student: "Student (stipend)", gig: "Gig worker" };

export default function Income() {
  const { cid, month, tick, explain } = useFin();
  const r = useApi<R>(month ? `/finance/income?customer_id=${cid}&month=${month}` : null, [tick]);
  const d = r.data;
  return (
    <>
      <PageHead eyebrow="My money" title="Income">Every way money comes in, with gross vs net (what was earned vs what reached you) and a monthly average so irregular months do not mislead. Click a card or row.</PageHead>
      <State loading={r.loading || !month} error={r.error}>
        {d && (
          <>
            <p className="hint">Income profile: <strong>{PROFILE[d.profile.income_profile ?? ""] ?? d.profile.income_profile}</strong> · last 12 months ending at the selected month.</p>
            <div className="stats">{d.metrics.map((m) => <MetricCard key={m.key} m={m} />)}</div>
            <div className="grid">
              <Card title="Gross vs net by month" note="Blue = gross (before deductions). Coral = net (reached your account).">
                <PairBars aName="Gross" bName="Net" pts={d.by_month.map((b) => ({ label: b.label, a: Number(b.gross) / 100, b: Number(b.net) / 100 }))} />
              </Card>
              <Card title="Income by source (12 months)">
                <div className="scroll"><table>
                  <thead><tr><th>Source</th><th>Class</th><th className="n">Gross</th><th className="n">Net</th></tr></thead>
                  <tbody>{d.types.map((t) => (
                    <tr key={t.income_type} className="row-btn" tabIndex={0} onClick={() => explain({ title: t.label, value: inr(t.net), explain: t.explain })}
                      onKeyDown={(e) => e.key === "Enter" && explain({ title: t.label, value: inr(t.net), explain: t.explain })}>
                      <td><strong>{t.label}</strong><div className="hint">{t.count} payments</div></td><td><span className="badge2">{t.class}</span></td>
                      <td className="n">{inr(t.gross)}</td><td className="n"><strong>{inr(t.net)}</strong></td></tr>))}</tbody>
                </table></div>
              </Card>
            </div>
          </>
        )}
      </State>
    </>
  );
}
