"use client";
import { useState, type FormEvent } from "react";
import { api, useApi } from "@/lib/api";
import { RoleGate } from "@/lib/auth";
import { Card, PageHead, State } from "@/components/ui";

type U = { id: string; email: string; role: string; customer_id: number | null; active: boolean; last_login_at: number | null };

function UsersInner() {
  const [bump, setBump] = useState(0);
  const users = useApi<{ items: U[] }>("/admin/users", [bump]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("customer");
  const [cid, setCid] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const r = await api<{ email: string; initial_password: string }>("/admin/users", { method: "POST", body: JSON.stringify({ email, role, customer_id: role === "customer" ? Number(cid) : null }) });
      setMsg({ ok: true, text: `Created ${r.email}. One-time password (shown once, only a hash is stored): ${r.initial_password}` });
      setEmail(""); setCid(""); setBump((b) => b + 1);
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
  }
  async function patch(id: string, body: object, label: string) {
    setMsg(null);
    try {
      const r = await api<{ new_password?: string }>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });
      setMsg({ ok: true, text: r.new_password ? `${label}. New one-time password: ${r.new_password}` : `${label}.` });
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
    setBump((b) => b + 1);
  }
  return (
    <>
      <PageHead eyebrow="Administration" title="Users">Create accounts, deactivate them, or reset a password. Only Argon2id hashes are stored.</PageHead>
      {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "note" : "note err"}>{msg.text}</p>}
      <Card title="Create user" note="Passwords are generated server-side and displayed once; only an Argon2id hash is stored.">
        <form onSubmit={create} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
          <label>Email<br /><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Role<br /><select value={role} onChange={(e) => setRole(e.target.value)}><option>customer</option><option>analyst</option><option>admin</option></select></label>
          {role === "customer" && <label>Customer ID<br /><input type="number" min={1} max={600} required value={cid} onChange={(e) => setCid(e.target.value)} style={{ width: 90 }} /></label>}
          <button type="submit">Create</button>
        </form>
      </Card>
      <Card title="Accounts">
        <State loading={users.loading && !users.data} error={users.error}>
          <div className="scroll"><table><thead><tr><th>Email</th><th>Role</th><th>Customer</th><th>Active</th><th>Last login</th><th></th></tr></thead><tbody>
            {users.data?.items.map((u) => (
              <tr key={u.id}><td>{u.email}</td><td>{u.role}</td><td>{u.customer_id ?? "—"}</td><td>{u.active ? "yes" : "no"}</td>
                <td>{u.last_login_at ? new Date(u.last_login_at * 1000).toLocaleString() : "never"}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button onClick={() => patch(u.id, { active: !u.active }, u.active ? "Deactivated" : "Activated")}>{u.active ? "Deactivate" : "Activate"}</button>{" "}
                  <button onClick={() => patch(u.id, { reset_password: true }, "Password reset, sessions revoked")}>Reset password</button></td></tr>))}
          </tbody></table></div>
        </State>
      </Card>
    </>
  );
}

export default function Users() {
  return <RoleGate allow={["admin"]}><UsersInner /></RoleGate>;
}
