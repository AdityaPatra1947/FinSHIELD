"use client";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { fmt, useFin, type Explain } from "@/lib/fin";
import { Line } from "@/components/FinCharts";
import { Card, PageHead, State } from "@/components/ui";

type H = { holding_id: number; name: string; kind: string; asset_class: string; sip: string; invested: string; value: string; gain: string; return_pct: number | null; tax_80c: boolean; explain: Explain };
type R = { holdings: H[]; totals: { value: string; invested: string; gain: string; return_pct: number | null }; allocation: { asset_class: string; value: string; share_pct: number | null }[];
  series: { label: string; value: string; invested: string }[] };
const KIND: Record<string, string> = { sip_mf: "Mutual fund SIP", stock: "Stocks", fd: "Fixed deposit", gold: "Gold" };

export default function Investments() {
  const { cid, tick, explain } = useFin();
  const r = useApi<R>(`/finance/investments?customer_id=${cid}`, [tick]);
  const d = r.data;
  return (
    <>
      <PageHead eyebrow="My money" title="Investments">SIPs and holdings with invested amount, current value and returns. Click a holding for the working.</PageHead>
      <State loading={r.loading} error={r.error}>
        {d && d.holdings.length === 0 && <p className="note">No investments yet. Start a monthly SIP from the Transactions page (type: Investment).</p>}
        {d && d.holdings.length > 0 && (
          <>
            <div className="stats">
              <div className="stat blue"><div className="lab">Current value</div><div className="big num">{inr(d.totals.value)}</div></div>
              <div className="stat"><div className="lab">Invested</div><div className="big num">{inr(d.totals.invested)}</div></div>
              <div className="stat coral"><div className="lab">Gain / loss</div><div className="big num">{inr(d.totals.gain)}</div><div className="sub">{fmt("pct", d.totals.return_pct)} return</div></div>
            </div>
            <div className="grid">
              <Card title="Value vs amount invested" note="Blue line: value. The gap above invested is your gain.">
                <Line pts={d.series.map((s) => ({ label: s.label, v: Number(s.value) / 100 }))} />
                <Line color="#EF8557" pts={d.series.map((s) => ({ label: s.label, v: Number(s.invested) / 100 }))} height={110} />
              </Card>
              <Card title="Asset allocation" note="Share of current value by asset class.">
                {d.allocation.map((a) => (
                  <div key={a.asset_class} className="hb"><span className="nm">{a.asset_class}</span><div className="track"><div className="fill" style={{ width: `${a.share_pct ?? 0}%` }} /></div><span className="tx">{fmt("pct", a.share_pct)}</span></div>))}
              </Card>
            </div>
            <Card title="Holdings">
              <div className="scroll"><table>
                <thead><tr><th>Holding</th><th>Type</th><th className="n">Monthly SIP</th><th className="n">Invested</th><th className="n">Value</th><th className="n">Gain</th><th className="n">Return</th></tr></thead>
                <tbody>{d.holdings.map((h) => (
                  <tr key={h.holding_id} className="row-btn" tabIndex={0} onClick={() => explain({ title: h.name, value: inr(h.value), explain: h.explain })}
                    onKeyDown={(e) => e.key === "Enter" && explain({ title: h.name, value: inr(h.value), explain: h.explain })}>
                    <td><strong>{h.name}</strong> {h.tax_80c && <span className="badge2 good">80C</span>}</td><td>{KIND[h.kind] ?? h.kind}</td>
                    <td className="n">{Number(h.sip) ? inr(h.sip) : "—"}</td><td className="n">{inr(h.invested)}</td><td className="n"><strong>{inr(h.value)}</strong></td>
                    <td className={`n ${Number(h.gain) >= 0 ? "amt-in" : "amt-out"}`}>{inr(h.gain)}</td><td className="n">{fmt("pct", h.return_pct)}</td></tr>))}</tbody>
              </table></div>
            </Card>
          </>
        )}
      </State>
    </>
  );
}
