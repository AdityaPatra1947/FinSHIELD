"use client";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { useFin, type Explain } from "@/lib/fin";
import { Card, PageHead, State } from "@/components/ui";

type Item = { recurring_id: number; name: string; kind: string; amount: string; frequency: string; direction: string; category_label: string | null; subcategory_label: string | null;
  last_paid_ts: number | null; next_due_ts: number | null };
type R = { items: Item[]; due_next_30_days: { count: number; amount: string }; monthly_commitments: string; monthly_recurring_income: string;
  subscriptions: { count: number; monthly: string; annual: string }; explain: Explain };
const KIND: Record<string, string> = { income: "Income", rent: "Rent", bill: "Bills", subscription: "Subscriptions", emi: "EMIs", sip: "SIP / investments", insurance: "Insurance" };
const date = (ts: number | null) => (ts ? new Date(ts * 1000).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—");

export default function Recurring() {
  const { cid, tick, explain } = useFin();
  const r = useApi<R>(`/finance/recurring?customer_id=${cid}`, [tick]);
  const d = r.data;
  const groups = d ? Object.keys(KIND).map((k) => ({ k, rows: d.items.filter((i) => i.kind === k) })).filter((g) => g.rows.length) : [];
  return (
    <>
      <PageHead eyebrow="My money" title="Recurring">Salary, rent, bills, subscriptions, EMIs, SIPs and insurance with next due dates. Spot subscriptions you forgot about.</PageHead>
      <State loading={r.loading} error={r.error}>
        {d && (
          <>
            <div className="stats">
              <button className="stat stat-btn blue" onClick={() => explain({ title: "Monthly commitments", value: inr(d.monthly_commitments), explain: d.explain })}>
                <div className="lab">Monthly commitments<span className="info">i</span></div><div className="big num">{inr(d.monthly_commitments)}</div><div className="sub">bills, EMIs, rent, SIPs (annual items ÷ 12)</div></button>
              <div className="stat"><div className="lab">Due in the next 30 days</div><div className="big num">{inr(d.due_next_30_days.amount)}</div><div className="sub">{d.due_next_30_days.count} payments</div></div>
              <div className="stat coral"><div className="lab">Subscriptions</div><div className="big num">{inr(d.subscriptions.annual)}<span style={{ fontSize: 12 }}> /year</span></div><div className="sub">{d.subscriptions.count} active · {inr(d.subscriptions.monthly)} per month</div></div>
              <div className="stat"><div className="lab">Recurring income</div><div className="big num">{inr(d.monthly_recurring_income)}</div><div className="sub">per month</div></div>
            </div>
            {groups.map((g) => (
              <Card key={g.k} title={KIND[g.k]}>
                <div className="scroll"><table>
                  <thead><tr><th>Name</th><th>Category</th><th>Repeats</th><th>Last paid</th><th>Next due</th><th className="n">Amount</th></tr></thead>
                  <tbody>{g.rows.map((i) => (
                    <tr key={i.recurring_id}><td><strong>{i.name}</strong></td><td>{i.category_label ?? "—"}<div className="hint">{i.subcategory_label ?? ""}</div></td>
                      <td>{i.frequency}</td><td>{date(i.last_paid_ts)}</td><td>{date(i.next_due_ts)}</td>
                      <td className={`n ${i.direction === "credit" ? "amt-in" : "amt-out"}`}>{i.direction === "credit" ? "+" : "−"}{inr(i.amount)}</td></tr>))}</tbody>
                </table></div>
              </Card>))}
          </>
        )}
      </State>
    </>
  );
}
