"use client";
import { useState, type FormEvent } from "react";
import { api, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { inr } from "@/lib/format";
import { Card, CustomerPicker, PageHead, State, useCid } from "@/components/ui";

type Tx = { id: number; occurred_at: string; amount_minor: string; direction: string; status: string; purpose: string;
  category: string | null; channel: string; account_kind: string; fraud_probability: number | null };
const CATS = ["groceries", "dining", "transport", "shopping", "entertainment", "health", "utilities", "travel", "education", "rent"];

function AddTransaction({ onAdded }: { onAdded: () => void }) {
  const [amount, setAmount] = useState("");
  const [purpose, setPurpose] = useState("purchase");
  const [category, setCategory] = useState("groceries");
  const [kind, setKind] = useState("bank");
  const [merchant, setMerchant] = useState("");
  const [when, setWhen] = useState(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());

  async function submit(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const off = -new Date(when).getTimezoneOffset();
      const sign = off >= 0 ? "+" : "-";
      const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, "0"), mm = String(Math.abs(off) % 60).padStart(2, "0");
      const r = await api<{ id: number }>("/transactions", {
        method: "POST", headers: { "Idempotency-Key": key },
        body: JSON.stringify({ amount, purpose, category: purpose === "purchase" ? category : null, account_kind: kind,
          merchant_display: merchant || null, occurred_at: `${when}:00${sign}${hh}:${mm}` }) });
      setMsg({ ok: true, text: `Saved transaction #${r.id}.` });
      setAmount(""); setKey(crypto.randomUUID()); onAdded();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Could not save" });
    }
  }
  return (
    <Card title="Add a transaction" note="Manual entries are posted immediately, audited, and are not fraud-scored (only observed digital attempts are scored).">
      <form onSubmit={submit} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
        <label>Amount (₹)<br /><input required inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 110 }} /></label>
        <label>Type<br /><select value={purpose} onChange={(e) => setPurpose(e.target.value)}><option value="purchase">Purchase</option><option value="fee">Fee</option><option value="salary">Salary (income)</option></select></label>
        {purpose === "purchase" && <label>Category<br /><select value={category} onChange={(e) => setCategory(e.target.value)}>{CATS.map((c) => <option key={c}>{c}</option>)}</select></label>}
        <label>Account<br /><select value={kind} onChange={(e) => setKind(e.target.value)}><option value="bank">Bank</option><option value="cash">Cash wallet</option><option value="credit_card">Credit card</option></select></label>
        <label>Merchant<br /><input value={merchant} maxLength={80} onChange={(e) => setMerchant(e.target.value)} style={{ width: 150 }} /></label>
        <label>When<br /><input type="datetime-local" required value={when} onChange={(e) => setWhen(e.target.value)} /></label>
        <button type="submit">Add</button>
      </form>
      {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "note" : "note err"}>{msg.text}</p>}
    </Card>
  );
}

export default function Transactions() {
  const { me } = useAuth();
  const [picked, setCid] = useState(1);
  const cid = useCid(picked);
  const [status, setStatus] = useState("");
  const [purpose, setPurpose] = useState("");
  const [cursors, setCursors] = useState<number[]>([]);
  const [bump, setBump] = useState(0);
  const cur = cursors.length ? cursors[cursors.length - 1] : null;
  const q = `/transactions?customer_id=${cid}&limit=50${status ? `&status=${status}` : ""}${purpose ? `&purpose=${purpose}` : ""}${cur ? `&cursor=${cur}` : ""}`;
  const r = useApi<{ items: Tx[]; next_cursor: number | null }>(q, [bump]);
  const reset = (f: () => void) => { f(); setCursors([]); };
  return (
    <>
      <PageHead eyebrow="Workspace" title="Transactions">Every posted, pending and failed movement. Customers can add their own entries; digital attempts carry a fraud score where one exists.</PageHead>
      {me?.role === "customer" && <AddTransaction onAdded={() => { setCursors([]); setBump((b) => b + 1); }} />}
      <div className="toolbar">
        <CustomerPicker value={picked} onChange={(n) => reset(() => setCid(n))} />
        <label>Status <select value={status} onChange={(e) => reset(() => setStatus(e.target.value))}>
          <option value="">all</option><option>posted</option><option>failed</option><option>cancelled</option></select></label>
        <label>Purpose <select value={purpose} onChange={(e) => reset(() => setPurpose(e.target.value))}>
          <option value="">all</option>{["purchase", "salary", "refund", "fee", "own_transfer", "cash_withdrawal", "card_repayment", "investment_contribution", "external_transfer"].map((p) => <option key={p}>{p}</option>)}</select></label>
      </div>
      <State loading={r.loading} error={r.error}>
        {r.data && r.data.items.length === 0 && <p>No transactions match these filters.</p>}
        {r.data && r.data.items.length > 0 && (
          <div className="scroll"><table>
            <thead><tr><th>Date (IST)</th><th>Purpose</th><th>Category</th><th>Channel</th><th>Account</th><th>Status</th><th className="n">Amount</th><th className="n">Fraud score</th></tr></thead>
            <tbody>{r.data.items.map((t) => (
              <tr key={t.id}>
                <td>{t.occurred_at.slice(0, 16).replace("T", " ")}</td><td>{t.purpose}</td><td>{t.category ?? "—"}</td>
                <td>{t.channel}</td><td>{t.account_kind}</td><td><span className="tag">{t.status}</span></td>
                <td className="n">{t.direction === "credit" ? "+" : "−"}{inr(t.amount_minor)}</td>
                <td className="n">{t.fraud_probability == null ? "—" : <span className={t.fraud_probability > 0.5 ? "risk-high" : t.fraud_probability > 0.1 ? "risk-med" : "risk-low"}>{t.fraud_probability.toFixed(3)}</span>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        <p>
          <button disabled={!cursors.length} onClick={() => setCursors((c) => c.slice(0, -1))}>Newer</button>{" "}
          <button disabled={!r.data?.next_cursor} onClick={() => r.data?.next_cursor && setCursors((c) => [...c, r.data!.next_cursor!])}>Older</button>
        </p>
        <p className="muted small">Fraud scores exist only for the locked test period (days 299–365). A score is an estimate for review, not proof of fraud.</p>
      </State>
    </>
  );
}
