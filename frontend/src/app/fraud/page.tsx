"use client";
import { RoleGate } from "@/lib/auth";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { inr, modelName } from "@/lib/format";
import { Card, PageHead, State } from "@/components/ui";

type Alert = { txn_id: number; customer: string; amount_minor: string; purpose: string; channel: string; occurred_at: string;
  probability: number; reasons: string[]; state: string; note: string | null; synthetic_label: number };
type Resp = { available: boolean; reason?: string; model?: string; threshold?: number; total?: number; items: Alert[]; note?: string };

function FraudInner() {
  const [page, setPage] = useState(1);
  const [bump, setBump] = useState(0);
  const r = useApi<Resp>(`/fraud/alerts?page=${page}&size=25&_=${bump}`);
  const set = async (id: number, state: string) => {
    await api(`/fraud/alerts/${id}`, { method: "PATCH", body: JSON.stringify({ state }) });
    setBump((b) => b + 1);
  };
  return (
    <>
      <PageHead eyebrow="Insights" title="Fraud review queue">Transactions the promoted model flagged in the locked test period. A score is an estimate for human review, never proof of fraud.</PageHead>
      <State loading={r.loading} error={r.error}>
        {r.data && !r.data.available && <Card title="No operational model"><p>{r.data.reason}</p></Card>}
        {r.data?.available && (
          <>
            <p>Model: <strong>{modelName(r.data.model)}</strong> · threshold {r.data.threshold?.toFixed(3)} · {r.data.total} alerts in the locked test period.
              <br /><span className="muted small">{r.data.note}</span></p>
            <div className="scroll"><table>
              <thead><tr><th>Txn</th><th>Customer</th><th>When (IST)</th><th>Type</th><th className="n">Amount</th><th className="n">Score</th><th>Contextual signals</th><th>Demo label</th><th>State</th></tr></thead>
              <tbody>{r.data.items.map((a) => (
                <tr key={a.txn_id}>
                  <td>{a.txn_id}</td><td>{a.customer}</td><td>{a.occurred_at.slice(0, 16).replace("T", " ")}</td>
                  <td>{a.purpose} / {a.channel}</td><td className="n">{inr(a.amount_minor)}</td>
                  <td className="n"><span className="risk-high">{a.probability.toFixed(3)}</span></td>
                  <td>{a.reasons.join("; ")}</td>
                  <td>{a.synthetic_label === 1 ? "fraud" : a.synthetic_label === 0 ? "legitimate" : "unknown"}</td>
                  <td><select aria-label={`State for transaction ${a.txn_id}`} value={a.state} onChange={(e) => set(a.txn_id, e.target.value)}>
                    <option>open</option><option>in_review</option><option>resolved</option></select></td>
                </tr>))}</tbody>
            </table></div>
            <p><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>{" "}
              <button disabled={page * 25 >= (r.data.total ?? 0)} onClick={() => setPage(page + 1)}>Next</button></p>
            <p className="muted small">The "demo label" is the synthetic ground truth, shown only because this is a demo. Reason codes are contextual signals, not causal proof. Alert state is stored locally; adjudicated labels are not written from here.</p>
          </>
        )}
      </State>
    </>
  );
}

export default function Fraud() {
  return <RoleGate allow={["analyst", "admin"]}><FraudInner /></RoleGate>;
}

