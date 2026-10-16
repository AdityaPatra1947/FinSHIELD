"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth, type Role } from "@/lib/auth";
import Logo from "./Logo";

const I = (d: ReactNode) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
const ICONS: Record<string, ReactNode> = {
  home: I(<><path d="M3 11 12 3l9 8" /><path d="M5 10v10h14V10" /></>),
  acct: I(<><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M7 15h4" /></>),
  tx: I(<><path d="M4 7h13l-3-3M20 17H7l3 3" /></>),
  budget: I(<><circle cx="12" cy="12" r="9" /><path d="M12 12V3M12 12l6 6" /></>),
  goal: I(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></>),
  debt: I(<><path d="M12 3v18M17 7H9.5a2.500 2.500 0 0 0 0 5h5a2.500 2.500 0 0 1 0 5H7" /></>),
  invest: I(<><path d="M3 20h18M6 16l4-5 3 3 5-7" /></>),
  income: I(<><path d="M12 19V5M6 11l6-6 6 6" /><path d="M5 21h14" /></>),
  repeat: I(<><path d="M17 2l4 4-4 4" /><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4" /><path d="M21 13v2a3 3 0 0 1-3 3H3" /></>),
  bulb: I(<><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.500c.700.700 1 1.500 1 2.500h6c0-1 .300-1.800 1-2.500A6 6 0 0 0 12 3Z" /></>),
  tax: I(<><path d="M7 3h8l4 4v14H7z" /><path d="M14 3v5h5M10 13h6M10 17h4" /></>),
  gear: I(<><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.200 4.200l2.100 2.100M17.700 17.700l2.100 2.100M2 12h3M19 12h3M4.200 19.800l2.100-2.100M17.700 6.300l2.100-2.100" /></>),
  org: I(<><rect x="3" y="3" width="7" height="9" rx="1.500" /><rect x="14" y="3" width="7" height="5" rx="1.500" /><rect x="14" y="12" width="7" height="9" rx="1.500" /><rect x="3" y="16" width="7" height="5" rx="1.500" /></>),
  fraud: I(<><path d="M12 3 20 6v6c0 5-3.500 8-8 9-4.500-1-8-4-8-9V6Z" /><path d="M12 8v5M12 16v.01" /></>),
  models: I(<><path d="M3 20h18M6 16l4-5 3 3 5-7" /></>),
  seg: I(<><circle cx="8" cy="9" r="3" /><circle cx="17" cy="8" r="2.200" /><path d="M2.500 19c.5-3.500 3-5 5.500-5s5 1.500 5.500 5M15 14.500c3 0 5 1.300 5.500 4.500" /></>),
  users: I(<><circle cx="12" cy="8" r="3.500" /><path d="M5 20c.8-4 3.500-6 7-6s6.200 2 7 6" /></>),
  audit: I(<><path d="M7 3h8l4 4v14H7z" /><path d="M14 3v5h5M10 13h6M10 17h6" /></>),
};

type Item = [href: string, label: string, icon: string, roles: Role[]];
const ALL: Role[] = ["customer", "analyst", "admin"];
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "My money", items: [
    ["/finance", "Overview", "home", ALL], ["/finance/accounts", "Accounts", "acct", ALL], ["/finance/transactions", "Transactions", "tx", ALL],
    ["/finance/budgets", "Budgets", "budget", ALL], ["/finance/goals", "Goals", "goal", ALL], ["/finance/debts", "Debts", "debt", ALL],
    ["/finance/investments", "Investments", "invest", ALL], ["/finance/income", "Income", "income", ALL], ["/finance/recurring", "Recurring", "repeat", ALL],
    ["/finance/insights", "Insights", "bulb", ALL], ["/finance/tax", "Tax summary", "tax", ALL], ["/finance/settings", "Settings", "gear", ALL],
  ] },
  { title: "Analytics", items: [
    ["/org", "Organization", "org", ["analyst", "admin"]], ["/fraud", "Fraud review", "fraud", ["analyst", "admin"]],
    ["/models", "Model comparison", "models", ["analyst", "admin"]], ["/customers", "Customer segments", "seg", ["analyst", "admin"]],
  ] },
  { title: "Administration", items: [
    ["/admin/operations", "Operations", "gear", ["admin"]], ["/admin/users", "Users", "users", ["admin"]], ["/admin/audit", "Audit log", "audit", ["admin"]],
  ] },
];

export default function Nav() {
  const path = usePathname();
  const { me, logout } = useAuth();
  return (
    <aside className="side" aria-label="Sidebar">
      <Logo />
      <span className="badge">Synthetic data</span>
      {me && (
        <>
          <nav aria-label="Main" style={{ display: "contents" }}>
            {GROUPS.map((g) => {
              const items = g.items.filter(([, , , r]) => r.includes(me.role));
              if (!items.length) return null;
              return (
                <div key={g.title} style={{ display: "contents" }}>
                  <h5>{g.title}</h5>
                  {items.map(([h, l, ic]) => (
                    <Link key={h} href={h} className="link" aria-current={path === h ? "page" : undefined}>{ICONS[ic]}{l}</Link>
                  ))}
                </div>
              );
            })}
          </nav>
          <div className="user">
            <div><b>{me.email}</b><span className="rolepill">{me.role}</span></div>
            <button onClick={logout}>Sign out</button>
          </div>
        </>
      )}
    </aside>
  );
}
