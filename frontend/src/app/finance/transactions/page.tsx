"use client";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { Modal, useFin, monthLabel } from "@/lib/fin";
import { Card, PageHead, State } from "@/components/ui";

type Tx = { id: number; date: string; time: string; amount: string; direction: string; status: string; type: string; kind_label: string; purpose: string;
  category: string | null; category_label: string | null; subcategory: string | null; subcategory_label: string | null; merchant: string | null; payment_method: string | null;
  account: string | null; account_id: number | null; tags: string | null; notes: string | null; recurring: boolean; fixed_variable: string | null; need_want: string | null;
  income_type: string | null; gross: string | null; tds: string | null; pf: string | null; needs_classification: boolean; classified: boolean; voidable: boolean; fraud_probability: number | null };
type Tax = { categories: { code: string; label: string; group: string; need_want: string; subcategories: { code: string; label: string; fixed: boolean }[] }[];
  income_types: { code: string; label: string; class: string }[]; payment_methods: string[] };
type Acc = { account_id: number; kind: string; name: string };

const TYPES = [["", "All"], ["income", "Income"], ["expense", "Expense"], ["transfer", "Transfers"], ["investment", "Investments"], ["debt", "Debt principal"]];

function CategoryPicker({ tax, cat, sub, setCat, setSub }: { tax: Tax; cat: string; sub: string; setCat: (c: string) => void; setSub: (s: string) => void }) {
  const subs = tax.categories.find((c) => c.code === cat)?.subcategories ?? [];
  return (
    <>
      <label>Category<select value={cat} onChange={(e) => { setCat(e.target.value); setSub(""); }}>
        <option value="">Choose…</option>
        {["Essentials", "Lifestyle", "Social", "Financial"].map((g) => (
          <optgroup key={g} label={g}>{tax.categories.filter((c) => c.group === g).map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}</optgroup>))}
      </select></label>
      <label>Subcategory<select value={sub} onChange={(e) => setSub(e.target.value)} disabled={!subs.length}>
        <option value="">—</option>{subs.map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}</select></label>
    </>
  );
}

function Detail({ t, tax, onClose, onChanged, canEdit }: { t: Tx; tax: Tax; onClose: () => void; onChanged: () => void; canEdit: boolean }) {
  const [cat, setCat] = useState(t.category ?? "");
  const [sub, setSub] = useState(t.subcategory ?? "");
  const [tags, setTags] = useState(t.tags ?? "");
  const [notes, setNotes] = useState(t.notes ?? "");
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const editableCat = t.type === "expense" || t.purpose === "external_transfer";
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    try {
      await api(`/finance/transactions/${t.id}/classification`, { method: "PATCH", body: JSON.stringify({ ...(editableCat && cat ? { category: cat, subcategory: sub || null } : {}), tags, notes }) });
      setMsg({ ok: true, t: "Saved. Reports now use the new classification." }); onChanged();
    } catch (er) { setMsg({ ok: false, t: er instanceof Error ? er.message : "Failed" }); }
  };
  const del = async () => {
    if (!confirm("Delete this entry? It is voided (kept for audit) and removed from your reports.")) return;
    try { await api(`/finance/transactions/${t.id}`, { method: "DELETE" }); onChanged(); onClose(); } catch (er) { setMsg({ ok: false, t: er instanceof Error ? er.message : "Failed" }); }
  };
  const rows: [string, string | null][] = [
    ["Type", t.kind_label], ["Date", `${t.date} ${t.time}`], ["Account", t.account], ["Payment method", t.payment_method], ["Merchant / party", t.merchant],
    ["Category", t.category_label ? `${t.category_label}${t.subcategory_label ? " → " + t.subcategory_label : ""}` : null],
    ["Need or want", t.need_want], ["Fixed or variable", t.fixed_variable], ["Recurring", t.recurring ? "Yes" : "No"], ["Status", t.status]];
  return (
    <Modal title={`${t.direction === "credit" ? "+" : "−"}${inr(t.amount)} · ${t.kind_label}`} onClose={onClose}>
      <table><tbody>{rows.filter((r) => r[1]).map(([k, v]) => <tr key={k}><td className="muted">{k}</td><td>{v}</td></tr>)}</tbody></table>
      {t.gross && <p className="formula-note hint">Gross {inr(t.gross)} − tax {inr(t.tds ?? "0")} − PF {inr(t.pf ?? "0")} = <strong>net {inr(t.amount)}</strong> received.</p>}
      {t.fraud_probability != null && <p className="hint">Fraud model score: {t.fraud_probability.toFixed(3)} (estimate for review, not proof).</p>}
      {t.needs_classification && <p className="note">This payment to another person is <strong>not counted as spending</strong> until you choose a category below.</p>}
      {canEdit && (
        <form onSubmit={save} style={{ marginTop: 14 }}>
          <div className="formgrid">
            {editableCat && <CategoryPicker tax={tax} cat={cat} sub={sub} setCat={setCat} setSub={setSub} />}
            <label>Tags<input value={tags} maxLength={80} onChange={(e) => setTags(e.target.value)} placeholder="birthday, work trip" /></label>
            <label>Notes<input value={notes} maxLength={200} onChange={(e) => setNotes(e.target.value)} /></label>
          </div>
          <p style={{ display: "flex", gap: 8, marginTop: 12 }}><button type="submit">Save changes</button>{t.voidable && <button type="button" onClick={del}>Delete entry</button>}</p>
          {!t.voidable && <p className="hint">Bank and imported entries are evidence: the amount and date cannot change or be deleted, but you can reclassify them.</p>}
        </form>)}
      {msg && <p className={`note${msg.ok ? "" : " err"}`} role={msg.ok ? "status" : "alert"}>{msg.t}</p>}
    </Modal>
  );
}

