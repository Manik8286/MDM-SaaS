"use client";

import { useEffect, useState } from "react";
import { getTenant, updateTenant, pushPsso, setApiUrl, getApiUrl, type TenantInfo } from "@/lib/api";
import { Save, Send, CheckCircle, Globe } from "lucide-react";

export default function SettingsPage() {
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  // Entra config form
  const [entraTenantId, setEntraTenantId] = useState("");
  const [entraClientId, setEntraClientId] = useState("");

  // API URL
  const [apiUrlInput, setApiUrlInput] = useState("");
  const [apiUrlSaved, setApiUrlSaved] = useState(false);

  // PSSO push form
  const [authMethod, setAuthMethod] = useState("UserSecureEnclaveKey");
  const [createUser, setCreateUser] = useState(true);
  const [registrationToken, setRegistrationToken] = useState("");
  const [adminGroups, setAdminGroups] = useState("");
  const [pushing, setPushing] = useState(false);
  const [pushResult, setPushResult] = useState<{ queued: number } | null>(null);
  const [pushError, setPushError] = useState("");

  useEffect(() => {
    setApiUrlInput(getApiUrl());
  }, []);

  useEffect(() => {
    getTenant()
      .then((t) => {
        setTenant(t);
        setEntraTenantId(t.entra_tenant_id ?? "");
        setEntraClientId(t.entra_client_id ?? "");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSaveEntra(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const updated = await updateTenant({
        entra_tenant_id: entraTenantId || undefined,
        entra_client_id: entraClientId || undefined,
      });
      setTenant(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handlePushPsso(e: React.FormEvent) {
    e.preventDefault();
    setPushing(true);
    setPushResult(null);
    setPushError("");
    try {
      const groups = adminGroups.trim()
        ? adminGroups.split(",").map((s) => s.trim()).filter(Boolean)
        : undefined;
      const result = await pushPsso({
        auth_method: authMethod,
        enable_create_user_at_login: createUser,
        registration_token: registrationToken || undefined,
        admin_groups: groups,
      });
      setPushResult(result);
    } catch (err: unknown) {
      setPushError(err instanceof Error ? err.message : "Push failed");
    } finally {
      setPushing(false);
    }
  }

  if (loading) {
    return <div className="p-8 text-zinc-400">Loading…</div>;
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Settings</h1>
      <p className="text-sm text-zinc-500 mb-8">
        Tenant: <span className="font-medium text-zinc-700">{tenant?.name}</span>
      </p>

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── API Server URL ───────────────────────────────────────────────── */}
      <section className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
        <h2 className="text-sm font-semibold text-zinc-900 mb-1 flex items-center gap-2">
          <Globe size={14} /> API Server
        </h2>
        <p className="text-xs text-zinc-500 mb-4">
          Change this if you are accessing the dashboard from a different machine on the same network.
          Use <code className="bg-zinc-100 px-1 rounded">http://&lt;host-ip&gt;:8000</code>.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={apiUrlInput}
            onChange={(e) => setApiUrlInput(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-mono text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
          />
          <button
            type="button"
            onClick={() => {
              setApiUrl(apiUrlInput);
              setApiUrlSaved(true);
              setTimeout(() => setApiUrlSaved(false), 2000);
            }}
            className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 transition-colors"
          >
            <Save size={14} />
            Apply
          </button>
        </div>
        {apiUrlSaved && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-green-600">
            <CheckCircle size={12} /> Saved — reload the page to re-fetch data
          </p>
        )}
        <div className="mt-3 flex gap-2">
          {[
            { label: "Production", url: "https://mdm.strativon.click" },
            { label: "Local", url: typeof window !== "undefined" ? `http://${window.location.hostname}:8000` : "http://localhost:8000" },
          ].map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => setApiUrlInput(preset.url)}
              className="text-xs rounded-md border border-zinc-200 px-2 py-1 text-zinc-600 hover:bg-zinc-50 font-mono"
            >
              {preset.label}: {preset.url}
            </button>
          ))}
        </div>
      </section>

      {/* ── Microsoft Entra ID config ─────────────────────────────────────── */}
      <section className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
        <h2 className="text-sm font-semibold text-zinc-900 mb-1">Microsoft Entra ID</h2>
        <p className="text-xs text-zinc-500 mb-4">
          Configure your Azure AD / Entra app registration to enable SSO login and PSSO profile push.
          The client secret must be set in the server <code className="bg-zinc-100 px-1 rounded">.env</code> as{" "}
          <code className="bg-zinc-100 px-1 rounded">ENTRA_CLIENT_SECRET</code>.
        </p>

        <form onSubmit={handleSaveEntra} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              Entra Tenant ID (Directory ID)
            </label>
            <input
              type="text"
              value={entraTenantId}
              onChange={(e) => setEntraTenantId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm font-mono text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-zinc-400">
              Found in Azure Portal → Entra ID → Overview → Directory (tenant) ID
            </p>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              Client ID (Application ID)
            </label>
            <input
              type="text"
              value={entraClientId}
              onChange={(e) => setEntraClientId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm font-mono text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-zinc-400">
              Found in Azure Portal → App registrations → your app → Application (client) ID
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              <Save size={14} />
              {saving ? "Saving…" : "Save"}
            </button>
            {saved && (
              <span className="flex items-center gap-1.5 text-sm text-green-600">
                <CheckCircle size={14} />
                Saved
              </span>
            )}
          </div>
        </form>
      </section>

      {/* ── PSSO profile push ────────────────────────────────────────────── */}
      <section className="bg-white rounded-xl border border-zinc-200 p-6">
        <h2 className="text-sm font-semibold text-zinc-900 mb-1">Push PSSO Profile</h2>
        <p className="text-xs text-zinc-500 mb-4">
          Build and push a macOS Platform SSO configuration profile to all enrolled devices.
          This installs the Microsoft Entra SSO extension on the Mac.
        </p>

        <form onSubmit={handlePushPsso} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              Authentication Method
            </label>
            <select
              value={authMethod}
              onChange={(e) => setAuthMethod(e.target.value)}
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900"
            >
              <option value="UserSecureEnclaveKey">UserSecureEnclaveKey (recommended — passwordless)</option>
              <option value="Password">Password</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="create-user"
              checked={createUser}
              onChange={(e) => setCreateUser(e.target.checked)}
              className="rounded border-zinc-300"
            />
            <label htmlFor="create-user" className="text-sm text-zinc-700">
              Enable create user at login (auto-provision Mac account from Entra)
            </label>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              Registration Token <span className="text-zinc-400">(optional)</span>
            </label>
            <input
              type="text"
              value={registrationToken}
              onChange={(e) => setRegistrationToken(e.target.value)}
              placeholder="Token from Entra portal for PSSO registration"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-zinc-400">
              Azure Portal → Entra ID → Devices → macOS Platform Single Sign-on → Create token
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              Admin Groups <span className="text-zinc-400">(optional, comma-separated)</span>
            </label>
            <input
              type="text"
              value={adminGroups}
              onChange={(e) => setAdminGroups(e.target.value)}
              placeholder="IT Admins, DevOps"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-zinc-400">
              Members of these groups get local admin rights on the Mac
            </p>
          </div>

          {pushError && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {pushError}
            </div>
          )}

          {pushResult && (
            <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
              PSSO profile queued for <strong>{pushResult.queued}</strong> device{pushResult.queued !== 1 ? "s" : ""}.
              Devices will receive it on next check-in.
            </div>
          )}

          <button
            type="submit"
            disabled={pushing}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            <Send size={14} />
            {pushing ? "Pushing…" : "Push to all enrolled devices"}
          </button>
        </form>
      </section>

      {/* ── Setup guide ─────────────────────────────────────────────────── */}
      <section className="mt-6 rounded-xl border border-zinc-200 bg-zinc-50 p-6 text-sm text-zinc-600 space-y-3">
        <h3 className="font-semibold text-zinc-800">Entra + PSSO setup guide</h3>
        <ol className="list-decimal list-inside space-y-1.5 text-xs leading-relaxed">
          <li>In Azure Portal, go to <strong>Entra ID → App registrations → New registration</strong></li>
          <li>Set redirect URI to: <code className="bg-white border border-zinc-200 px-1 rounded">
            {typeof window !== "undefined" ? `${process.env.NEXT_PUBLIC_API_URL || "http://192.168.64.1:8000"}/api/v1/auth/sso/entra/callback` : "…/api/v1/auth/sso/entra/callback"}
          </code></li>
          <li>Copy the <strong>Application (client) ID</strong> and <strong>Directory (tenant) ID</strong> above</li>
          <li>Under <strong>Certificates & secrets</strong>, create a client secret and add it to your <code className="bg-white border border-zinc-200 px-1 rounded">.env</code> as <code className="bg-white border border-zinc-200 px-1 rounded">ENTRA_CLIENT_SECRET</code></li>
          <li>Restart the backend container: <code className="bg-white border border-zinc-200 px-1 rounded">docker compose restart app</code></li>
          <li>For PSSO: go to <strong>Entra ID → Devices → macOS Platform Single Sign-on</strong> and create a registration token</li>
          <li>Paste the token above and click <strong>Push to all enrolled devices</strong></li>
          <li>On each Mac, open <strong>System Settings → Privacy & Security → Profiles</strong> to verify the profile was installed</li>
        </ol>
      </section>
    </div>
  );
}
