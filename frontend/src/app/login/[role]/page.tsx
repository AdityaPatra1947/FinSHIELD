import { notFound } from "next/navigation";
import LoginForm from "@/components/LoginForm";
import type { Role } from "@/lib/auth";

const ROLES: Role[] = ["customer", "analyst", "admin"];

export default async function RoleLogin({ params }: { params: Promise<{ role: string }> }) {
  const { role } = await params;
  if (!ROLES.includes(role as Role)) notFound();
  return <LoginForm role={role as Role} />;
}