function AddTx({ tax, accounts, onClose, onAdded }: { tax: Tax; accounts: Acc[]; onClose: () => void; onAdded: () => void }) {
  const [type, setType] = useState<"expense" | "income" | "transfer" | "investment">("expense");
  const [f, setF] = useState({ amount: "", account_id: String(accounts[0]?.account_id ?? ""), to_account_id: "", merchant: "", payment_method: "UPI", income_type: "salary", gross: "", tags: "", notes: "", recurring: false });
  const [cat, setCat] = useState(""); const [sub, setSub] = useState("");
  const [when, setWhen] = useState(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16));
  const [msg, setMsg] = useState<string | null>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const asset = accounts.filter((a) => a.kind !== "credit_card");
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setMsg(null);
    const off = -new Date(when).getTimezoneOffset(); const sg = off >= 0 ? "+" : "-";
    const oa = `${when}:00${sg}${String(Math.floor(Math.abs(off) / 60)).padStart(2, "0")}:${String(Math.abs(off) % 60).padStart(2, "0")}`;
    try {
      await api("/finance/transactions", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({
        type, amount: f.amount, occurred_at: oa, account_id: Number(f.account_id), to_account_id: f.to_account_id ? Number(f.to_account_id) : null,
        category: type === "expense" ? cat : null, subcategory: type === "expense" && sub ? sub : null, merchant: f.merchant || null,
        payment_method: f.payment_method, income_type: type === "income" ? f.income_type : null, gross: type === "income" && f.gross ? f.gross : null,
        tags: f.tags || null, notes: f.notes || null, recurring: f.recurring }) });
      setKey(crypto.randomUUID()); onAdded(); onClose();
    } catch (er) { setMsg(er instanceof Error ? er.message : "Could not save"); }
  };
  const set = (k: string, v: string | boolean) => setF({ ...f, [k]: v });
  return (
    <Modal title="Add a transaction" onClose={onClose}>
      <div className="pills" role="group" aria-label="Transaction type" style={{ marginBottom: 12 }}>
        {(["expense", "income", "transfer", "investment"] as const).map((t) => <button key={t} type="button" aria-pressed={type === t} onClick={() => setType(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}
      </div>
      <p className="hint">{type === "transfer" ? "Moving money between your own accounts (or paying a card bill) is a transfer, not spending." :
        type === "investment" ? "SIPs and investments are tracked separately from spending." :
        type === "income" ? "Enter what reached your account (net). Add gross if you know it, for tax tracking." : "Everyday spending: pick a category so budgets and reports stay accurate."}</p>
      <form onSubmit={submit}>
        <div className="formgrid">
          <label>Amount (₹)<input required inputMode="decimal" value={f.amount} onChange={(e) => set("amount", e.target.value)} /></label>
          <label>{type === "transfer" ? "From account" : type === "income" ? "Into account" : "Account"}
            <select value={f.account_id} onChange={(e) => set("account_id", e.target.value)}>
              {(type === "expense" ? accounts : asset).map((a) => <option key={a.account_id} value={a.account_id}>{a.name}</option>)}</select></label>
          {type === "transfer" && <label>To account<select required value={f.to_account_id} onChange={(e) => set("to_account_id", e.target.value)}>
            <option value="">Choose…</option>{accounts.filter((a) => String(a.account_id) !== f.account_id).map((a) => <option key={a.account_id} value={a.account_id}>{a.name}</option>)}</select></label>}
          {type === "expense" && <CategoryPicker tax={tax} cat={cat} sub={sub} setCat={setCat} setSub={setSub} />}
          {type === "income" && <label>Income type<select value={f.income_type} onChange={(e) => set("income_type", e.target.value)}>
            {["Active", "Business", "Passive", "Capital gains", "Irregular", "Benefits"].map((c) => <optgroup key={c} label={c}>{tax.income_types.filter((i) => i.class === c).map((i) => <option key={i.code} value={i.code}>{i.label}</option>)}</optgroup>)}</select></label>}
          {type === "income" && <label>Gross before deductions (₹, optional)<input inputMode="decimal" value={f.gross} onChange={(e) => set("gross", e.target.value)} /></label>}
          {type !== "transfer" && <label>{type === "income" ? "Source" : "Merchant"}<input maxLength={80} value={f.merchant} onChange={(e) => set("merchant", e.target.value)} /></label>}
          <label>Payment method<select value={f.payment_method} onChange={(e) => set("payment_method", e.target.value)}>{tax.payment_methods.map((p) => <option key={p}>{p}</option>)}</select></label>
          <label>When<input type="datetime-local" required value={when} onChange={(e) => setWhen(e.target.value)} /></label>
          <label>Tags<input maxLength={80} value={f.tags} onChange={(e) => set("tags", e.target.value)} placeholder="birthday, work trip" /></label>
          <label>Notes<input maxLength={200} value={f.notes} onChange={(e) => set("notes", e.target.value)} /></label>
          <label style={{ alignContent: "end" }}><span><input type="checkbox" checked={f.recurring} onChange={(e) => set("recurring", e.target.checked)} style={{ width: "auto" }} /> Repeats every month</span></label>
        </div>
        {msg && <p className="note err" role="alert">{msg}</p>}
        <p><button type="submit">Save transaction</button></p>
      </form>
    </Modal>
  );
}

export default function Transactions() {
  const { cid, month, tick, refresh, isStaff } = useFin();
  const [review, setReview] = useState(false);
  useEffect(() => { setReview(new URLSearchParams(window.location.search).get("review") === "1"); }, []);
  const [type, setType] = useState(""); const [category, setCategory] = useState(""); const [account, setAccount] = useState("");
  const [nw, setNw] = useState(""); const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [rec, setRec] = useState(false); const [inMonth, setInMonth] = useState(false);
  const [items, setItems] = useState<Tx[]>([]); const [cursor, setCursor] = useState<string | null>(null); const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Tx | null>(null); const [adding, setAdding] = useState(false);
  const tax = useApi<Tax>("/finance/taxonomy");
  const accs = useApi<{ accounts: Acc[] }>(`/finance/accounts?customer_id=${cid}`, [tick]);
  const qs = useMemo(() => {
    const p = new URLSearchParams({ customer_id: String(cid), limit: "50" });
    if (type) p.set("type", type); if (category) p.set("category", category); if (account) p.set("account_id", account);
    if (nw) p.set("need_want", nw); if (q) p.set("q", q); if (status) p.set("status", status); if (rec) p.set("recurring", "true");
    if (inMonth && month) p.set("month", month);
    return p.toString();
  }, [cid, type, category, account, nw, q, status, rec, inMonth, month]);
  const load = async (more: boolean) => {
    setLoading(true); setError(null);
    try {
      const path = review ? `/finance/review-queue?customer_id=${cid}` : `/finance/transactions?${qs}${more && cursor ? `&cursor=${cursor}` : ""}`;
      const r = await api<{ items: Tx[]; next_cursor?: string | null; total: number }>(path);
      setItems((cur) => (more ? [...cur, ...r.items] : r.items)); setCursor(r.next_cursor ?? null); setTotal(r.total);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); } finally { setLoading(false); }
  };
  useEffect(() => { const t = setTimeout(() => load(false), q ? 300 : 0); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [qs, tick, review]);
  const changed = () => { refresh(); };
  return (
    <>
      <PageHead eyebrow="My money" title={review ? "Review queue" : "Transactions"}
        actions={!isStaff && tax.data && accs.data ? <button onClick={() => setAdding(true)}>+ Add transaction</button> : undefined}>
        {review ? "Payments to other people that need a category. Until classified they are not counted as spending."
          : "Every money movement with its type, category, account, payment method, tags and flags. Click a row to see details or reclassify."}
      </PageHead>
      {review && <p><button onClick={() => { setReview(false); history.replaceState(null, "", "/finance/transactions"); }}>← All transactions</button></p>}
      {!review && tax.data && (
        <div className="toolbar">
          <div className="pills" role="group" aria-label="Type">{TYPES.map(([v, l]) => <button key={v} aria-pressed={type === v} onClick={() => setType(v)}>{l}</button>)}</div>
          <label>Category<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All</option>{tax.data.categories.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}</select></label>
          <label>Account<select value={account} onChange={(e) => setAccount(e.target.value)}><option value="">All</option>{accs.data?.accounts.map((a) => <option key={a.account_id} value={a.account_id}>{a.name}</option>)}</select></label>
          <label>Need / want<select value={nw} onChange={(e) => setNw(e.target.value)}><option value="">All</option><option value="need">Needs</option><option value="want">Wants</option><option value="social">Social</option></select></label>
          <label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option>posted</option><option>failed</option><option>cancelled</option></select></label>
          <label>Search<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="merchant, note, subcategory" style={{ width: 190 }} /></label>
          <label><span><input type="checkbox" checked={rec} onChange={(e) => setRec(e.target.checked)} style={{ width: "auto" }} /> Recurring only</span></label>
          <label><span><input type="checkbox" checked={inMonth} onChange={(e) => setInMonth(e.target.checked)} style={{ width: "auto" }} /> Only {month ? monthLabel(month) : "month"}</span></label>
        </div>)}
      <State loading={loading && items.length === 0} error={error}>
        <Card title={`${total.toLocaleString("en-IN")} transactions`}>
          <div className="scroll"><table>
            <thead><tr><th>Date</th><th>Description</th><th>Category</th><th>Account · method</th><th>Flags</th><th className="n">Amount</th></tr></thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className="row-btn" tabIndex={0} onClick={() => setOpen(t)} onKeyDown={(e) => e.key === "Enter" && setOpen(t)}>
                  <td style={{ whiteSpace: "nowrap" }}>{t.date}<div className="hint">{t.time}</div></td>
                  <td><strong>{t.merchant ?? t.kind_label}</strong><div className="hint">{t.kind_label}{t.notes ? ` · ${t.notes}` : ""}</div></td>
                  <td>{t.category_label ? <>{t.category_label}<div className="hint">{t.subcategory_label ?? ""}</div></> : <span className="hint">—</span>}
                    {t.needs_classification && <span className="badge2 warn">needs category</span>}</td>
                  <td>{t.account}<div className="hint">{t.payment_method}</div></td>
                  <td>{t.type === "expense" && t.need_want && <span className={`badge2 ${t.need_want === "need" ? "need" : "want"}`}>{t.need_want}</span>} {t.recurring && <span className="badge2">repeats</span>}
                    {t.fixed_variable && <span className="badge2">{t.fixed_variable}</span>} {t.tags && <span className="badge2">{t.tags}</span>} {t.status !== "posted" && <span className="badge2 warn">{t.status}</span>}</td>
                  <td className={`n ${t.direction === "credit" ? "amt-in" : "amt-out"}`}>{t.direction === "credit" ? "+" : "−"}{inr(t.amount)}</td>
                </tr>))}
            </tbody>
          </table></div>
          {items.length === 0 && !loading && <p>No transactions match these filters.</p>}
          {cursor && <p><button onClick={() => load(true)} disabled={loading}>{loading ? "Loading…" : "Load more"}</button></p>}
        </Card>
      </State>
      {open && tax.data && <Detail t={open} tax={tax.data} canEdit={!isStaff || true} onClose={() => setOpen(null)} onChanged={changed} />}
      {adding && tax.data && accs.data && <AddTx tax={tax.data} accounts={accs.data.accounts} onClose={() => setAdding(false)} onAdded={changed} />}
    </>
  );
}
