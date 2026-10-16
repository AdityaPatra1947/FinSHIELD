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
  org: I(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>),
  spend: I(<><path d="M4 19V9M10 19V5M16 19v-7M22 19H2" /></>),
  tx: I(<><path d="M4 7h13l-3-3M20 17H7l3 3" /></>),
  fraud: I(<><path d="M12 3 20 6v6c0 5-3.500 8-8 9-4.500-1-8-4-8-9V6Z" /><path d="M12 8v5M12 16v.01" /></>),
  models: I(<><path d="M3 20h18M6 16l4-5 3 3 5-7" /></>),
  seg: I(<><circle cx="8" cy="9" r="3" /><circle cx="17" cy="8" r="2.200" /><path d="M2.500 19c.5-3.500 3-5 5.500-5s5 1.500 5.500 5M15 14.500c3 0 5 1.300 5.500 4.500" /></>),
  ops: I(<><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.200 4.200l2.100 2.100M17.700 17.700l2.100 2.100M2 12h3M19 12h3M4.200 19.800l2.100-2.100M17.700 6.300l2.100-2.100" /></>),
  users: I(<><circle cx="12" cy="8" r="3.500" /><path d="M5 20c.8-4 3.500-6 7-6s6.200 2 7 6" /></>),
  audit: I(<><path d="M7 3h8l4 4v14H7z" /><path d="M14 3v5h5M10 13h6M10 17h6" /></>),
};

type Item = [href: string, label: string, icon: string, roles: Role[]];
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Workspace", items: [
    ["/dashboard", "Spending", "spend", ["customer", "analyst", "admin"]],
    ["/transactions", "Transactions", "tx", ["customer", "analyst", "admin"]],
  ] },
  { title: "Insights", items: [
    ["/org", "Organization", "org", ["analyst", "admin"]],
    ["/fraud", "Fraud review", "fraud", ["analyst", "admin"]],
    ["/models", "Model comparison", "models", ["analyst", "admin"]],
    ["/customers", "Customer segments", "seg", ["analyst", "admin"]],
  ] },
  { title: "Administration", items: [
    ["/admin/operations", "Operations", "ops", ["admin"]],
    ["/admin/users", "Users", "users", ["admin"]],
    ["/admin/audit", "Audit log", "audit", ["admin"]],
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
