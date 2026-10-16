"use client";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { MetricCard, useFin, type Metric } from "@/lib/fin";
import { PageHead, State } from "@/components/ui";

type R = { fy: string; months_with_data: number; metrics: Metric[]; rent_paid: string; tds: string; pf: string; gross: string; net: string; note: string };

export default function Tax() {
  const { cid, tick } = useFin();
  const r = useApi<R>(`/finance/tax?customer_id=${cid}`, [tick]);
  const d = r.data;
  return (
    <>
      <PageHead eyebrow="My money" title="Tax summary">Year-end view: gross income, tax already deducted, deductions you can claim, and a rough tax estimate. Click a card for the working.</PageHead>
      <State loading={r.loading} error={r.error}>
        {d && (
          <>
            <p className="note">Financial year <strong>{d.fy}</strong> · {d.months_with_data} of 12 months of data{d.months_with_data < 12 ? " (partial year, estimate is annualised)" : ""}. {d.note}</p>
            <div className="stats">{d.metrics.map((m) => <MetricCard key={m.key} m={m} />)}</div>
            <p className="hint">Rent paid this year: {inr(d.rent_paid)} (useful for an HRA claim). Net pay received: {inr(d.net)}.</p>
          </>
        )}
      </State>
    </>
  );
}
