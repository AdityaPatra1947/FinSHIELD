"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError } from "./api";

export type Role = "customer" | "analyst" | "admin";
export type Me = { id: string; email: string; role: Role; customer_id: number | null };

type Ctx = { me: Me | null; loading: boolean; login: (e: string, p: string) => Promise<Me>; logout: () => Promise<void> };
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const useAuth = () => useContext(AuthCtx);
export const homeFor = (r: Role) => (r === "customer" ? "/dashboard" : "/org");
export const isPublicPath = (p: string | null) => p === "/" || (p ?? "").startsWith("/login");

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [down, setDown] = useState(false);
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    api<Me>("/auth/me").then(setMe)
      .catch((e) => { if (e instanceof ApiError && e.status === 401) setMe(null); else setDown(true); })
      .finally(() => setLoading(false));
    const h = () => setMe(null);
    window.addEventListener("fs-unauth", h);
    return () => window.removeEventListener("fs-unauth", h);
  }, []);

  useEffect(() => {
    if (!loading && !down && !me && !isPublicPath(path)) router.replace("/login");
  }, [loading, down, me, path, router]);

  const login = useCallback(async (email: string, password: string) => {
    const { csrf_token } = await api<{ csrf_token: string }>("/auth/csrf");
    const u = await api<Me>("/auth/login", { method: "POST", csrf: csrf_token, body: JSON.stringify({ email, password }) });
    setMe(u);
    return u;
  }, []);
  const logout = useCallback(async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch {}
    setMe(null);
    router.replace("/login");
  }, [router]);

  if (down) return <p role="alert" className="err" style={{ padding: 24 }}>The FinShield API is unavailable. Check that the backend is running, then <a href="">reload</a>.</p>;
  return <AuthCtx.Provider value={{ me, loading, login, logout }}>{children}</AuthCtx.Provider>;
}

/** Client-side convenience only; the server enforces every permission. */
export function RoleGate({ allow, children }: { allow: Role[]; children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <p role="status">Loading…</p>;
  if (!me) return null;
  if (!allow.includes(me.role)) return <p role="alert" className="err">Your role ({me.role}) cannot view this page.</p>;
  return <>{children}</>;
}
