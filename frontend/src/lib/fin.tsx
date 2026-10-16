"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import { inr } from "./format";

export type Inp = { label: string; value: string | number | null; kind: string };
export type Explain = { formula: string; inputs: Inp[]; meaning: string; reading: string; caveat?: string | null };
export type Metric = { key: string; label: string; value: string | number | null; kind: string; sub?: string | null; tone?: string | null; explain: Explain };

export function fmt(kind: string, v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "Not available";
  switch (kind) {
    case "money": return inr(String(v));
    case "pct": return `${Number(v).toFixed(1)}%`;
    case "months": return `${Number(v).toFixed(1)} months`;
    case "count": return Number(v).toLocaleString("en-IN");
    default: return String(v);
  }
}

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const monthLabel = (m: string) => { const [y, mo] = m.split("-"); return `${MONTHS[Number(mo) - 1]} ${y}`; };

type Open = { title: string; value?: string; explain: Explain; extra?: ReactNode } | null;
type Ctx = {
  cid: number; setCid: (n: number) => void; month: string | null; setMonth: (m: string | null) => void;
  months: string[]; mode: "simple" | "advanced"; setMode: (m: "simple" | "advanced") => void;
  explain: (o: NonNullable<Open>) => void; bracket: { code: string; label: string; situation: string; emphasis: string[] } | null;
  refresh: () => void; tick: number; isStaff: boolean;
};
const FinCtx = createContext<Ctx>(null as unknown as Ctx);
export const useFin = () => useContext(FinCtx);

export function FinProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const isStaff = me?.role !== "customer";
  const [picked, setCid] = useState(1);
  const cid = !isStaff && me?.customer_id ? me.customer_id : picked;
  const [month, setMonth] = useState<string | null>(null);
  const [months, setMonths] = useState<string[]>([]);
  const [mode, setModeState] = useState<"simple" | "advanced">("advanced");
  const [bracket, setBracket] = useState<Ctx["bracket"]>(null);
  const [open, setOpen] = useState<Open>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api<{ profile: { preferred_mode?: string }; bracket: NonNullable<Ctx["bracket"]>; months: string[] }>(`/finance/profile?customer_id=${cid}`)
      .then((p) => {
        if (!live) return;
        setMonths(p.months || []);
        setBracket(p.bracket);
        let saved: string | null = null;
        try { saved = localStorage.getItem(`fs_mode_${cid}`); } catch {}
        setModeState((saved as "simple" | "advanced") || (p.profile.preferred_mode as "simple" | "advanced") || "advanced");
        setMonth((cur) => (cur && p.months.includes(cur) ? cur : p.months[p.months.length - 1] ?? null));
      })
      .catch(() => {});
    return () => { live = false; };
  }, [cid]);

  const setMode = useCallback((m: "simple" | "advanced") => {
    setModeState(m);
    try { localStorage.setItem(`fs_mode_${cid}`, m); } catch {}
    if (!isStaff) api(`/finance/profile`, { method: "PUT", body: JSON.stringify({ preferred_mode: m }) }).catch(() => {});
  }, [cid, isStaff]);

  const value = useMemo<Ctx>(() => ({
    cid, setCid, month, setMonth, months, mode, setMode, explain: (o) => setOpen(o), bracket, tick, isStaff,
    refresh: () => setTick((t) => t + 1),
  }), [cid, month, months, mode, setMode, bracket, tick, isStaff]);

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open]);

  return (
    <FinCtx.Provider value={value}>
      {children}
      {open && (
        <div className="drawer-wrap" onClick={() => setOpen(null)}>
          <aside className="drawer" role="dialog" aria-modal="true" aria-label={`How ${open.title} is calculated`} onClick={(e) => e.stopPropagation()}>
            <button className="drawer-x" onClick={() => setOpen(null)} aria-label="Close explanation" autoFocus>✕</button>
            <div className="ey">How this is calculated</div>
            <h2 className="drawer-title">{open.title}</h2>
            {open.value && <div className="drawer-value">{open.value}</div>}
            <h3>What it means</h3>
            <p>{open.explain.meaning}</p>
            <h3>Formula</h3>
            <p className="formula">{open.explain.formula}</p>
            <h3>Your numbers</h3>
            <table><tbody>
              {open.explain.inputs.map((i, k) => (
                <tr key={k}><td>{i.label}</td><td className="n"><strong>{fmt(i.kind, i.value)}</strong></td></tr>))}
            </tbody></table>
            <h3>How to read it</h3>
            <p>{open.explain.reading}</p>
            {open.explain.caveat && <p className="note">{open.explain.caveat}</p>}
            {open.extra}
          </aside>
        </div>
      )}
    </FinCtx.Provider>
  );
}

export function MetricCard({ m, tone }: { m: Metric; tone?: string }) {
  const { explain } = useFin();
  const t = tone ?? m.tone ?? undefined;
  const value = fmt(m.kind, m.value);
  return (
    <button type="button" className={`stat stat-btn${t ? ` ${t}` : ""}`} onClick={() => explain({ title: m.label, value, explain: m.explain })}
      aria-label={`${m.label}: ${value}. Click to see how it is calculated`}>
      <div className="lab">{m.label}<span className="info" aria-hidden="true">i</span></div>
      <div className={`big${/^[₹\d-]/.test(value) ? " num" : ""}`}>{value}</div>
      {m.sub && <div className="sub">{m.sub}</div>}
    </button>
  );
}

/** Small clickable "i" that opens an explanation for table rows etc. */
export function ExplainLink({ title, value, explain, children }: { title: string; value?: string; explain: Explain; children: ReactNode }) {
  const { explain: open } = useFin();
  return <button type="button" className="linkish" onClick={() => open({ title, value, explain })}>{children}</button>;
}

export function Progress({ pct, status }: { pct: number | null; status?: "ok" | "near" | "over" }) {
  const w = Math.max(0, Math.min(100, pct ?? 0));
  return (
    <div className="prog" role="progressbar" aria-valuenow={Math.round(pct ?? 0)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`prog-fill ${status ?? "ok"}`} style={{ width: `${w}%` }} />
    </div>
  );
}

export function SplitBar({ parts }: { parts: { label: string; pct: number | null; color: string }[] }) {
  const tot = parts.reduce((a, p) => a + Math.max(0, p.pct ?? 0), 0) || 1;
  return (
    <div>
      <div className="split">{parts.map((p) => <div key={p.label} style={{ width: `${(Math.max(0, p.pct ?? 0) / tot) * 100}%`, background: p.color }} title={`${p.label}: ${p.pct?.toFixed(1)}%`} />)}</div>
      <div className="split-leg">{parts.map((p) => <span key={p.label}><i style={{ background: p.color }} />{p.label} {p.pct == null ? "n/a" : `${p.pct.toFixed(0)}%`}</span>)}</div>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-wrap" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><h2>{title}</h2><button onClick={onClose} aria-label="Close">✕</button></div>
        {children}
      </div>
    </div>
  );
}
