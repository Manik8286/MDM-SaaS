"use client";

import { useEffect, useState } from "react";
import { listUsers, createUser, updateUser, deleteUser, type DashboardUser } from "@/lib/api";
import { UserPlus, Trash2, ShieldCheck, ShieldOff } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
};

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-purple-100 text-purple-700",
  admin: "bg-blue-100 text-blue-700",
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  inactive: "bg-zinc-100 text-zinc-500",
};

export default function UsersPage() {
  const [users, setUsers] = useState<DashboardUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Add user form
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("admin");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      setUsers(await listUsers());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setAddError("");
    try {
      const u = await createUser(email.trim(), role);
      setUsers((prev) => [...prev, u]);
      setEmail("");
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Failed to add user");
    } finally {
      setAdding(false);
    }
  }

  async function toggleStatus(user: DashboardUser) {
    const newStatus = user.status === "active" ? "inactive" : "active";
    try {
      const updated = await updateUser(user.id, { status: newStatus });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function changeRole(user: DashboardUser, newRole: string) {
    try {
      const updated = await updateUser(user.id, { role: newRole });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function handleDelete(user: DashboardUser) {
    if (!confirm(`Remove ${user.email}? They will lose dashboard access immediately.`)) return;
    try {
      await deleteUser(user.id);
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (loading) return <div className="p-8 text-zinc-400">Loading…</div>;

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Team Access</h1>
      <p className="text-sm text-zinc-500 mb-8">
        Add colleagues who can sign in to this dashboard with their Microsoft Entra account.
      </p>

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Add user */}
      <section className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
        <h2 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
          <UserPlus size={14} /> Add person
        </h2>
        <form onSubmit={handleAdd} className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              Work email (Entra account)
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@yourcompany.com"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900"
            >
              <option value="admin">Admin</option>
              <option value="owner">Owner</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={adding}
            className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
          >
            <UserPlus size={14} />
            {adding ? "Adding…" : "Add"}
          </button>
        </form>
        {addError && (
          <p className="mt-2 text-sm text-red-600">{addError}</p>
        )}
        <p className="mt-3 text-xs text-zinc-400">
          The person can sign in immediately using <strong>Sign in with Microsoft</strong> on the login page — no password needed.
        </p>
      </section>

      {/* User list */}
      <section className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 text-xs font-medium text-zinc-500 uppercase tracking-wide">
              <th className="px-5 py-3 text-left">Email</th>
              <th className="px-5 py-3 text-left">Role</th>
              <th className="px-5 py-3 text-left">Status</th>
              <th className="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-50">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-zinc-50">
                <td className="px-5 py-3 font-mono text-zinc-800 text-xs">{u.email}</td>
                <td className="px-5 py-3">
                  <select
                    value={u.role}
                    onChange={(e) => changeRole(u, e.target.value)}
                    className={`rounded-md px-2 py-0.5 text-xs font-medium border-0 cursor-pointer focus:ring-2 focus:ring-zinc-900 focus:outline-none ${ROLE_COLORS[u.role] ?? "bg-zinc-100 text-zinc-600"}`}
                  >
                    <option value="admin">Admin</option>
                    <option value="owner">Owner</option>
                  </select>
                </td>
                <td className="px-5 py-3">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[u.status] ?? "bg-zinc-100 text-zinc-500"}`}>
                    {u.status}
                  </span>
                </td>
                <td className="px-5 py-3 text-right">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => toggleStatus(u)}
                      title={u.status === "active" ? "Deactivate" : "Activate"}
                      className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
                    >
                      {u.status === "active" ? <ShieldOff size={14} /> : <ShieldCheck size={14} />}
                    </button>
                    <button
                      onClick={() => handleDelete(u)}
                      title="Remove"
                      className="p-1.5 rounded-md text-zinc-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-zinc-400 text-sm">
                  No users yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
