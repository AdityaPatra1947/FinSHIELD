"use client";
import type { ReactNode } from "react";

export const COLORS = ["#226192", "#EF8557", "#6b8296"];

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function monthLabel(l: string, i: number): [string, string] {
  const m = /^(\d{4})-(\d{2})$/.exec(l);
  if (!m) return [l.slice(-6), ""];
  const mo = Number(m[2]) - 1;
  return [MON[mo], mo === 0 || i === 0 ? `\u2019${m[1].slice(2)}` : ""];
}

export function Bars({ items, height = 190 }: { items: { label: string; value: number; sub?: string }[]; height?: number }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  const cols = { gridTemplateColumns: `repeat(${Math.max(items.length, 1)}, minmax(0, 1fr))` };
  return (
    <div role="img" aria-label={`Bar chart: ${items.map((i) => `${i.label} ${i.sub ?? i.value}`).join(", ")}`}>
      <div className="bars" style={{ ...cols, height }}>
        {items.map((it) => (
          <div key={it.label} className={`bar${it.value < 0 ? " neg" : ""}`} title={`${it.label}: ${it.sub ?? it.value}`}
            style={{ height: `${Math.max((Math.abs(it.value) / max) * 100, 1.5)}%` }} />
        ))}
      </div>
      <div className="bars" style={cols} aria-hidden="true">
        {items.map((it, i) => {
          const [a, b] = monthLabel(it.label, i);
          return <div key={it.label} className="lbl">{a}<br />{b || "\u00a0"}</div>;
        })}
      </div>
    </div>
  );
}

export function HBars({ items }: { items: { label: string; value: number; text: string }[] }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  return (
    <div>
      {items.map((i) => (
        <div key={i.label} className="hb">
          <span className="nm" title={i.label}>{i.label}</span>
          <div className="track"><div className={`fill${i.value < 0 ? " neg" : ""}`} style={{ width: `${(Math.abs(i.value) / max) * 100}%` }} /></div>
          <span className="tx" title={i.text}>{i.text}</span>
        </div>
      ))}
    </div>
  );
}
type Series = { name: string; color: string; pts: number[][]; dash?: string };
export function LineChart({ series, xLabel, yLabel, diagonal, size = 260 }:
  { series: Series[]; xLabel: string; yLabel: string; diagonal?: boolean; size?: number }) {
  const P = 34, S = size;
  const X = (v: number) => P + v * (S - P - 8);
  const Y = (v: number) => S - P - v * (S - P - 8);
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label={`${yLabel} versus ${xLabel}`} style={{ width: "100%", maxWidth: 340 }}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={X(0)} x2={X(1)} y1={Y(t)} y2={Y(t)} stroke="var(--grid)" />
            <text x={X(0) - 4} y={Y(t) + 3} fontSize={8} textAnchor="end" fill="currentColor">{t}</text>
            <text x={X(t)} y={Y(0) + 11} fontSize={8} textAnchor="middle" fill="currentColor">{t}</text>
          </g>
        ))}
        {diagonal && <line x1={X(0)} y1={Y(0)} x2={X(1)} y2={Y(1)} stroke="var(--grid)" strokeDasharray="3 3" />}
        {series.map((s) => (
          <polyline key={s.name} fill="none" stroke={s.color} strokeWidth={1.8} strokeDasharray={s.dash}
            points={s.pts.map(([x, y]) => `${X(x)},${Y(y)}`).join(" ")} />
        ))}
        <text x={S / 2} y={S - 2} fontSize={9} textAnchor="middle" fill="currentColor">{xLabel}</text>
        <text x={8} y={S / 2} fontSize={9} textAnchor="middle" fill="currentColor" transform={`rotate(-90 8 ${S / 2})`}>{yLabel}</text>
      </svg>
      <figcaption style={{ fontSize: 12, display: "flex", gap: 12, flexWrap: "wrap" }}>
        {series.map((s) => (
          <span key={s.name}><span style={{ color: s.color }}>{s.dash ? "╌╌" : "━━"}</span> {s.name}</span>
        ))}
      </figcaption>
    </figure>
  );
}

export function Scatter({ pts, colors, size = 380 }: { pts: { x: number; y: number; c: number; t: string }[]; colors: string[]; size?: number }) {
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const m = 16;
  const X = (v: number) => m + ((v - x0) / (x1 - x0 || 1)) * (size - 2 * m);
  const Y = (v: number) => size - m - ((v - y0) / (y1 - y0 || 1)) * (size - 2 * m);
  const shapes = (c: number, x: number, y: number, t: string): ReactNode => {
    const k = c % 3;
    const fill = colors[c % colors.length];
    const title = <title>{t}</title>;
    if (k === 0) return <circle key={t} cx={x} cy={y} r={3.2} fill={fill} opacity={0.8}>{title}</circle>;
    if (k === 1) return <rect key={t} x={x - 3} y={y - 3} width={6} height={6} fill={fill} opacity={0.8}>{title}</rect>;
    return <polygon key={t} points={`${x},${y - 4} ${x + 4},${y + 3} ${x - 4},${y + 3}`} fill={fill} opacity={0.8}>{title}</polygon>;
  };
  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="PCA scatter of customer segments" style={{ width: "100%", maxWidth: 460 }}>
      <rect x={0} y={0} width={size} height={size} fill="none" stroke="var(--grid)" />
      {pts.map((p) => shapes(p.c, X(p.x), Y(p.y), p.t))}
    </svg>
  );
}
