"use client";
import { useState } from "react";
import { api, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useFin } from "@/lib/fin";
import { Card, PageHead, State } from "@/components/ui";

type B = { code: string; label: string; min_inr: number; max_inr: number; default_mode: "simple" | "advanced"; situation: string; emphasis: string[] };

function BracketRow({ b, onSaved, canEdit }: { b: B; onSaved: () => void; canEdit: boolean }) {
  const [f, setF] = useState({ label: b.label, min_inr: b.min_inr, max_inr: b.max_inr, default_mode: b.default_mode, situation: b.situation, emphasis: b.emphasis.join("\n") });
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => {
    setMsg(null);
    try {
      await api(`/finance/brackets/${b.code}`, { method: "PUT", body: JSON.stringify({ ...f, min_inr: Number(f.min_inr), max_inr: Number(f.max_inr), emphasis: f.emphasis.split("\n").map((x) => x.trim()).filter(Boolean) }) });
      setMsg("Saved."); onSaved();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  };
  return (
    <Card title={`${b.code} · ${b.label}`}>
      <div className="formgrid">
        <label>Label<input disabled={!canEdit} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></label>
        <label>From (₹ / month)<input disabled={!canEdit} type="number" value={f.min_inr} onChange={(e) => setF({ ...f, min_inr: Number(e.target.value) })} /></label>
        <label>To (₹ / month)<input disabled={!canEdit} type="number" value={f.max_inr} onChange={(e) => setF({ ...f, max_inr: Number(e.target.value) })} /></label>
        <label>Default mode<select disabled={!canEdit} value={f.default_mode} onChange={(e) => setF({ ...f, default_mode: e.target.value as "simple" | "advanced" })}><option>simple</option><option>advanced</option></select></label>
        <label>Typical situation<input disabled={!canEdit} value={f.situation} onChange={(e) => setF({ ...f, situation: e.target.value })} /></label>
        <label>What to emphasise (one per line)<textarea disabled={!canEdit} rows={4} value={f.emphasis} onChange={(e) => setF({ ...f, emphasis: e.target.value })} /></label>
      </div>
      {canEdit && <p><button onClick={save}>Save bracket</button> {msg && <span className="hint">{msg}</span>}</p>}
    </Card>
  );
}

export default function Settings() {
  const { me } = useAuth();
  const { cid, mode, setMode, bracket, tick, refresh } = useFin();
  const r = useApi<{ items: B[] }>("/finance/brackets", [tick]);
  const isAdmin = me?.role === "admin";
  return (
    <>
      <PageHead eyebrow="My money" title="Settings">Choose how much detail you want, and see how income brackets decide what FinShield emphasises.</PageHead>
      <Card title="Detail level">
        <div className="pills" role="group" aria-label="Detail level">
          <button aria-pressed={mode === "simple"} onClick={() => setMode("simple")}>Simple</button>
          <button aria-pressed={mode === "advanced"} onClick={() => setMode("advanced")}>Advanced</button>
        </div>
        <p className="hint">Simple shows the five numbers that matter most. Advanced adds net worth, debt ratios, trends and the 50/30/20 view. Customer {cid}{bracket ? ` is in the “${bracket.label}” bracket.` : "."}</p>
        <p className="hint">Currency: INR (₹). Months follow the calendar (1st to last day), in the Asia/Kolkata time zone.</p>
      </Card>
      <h2 style={{ margin: "22px 0 10px" }}>Income brackets {isAdmin ? "(editable by administrators)" : ""}</h2>
      <State loading={r.loading} error={r.error}>
        {r.data?.items.map((b) => <BracketRow key={b.code} b={b} canEdit={isAdmin} onSaved={refresh} />)}
      </State>
    </>
  );
}
