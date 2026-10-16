"use client";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { homeFor, useAuth, type Role } from "@/lib/auth";
import Logo from "./Logo";

const COPY: Record<string, { title: string; blurb: string; hint: string }> = {
  any: { title: "Welcome back", blurb: "Sign in to your FinShield workspace. You'll land where your role belongs.", hint: "" },
  customer: { title: "Customer sign-in", blurb: "See your spending, refunds and cash wallet — and add transactions of your own.", hint: "Customer accounts only." },
  analyst: { title: "Analyst sign-in", blurb: "Review flagged transactions, compare the three fraud models and explore customer segments.", hint: "Analyst accounts only." },
  admin: { title: "Admin sign-in", blurb: "Run training jobs, promote or roll back models, manage users and read the audit log.", hint: "Administrator accounts only." },
};

export default function LoginForm({ role }: { role?: Role }) {
  const { me, loading, login, logout } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const copy = COPY[role ?? "any"];

  useEffect(() => {
    if (!loading && me && (!role || me.role === role)) router.replace(homeFor(me.role));
  }, [loading, me, role, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(email, password);
      if (role && u.role !== role) {
        await logout();
        setError(`That account is a ${u.role} account. Use the ${u.role} sign-in instead.`);
        return;
      }
      router.replace(homeFor(u.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  const tabs: [string, string, string][] = [["/login", "Any", "any"], ["/login/customer", "Customer", "customer"], ["/login/analyst", "Analyst", "analyst"], ["/login/admin", "Admin", "admin"]];
  const current = role ?? "any";

  return (
    <div className="signin">
      <aside className="signin-art">
        <svg className="bg" viewBox="0 0 400 700" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          {Array.from({ length: 26 }, (_, i) => (
            <circle key={i} cx={(i * 97) % 380 + 10} cy={(i * 211) % 680 + 10} r={i % 5 === 0 ? 5 : 2.5} fill="#EAE6DE" />
          ))}
          <path d="M40 620 C140 560 220 600 360 470" fill="none" stroke="#EF8557" strokeWidth="2.5" />
          <circle cx="360" cy="470" r="7" fill="#EF8557" />
        </svg>
        <Logo />
        <div>
          <h2>{role ? <>{role}<br />desk</> : <>Sign in<br />to see<br />the signal</>}</h2>
          <p>{copy.blurb}</p>
        </div>
        <small style={{ color: "#cfe0ee" }}>Synthetic data · educational project · no real money moves</small>
      </aside>
      <section className="signin-form">
        <form onSubmit={submit}>
          <div className="tabs" role="navigation" aria-label="Choose sign-in type">
            {tabs.map(([h, l, k]) => <Link key={h} href={h} aria-current={current === k ? "page" : undefined}>{l}</Link>)}
          </div>
          <h1>{copy.title}</h1>
          {copy.hint && <p className="muted small" style={{ margin: 0 }}>{copy.hint}</p>}
          <label>Email<input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {error && <p role="alert" className="err" style={{ margin: 0 }}>{error}</p>}
          <button type="submit" className="btn" disabled={busy} style={{ justifyContent: "center", color: "#fff", background: "var(--blue)" }}>{busy ? "Signing in…" : "Sign in →"}</button>
          <p className="small muted" style={{ margin: 0 }}>Demo accounts are created during setup; the passwords are in <code>artifacts/demo_credentials.txt</code>. <Link href="/">← Back to home</Link></p>
        </form>
      </section>
    </div>
  );
}
