"use client";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

export function PageHead({ eyebrow, title, children, actions }: { eyebrow: string; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="pagehead">
      <div>
        <div className="ey">{eyebrow}</div>
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  );
}

export function State({ loading, error, children }: { loading: boolean; error: string | null; children: ReactNode }) {
  if (loading) return <p role="status" className="muted">Loading…</p>;
  if (error) return <p role="alert" className="note err">Could not load data: {error}. This is not a zero value — the request failed.</p>;
  return <>{children}</>;
}

export function Card({ title, children, note }: { title: string; children: ReactNode; note?: string }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {children}
      {note && <p className="muted small" style={{ marginBottom: 0 }}>{note}</p>}
    </section>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "blue" | "coral" }) {
  return (
    <div className={`stat${tone ? ` ${tone}` : ""}`}>
      <div className="lab">{label}</div>
      <div className={`big${/^[\u20b9\d-]/.test(value) ? " num" : ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

/** Customers are pinned to their own record; staff can pick any synthetic customer. */
export function CustomerPicker({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const { me } = useAuth();
  if (me?.role === "customer")
    return <label>Customer<span style={{ fontWeight: 700, fontSize: 15, color: "var(--blue)", letterSpacing: 0, textTransform: "none" }}>CUST-{String(me.customer_id).padStart(4, "0")} (you)</span></label>;
  return (
    <label>
      Customer (synthetic)
      <input type="number" min={1} max={600} value={value} onChange={(e) => onChange(Number(e.target.value) || 1)} style={{ width: 96 }} />
    </label>
  );
}

/** The customer id to query: own for customers, picked for staff. */
export function useCid(picked: number): number {
  const { me } = useAuth();
  return me?.role === "customer" && me.customer_id ? me.customer_id : picked;
}
