"use client";
import type { ReactNode } from "react";
import { FinProvider, monthLabel, useFin } from "@/lib/fin";

function FinBar() {
  const { cid, setCid, month, setMonth, months, mode, setMode, bracket, isStaff } = useFin();
  return (
    <div className="toolbar">
      {isStaff ? (
        <label>Customer (synthetic)<input type="number" min={1} max={600} value={cid} onChange={(e) => setCid(Number(e.target.value) || 1)} style={{ width: 96 }} /></label>
      ) : (
        <label>Customer<span style={{ fontWeight: 700, fontSize: 15, color: "var(--blue)", letterSpacing: 0, textTransform: "none" }}>CUST-{String(cid).padStart(4, "0")} (you)</span></label>
      )}
      <label>Month
        <select value={month ?? ""} onChange={(e) => setMonth(e.target.value)} aria-label="Month">
          {[...months].reverse().map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
        </select>
      </label>
      <div className="modebadge">
        {bracket && <span className="badge2" title={bracket.situation}>Income bracket: {bracket.label}</span>}
        <div className="pills" role="group" aria-label="Detail level">
          <button aria-pressed={mode === "simple"} onClick={() => setMode("simple")}>Simple</button>
          <button aria-pressed={mode === "advanced"} onClick={() => setMode("advanced")}>Advanced</button>
        </div>
      </div>
    </div>
  );
}

export default function FinLayout({ children }: { children: ReactNode }) {
  return (
    <FinProvider>
      <FinBar />
      {children}
    </FinProvider>
  );
}
