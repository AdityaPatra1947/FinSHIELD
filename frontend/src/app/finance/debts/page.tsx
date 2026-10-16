"use client";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { Modal, Progress, useFin, type Explain } from "@/lib/fin";
import { Card, PageHead, State } from "@/components/ui";

type Loan = { loan_id: number; name: string; kind: string; lender: string; rate_pct: number; principal: string; emi: string; tenure_months: number; paid: number; left: number;
  outstanding: string; payoff_date: string; remaining_interest: string; progress_pct: number | null; explain: Explain };
type CardT = { account_id: number; name: string; institution: string; owed: string; limit: string; utilisation: number | null; apr_pct: number; min_due: string; due_day: number };
type Sched = { name: string; paid: number; rows: { n: number; date: string; emi: string; principal: string; interest: string; balance: string }[] };

function Schedule({ id, cid, onClose }: { id: number; cid: number; onClose: () => void }) {
  const r = useApi<Sched>(`/finance/loans/${id}/schedule?customer_id=${cid}`);
  return (
    <Modal title={r.data ? `${r.data.name} — repayment schedule` : "Repayment schedule"} onClose={onClose}>
      <State loading={r.loading} error={r.error}>
        <p className="hint">Interest = balance × rate ÷ 12. Principal = EMI − interest. Rows up to the last EMI already paid are history.</p>
        <div className="scroll" style={{ maxHeight: "55vh" }}><table>
          <thead><tr><th>#</th><th>Date</th><th className="n">EMI</th><th className="n">Principal</th><th className="n">Interest</th><th className="n">Balance</th></tr></thead>
          <tbody>{r.data?.rows.map((x) => (
            <tr key={x.n} style={{ opacity: x.n <= (r.data?.paid ?? 0) ? 0.55 : 1 }}><td>{x.n}</td><td>{x.date}</td><td className="n">{inr(x.emi)}</td>
              <td className="n">{inr(x.principal)}</td><td className="n">{inr(x.interest)}</td><td className="n">{inr(x.balance)}</td></tr>))}</tbody>
        </table></div>
      </State>
    </Modal>
  );
}

export default function Debts() {
  const { cid, tick, explain } = useFin();
  const r = useApi<{ loans: Loan[]; cards: CardT[]; total_owed: string; monthly_emi: string }>(`/finance/debts?customer_id=${cid}`, [tick]);
  const [sched, setSched] = useState<number | null>(null);
  return (
    <>
      <PageHead eyebrow="My money" title="Debts">Loans with EMI schedules, interest and payoff dates, plus credit-card dues. Click a loan for the amortisation working.</PageHead>
      <State loading={r.loading} error={r.error}>
        {r.data && (
          <>
            <div className="stats">
              <div className="stat blue"><div className="lab">Total owed</div><div className="big num">{inr(r.data.total_owed)}</div><div className="sub">loans + credit cards</div></div>
              <div className="stat"><div className="lab">Monthly EMIs</div><div className="big num">{inr(r.data.monthly_emi)}</div></div>
            </div>
            {r.data.loans.length === 0 && <p className="note">No active loans. Debt-free on the loan side.</p>}
            <div className="cards">
              {r.data.loans.map((l) => (
                <div key={l.loan_id} className="cardbtn" style={{ cursor: "default" }}>
                  <button className="linkish t" onClick={() => explain({ title: l.name, value: inr(l.outstanding), explain: l.explain })}>{l.name}</button>
                  <span className="hint"> · {l.lender} · {l.rate_pct ? `${l.rate_pct}% p.a.` : "0% (no-cost EMI)"}</span>
                  <div className="big2">{inr(l.outstanding)} <span className="hint">still owed</span></div>
                  <Progress pct={l.progress_pct} />
                  <div className="hint">EMI {inr(l.emi)} · {l.paid} of {l.tenure_months} paid · last EMI {l.payoff_date}</div>
                  <div className="hint">Interest still to pay ≈ {inr(l.remaining_interest)}</div>
                  <p style={{ margin: "10px 0 0" }}><button onClick={() => setSched(l.loan_id)}>View schedule</button></p>
                </div>))}
            </div>
            {r.data.cards.length > 0 && (
              <Card title="Credit cards">
                <table><thead><tr><th>Card</th><th className="n">Owed</th><th className="n">Limit</th><th className="n">Utilisation</th><th className="n">Min due (5%)</th><th className="n">APR</th></tr></thead>
                  <tbody>{r.data.cards.map((c) => (
                    <tr key={c.account_id}><td>{c.name} <span className="hint">· {c.institution}</span></td><td className="n">{inr(c.owed)}</td><td className="n">{inr(c.limit)}</td>
                      <td className="n"><span className={`badge2 ${(c.utilisation ?? 0) > 50 ? "bad" : (c.utilisation ?? 0) > 30 ? "warn" : "good"}`}>{c.utilisation == null ? "n/a" : `${c.utilisation.toFixed(0)}%`}</span></td>
                      <td className="n">{inr(c.min_due)}</td><td className="n">{c.apr_pct}%</td></tr>))}</tbody></table>
                <p className="hint">Pay the full amount before the due date (around the {r.data.cards[0].due_day}th) to avoid interest. Keep utilisation under 30%.</p>
              </Card>)}
          </>
        )}
      </State>
      {sched !== null && <Schedule id={sched} cid={cid} onClose={() => setSched(null)} />}
    </>
  );
}
