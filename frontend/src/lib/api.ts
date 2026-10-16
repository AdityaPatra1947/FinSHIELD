"use client";
import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public fields?: Record<string, string>) {
    super(message);
  }
}

function cookie(name: string): string {
  const m = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
  return m ? decodeURIComponent(m.split("=")[1]) : "";
}

export async function api<T>(path: string, init: RequestInit & { csrf?: string } = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as Record<string, string>) };
  if (method !== "GET") headers["X-CSRF-Token"] = init.csrf ?? cookie("fs_csrf");
  const res = await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let msg = `Request failed (${res.status})`, code: string | undefined, fields: Record<string, string> | undefined;
    try {
      const j = await res.json();
      const e = j?.detail?.error || j?.error;
      if (e) { msg = e.message || msg; code = e.code; fields = e.fields; }
    } catch {}
    if (res.status === 401 && path !== "/auth/login" && path !== "/auth/me" && typeof window !== "undefined")
      window.dispatchEvent(new Event("fs-unauth"));
    throw new ApiError(res.status, msg, code, fields);
  }
  return res.json();
}

/** Failed queries surface as errors - never as zero values. */
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setLoading(true);
    setError(null);
    api<T>(path)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  return { data, error, loading };
}
