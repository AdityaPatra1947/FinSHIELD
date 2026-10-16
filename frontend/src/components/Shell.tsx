"use client";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import Nav from "./Nav";
import { isPublicPath } from "@/lib/auth";

/** Public pages (landing, sign-in) are full-bleed; app pages get the sidebar and content column. */
export default function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  if (isPublicPath(path)) return <>{children}</>;
  return (
    <div className="app">
      <Nav />
      <main className="content">{children}</main>
    </div>
  );
}
