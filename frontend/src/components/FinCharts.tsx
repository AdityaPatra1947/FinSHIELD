"use client";
import { inr } from "@/lib/format";

type Pt = { label: string; a: number | null; b?: number | null };

/** Paired bars (e.g. income vs expenses). Values in rupees. */
export function PairBars({ pts, aName, bName, height = 180 }: { pts: Pt[]; aName: string; bName: string; height?: number }) {
  const max = Math.max(1, ...pts.flatMap((p) => [p.a ?? 0, p.b ?? 0]));
  const cols = { gridTemplateColumns: `repeat(${Math.max(pts.length, 1)}, minmax(0, 1fr))` };
  return (
    <div>
      <div className="bars pair" style={{ ...cols, height }}>
        {pts.map((p) => (
          <div key={p.label} className="pairbar">
            <div className="bar" title={`${p.label} ${aName}: ${inr(String(Math.round((p.a ?? 0) * 100)))}`} style={{ height: `${Math.max(((p.a ?? 0) / max) * 100, 1.5)}%` }} />
            <div className="bar neg" title={`${p.label} ${bName}: ${inr(String(Math.round((p.b ?? 0) * 100)))}`} style={{ height: `${Math.max(((p.b ?? 0) / max) * 100, 1.5)}%` }} />
          </div>
        ))}
      </div>
      <div className="bars" style={cols} aria-hidden="true">{pts.map((p) => <div key={p.label} className="lbl">{p.label.split(" ")[0]}</div>)}</div>
      <div className="split-leg"><span><i style={{ background: "var(--blue)" }} />{aName}</span><span><i style={{ background: "var(--coral)" }} />{bName}</span></div>
    </div>
  );
}

/** Simple line chart for a single series. */
export function Line({ pts, unit = "money", height = 170, color = "#226192" }: { pts: { label: string; v: number | null }[]; unit?: "money" | "pct"; height?: number; color?: string }) {
  const vals = pts.map((p) => p.v).filter((v): v is number => v !== null);
  if (vals.length < 2) return <p className="muted small">Not enough history yet.</p>;
  const lo = Math.min(0, ...vals), hi = Math.max(...vals) || 1;
  const W = 320, H = height, P = 26;
  const X = (i: number) => P + (i / Math.max(pts.length - 1, 1)) * (W - P - 6);
  const Y = (v: number) => H - 22 - ((v - lo) / (hi - lo || 1)) * (H - 36);
  const path = pts.map((p, i) => (p.v === null ? null : `${X(i)},${Y(p.v)}`)).filter(Boolean).join(" ");
  const f = (v: number) => (unit === "pct" ? `${v.toFixed(0)}%` : inr(String(Math.round(v * 100))));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ width: "100%", height }} aria-label="Trend chart">
      <line x1={P} x2={W - 6} y1={Y(0)} y2={Y(0)} stroke="var(--grid)" />
      <polyline points={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      {pts.map((p, i) => p.v !== null && <circle key={i} cx={X(i)} cy={Y(p.v)} r="2.6" fill={color}><title>{`${p.label}: ${f(p.v)}`}</title></circle>)}
      <text x={P} y={H - 6} fontSize="8.5" fill="currentColor" opacity=".7">{pts[0].label}</text>
      <text x={W - 6} y={H - 6} fontSize="8.5" fill="currentColor" opacity=".7" textAnchor="end">{pts[pts.length - 1].label}</text>
      <text x={P} y={10} fontSize="8.5" fill="currentColor" opacity=".7">{f(hi)}</text>
    </svg>
  );
}
