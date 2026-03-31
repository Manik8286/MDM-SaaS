"use client";

import { useEffect, useState } from "react";
import { getProfiles, pushProfile, pushPsso, type Profile, type PssoOptions } from "@/lib/api";
import { RefreshCw, Send, Shield } from "lucide-react";

const typeLabels: Record<string, string> = {
  psso: "Platform SSO",
  wifi: "Wi-Fi",
  vpn: "VPN",
  custom: "Custom",
};

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [pushing, setPushing] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [showPsso, setShowPsso] = useState(false);
  const [pssoForm, setPssoForm] = useState<PssoOptions>({
    auth_method: "UserSecureEnclaveKey",
    enable_create_user_at_login: true,
  });
  const [pssoLoading, setPssoLoading] = useState(false);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  async function load() {
    setLoading(true);
    try {
      setProfiles(await getProfiles());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handlePush(id: string) {
    setPushing(id);
    try {
      const res = await pushProfile(id);
      showToast(`Pushed to ${res.queued} device(s)`);
    } catch (err: unknown) {
      showToast(`Error: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setPushing(null);
    }
  }

  async function handlePushPsso(e: React.FormEvent) {
    e.preventDefault();
    setPssoLoading(true);
    try {
      const res = await pushPsso(pssoForm);
      showToast(`PSSO pushed to ${res.queued} device(s)`);
      setShowPsso(false);
    } catch (err: unknown) {
      showToast(`Error: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setPssoLoading(false);
    }
  }

  return (
    <div className="p-8">
      {toast && (
        <div className="fixed top-4 right-4 z-50 rounded-lg bg-zinc-900 text-white text-sm px-4 py-2 shadow-lg">
          {toast}
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Profiles</h1>
          <p className="text-sm text-zinc-500 mt-0.5">{profiles.length} profiles</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPsso(true)}
            className="flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 transition-colors"
          >
            <Shield size={14} />
            Push PSSO
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50">
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Name</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Type</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Platform</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Created</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-zinc-400">Loading…</td>
              </tr>
            ) : profiles.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-zinc-400">No profiles yet</td>
              </tr>
            ) : (
              profiles.map((p) => (
                <tr key={p.id} className="hover:bg-zinc-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-zinc-900">{p.name}</td>
                  <td className="px-4 py-3 text-zinc-600">{typeLabels[p.type] ?? p.type}</td>
                  <td className="px-4 py-3 text-zinc-600">{p.platform}</td>
                  <td className="px-4 py-3 text-zinc-500">{new Date(p.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handlePush(p.id)}
                      disabled={pushing === p.id}
                      className="flex items-center gap-1.5 ml-auto rounded px-2.5 py-1.5 text-xs font-medium bg-zinc-900 text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
                    >
                      <Send size={11} />
                      {pushing === p.id ? "Pushing…" : "Push to all"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* PSSO modal */}
      {showPsso && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-base font-semibold text-zinc-900 mb-4">Push Platform SSO (Entra ID)</h2>
            <form onSubmit={handlePushPsso} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-1">Auth Method</label>
                <select
                  value={pssoForm.auth_method}
                  onChange={(e) => setPssoForm({ ...pssoForm, auth_method: e.target.value })}
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900"
                >
                  <option value="UserSecureEnclaveKey">Secure Enclave Key (recommended)</option>
                  <option value="Password">Password</option>
                </select>
              </div>

              <div className="flex items-center gap-3">
                <input
                  id="create-user"
                  type="checkbox"
                  checked={pssoForm.enable_create_user_at_login}
                  onChange={(e) => setPssoForm({ ...pssoForm, enable_create_user_at_login: e.target.checked })}
                  className="h-4 w-4 rounded border-zinc-300"
                />
                <label htmlFor="create-user" className="text-sm text-zinc-700">
                  Create user account at first login
                </label>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-1">
                  Registration Token <span className="text-zinc-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={pssoForm.registration_token ?? ""}
                  onChange={(e) => setPssoForm({ ...pssoForm, registration_token: e.target.value || undefined })}
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 font-mono"
                  placeholder="From Microsoft Entra ID portal"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-1">
                  Admin Groups <span className="text-zinc-400 font-normal">(comma-separated, optional)</span>
                </label>
                <input
                  type="text"
                  value={pssoForm.admin_groups?.join(", ") ?? ""}
                  onChange={(e) => {
                    const groups = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                    setPssoForm({ ...pssoForm, admin_groups: groups.length ? groups : undefined });
                  }}
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900"
                  placeholder="IT Admins, DevOps"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowPsso(false)}
                  className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={pssoLoading}
                  className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
                >
                  {pssoLoading ? "Pushing…" : "Push PSSO Profile"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
