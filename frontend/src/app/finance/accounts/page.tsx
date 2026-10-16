"use client";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { Progress, useFin, type Explain } from "@/lib/fin";
import { PageHead, State } from "@/components/ui";

type Acc = { account_id: number; kind: string; name: string; institution: string; masked_ref: string | null; balance: string; owed?: string; limit?: string;
  utilisation?: number | null; money_in?: string; money_out?: string; purpose?: string; explain: Explain };
type R = { accounts: Acc[]; totals: Record<string, string> };
const ICON: Record<string, string> = { bank: "🏦", savings: "🐖", cash: "👛", credit_card: "💳" };

export default function Accounts() {
  const { cid, tick, explain } = useFin();
  const r = useApi<R>(`/finance/accounts?customer_id=${cid}`, [tick]);
  const t = r.data?.totals;
  const tot: { label: string; value: string; ex: Explain; tone?: string }[] = t ? [
    { label: "Assets", value: t.assets, ex: { formula: "Assets = bank + savings + cash + investments (current value)", inputs: [
        { label: "Bank + savings + cash", value: t.liquid, kind: "money" }, { label: "Investments", value: t.investments, kind: "money" }, { label: "Assets", value: t.assets, kind: "money" }],
      meaning: "Everything you own that can be turned into money.", reading: "Does not include a home or vehicle.", caveat: null } },
    { label: "Liabilities", value: t.liabilities, ex: { formula: "Liabilities = credit-card outstanding + loan principal outstanding", inputs: [
        { label: "Credit cards", value: t.cards, kind: "money" }, { label: "Loans", value: t.loans, kind: "money" }, { label: "Liabilities", value: t.liabilities, kind: "money" }],
      meaning: "Everything you owe.", reading: "Paying off high-interest debt first improves your net worth fastest.", caveat: null }, tone: "coral" },
    { label: "Net worth", value: t.net_worth, ex: { formula: "Net worth = assets − liabilities", inputs: [
        { label: "Assets", value: t.assets, kind: "money" }, { label: "− Liabilities", value: t.liabilities, kind: "money" }, { label: "= Net worth", value: t.net_worth, kind: "money" }],
      meaning: "What you would be left with after paying every debt.", reading: "Track it monthly; the direction matters more than the level.", caveat: null }, tone: "blue" },
  ] : [];
  return (
    <>
      <PageHead eyebrow="My money" title="Accounts">Bank, savings, cash and credit cards with live balances. Click any card to see how its balance is built.</PageHead>
      <State loading={r.loading} error={r.error}>
        <div className="stats">
          {tot.map((x) => (
            <button key={x.label} className={`stat stat-btn${x.tone ? ` ${x.tone}` : ""}`} onClick={() => explain({ title: x.label, value: inr(x.value), explain: x.ex })}>
              <div className="lab">{x.label}<span className="info">i</span></div><div className="big num">{inr(x.value)}</div></button>))}
        </div>
        <div className="cards">
          {r.data?.accounts.map((a) => (
            <button key={a.account_id} className="cardbtn" onClick={() => explain({ title: a.name, value: inr(a.kind === "credit_card" ? a.owed! : a.balance), explain: a.explain })}>
              <div className="t">{ICON[a.kind]} {a.name} <span className="hint">· {a.institution}{a.masked_ref ? ` ${a.masked_ref}` : ""}</span></div>
              {a.kind === "credit_card" ? (
                <>
                  <div className="big2">{inr(a.owed!)} <span className="hint">owed</span></div>
                  <Progress pct={a.utilisation ?? 0} status={(a.utilisation ?? 0) > 50 ? "over" : (a.utilisation ?? 0) > 30 ? "near" : "ok"} />
                  <div className="hint">Limit {inr(a.limit!)} · utilisation {a.utilisation == null ? "n/a" : `${a.utilisation.toFixed(0)}%`}</div>
                </>
              ) : (
                <>
                  <div className="big2">{inr(a.balance)}</div>
                  <div className="hint">In {inr(a.money_in!)} · Out {inr(a.money_out!)} · {a.purpose}</div>
                </>
              )}
            </button>))}
        </div>
      </State>
    </>
  );
}
