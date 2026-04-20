"use client";

import { useEffect, useState } from "react";
import { getTenant, updateTenant, pushPsso, setApiUrl, getApiUrl, setup2fa, enable2fa, disable2fa, getTenantUsage, getBillingStatus, getPlans, startCheckout, openBillingPortal, type TenantInfo, type TenantUsage, type BillingStatus, type Plan } from "@/lib/api";
import { Save, Send, CheckCircle, Globe, ShieldCheck, ShieldOff, Monitor, Activity, HardDrive, CreditCard, Zap, ArrowUpRight } from "lucide-react";

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

  // Usage state
  const [usage, setUsage] = useState<TenantUsage | null>(null);

  // Billing state
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  // 2FA state
  const [totpSetup, setTotpSetup] = useState<{ secret: string; otpauth_url: string; qr_svg: string } | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [totpMsg, setTotpMsg] = useState("");
  const [totpLoading, setTotpLoading] = useState(false);
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [disableCode, setDisableCode] = useState("");

  useEffect(() => {
    setApiUrlInput(getApiUrl());
  }, []);

  useEffect(() => {
    Promise.all([getTenant(), getTenantUsage(), getBillingStatus(), getPlans()])
      .then(([t, u, b, p]) => {
        setTenant(t);
        setUsage(u);
        setBilling(b);
        setPlans(p);
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

      {/* ── Usage overview ──────────────────────────────────────────────── */}
      {usage && (
        <section className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
          <h2 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
            <Activity size={14} /> Usage Overview
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
              <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
                <Monitor size={11} /> Devices
              </div>
              <p className="text-2xl font-semibold text-zinc-900">{usage.total_devices}</p>
              <p className="text-xs text-zinc-400 mt-0.5">
                {usage.enrolled_devices} enrolled · {usage.pending_devices} pending
              </p>
            </div>
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
              <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
                <Activity size={11} /> Commands (30d)
              </div>
              <p className="text-2xl font-semibold text-zinc-900">{usage.commands_last_30_days}</p>
              <p className="text-xs text-zinc-400 mt-0.5">{usage.commands_queued} queued</p>
            </div>
            <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
              <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
                <HardDrive size={11} /> Storage
              </div>
              <p className="text-2xl font-semibold text-zinc-900">{usage.storage_used_mb} MB</p>
              <p className="text-xs text-zinc-400 mt-0.5">software packages</p>
            </div>
          </div>
        </section>
      )}

      {/* ── Billing ─────────────────────────────────────────────────────── */}
      {billing && (
        <section className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
          <h2 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
            <CreditCard size={14} /> Plan &amp; Billing
          </h2>

          {/* Current plan banner */}
          <div className={`rounded-lg px-4 py-3 mb-5 flex items-center justify-between ${
            billing.billing_status === "active" ? "bg-green-50 border border-green-200" :
            billing.billing_status === "past_due" ? "bg-red-50 border border-red-200" :
            "bg-amber-50 border border-amber-200"
          }`}>
            <div>
              <p className={`text-sm font-semibold ${
                billing.billing_status === "active" ? "text-green-800" :
                billing.billing_status === "past_due" ? "text-red-800" : "text-amber-800"
              }`}>
                {billing.plan_name} plan
                <span className="ml-2 text-xs font-normal opacity-75">
                  {billing.billing_status === "trialing"
                    ? `Trial · ${billing.trial_ends_at ? Math.max(0, Math.ceil((new Date(billing.trial_ends_at).getTime() - Date.now()) / 86400000)) : 0} days left`
                    : billing.billing_status === "past_due" ? "Payment past due"
                    : billing.billing_status === "canceled" ? "Canceled"
                    : "Active"}
                </span>
              </p>
              <p className="text-xs opacity-60 mt-0.5">
                {billing.device_limit} device limit · {billing.features.join(" · ")}
              </p>
            </div>
            {billing.has_stripe && (
              <button
                onClick={() => openBillingPortal()}
                className="flex items-center gap-1.5 text-xs font-medium text-zinc-600 hover:text-zinc-900 border border-zinc-300 rounded-lg px-3 py-1.5 hover:bg-white transition-colors"
              >
                <ArrowUpRight size={12} /> Manage
              </button>
            )}
          </div>

          {/* Upgrade plans — only show if not on professional/enterprise */}
          {billing.plan !== "professional" && billing.plan !== "enterprise" && (
            <div className="grid grid-cols-2 gap-4">
              {plans.filter(p => p.price_monthly && p.price_monthly > 0 && p.name !== "Enterprise").map((plan) => {
                const key = plan.name.toLowerCase() as "starter" | "professional";
                const isCurrent = billing.plan_name === plan.name;
                return (
                  <div key={plan.name} className={`rounded-xl border p-4 ${isCurrent ? "border-zinc-900 bg-zinc-50" : "border-zinc-200"}`}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-semibold text-zinc-900">{plan.name}</p>
                      <p className="text-sm font-semibold text-zinc-900">
                        ${plan.price_monthly}<span className="text-xs font-normal text-zinc-400">/mo</span>
                      </p>
                    </div>
                    <ul className="space-y-1 mb-4">
                      {plan.features.map((f) => (
                        <li key={f} className="flex items-center gap-1.5 text-xs text-zinc-500">
                          <CheckCircle size={10} className="text-green-500 flex-shrink-0" />
                          {f}
                        </li>
                      ))}
                    </ul>
                    <button
                      disabled={isCurrent || checkoutLoading === key}
                      onClick={async () => {
                        setCheckoutLoading(key);
                        try { await startCheckout(key); }
                        catch { setCheckoutLoading(null); }
                      }}
                      className={`flex items-center justify-center gap-1.5 w-full rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                        isCurrent
                          ? "bg-zinc-900 text-white cursor-default"
                          : "bg-zinc-900 text-white hover:bg-zinc-700"
                      } disabled:opacity-50`}
                    >
                      {checkoutLoading === key ? "Redirecting…" : isCurrent ? "Current plan" : <><Zap size={11} /> Upgrade</>}
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {billing.trial_expired && (
            <p className="mt-4 text-xs text-red-600 font-medium">
              Your trial has expired. Upgrade to continue enrolling devices.
            </p>
          )}
        </section>
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

      {/* ── Two-Factor Authentication ────────────────────────────────────── */}
      <section className="bg-white rounded-xl border border-zinc-200 p-6 mt-6">
        <h2 className="text-sm font-semibold text-zinc-900 mb-1 flex items-center gap-2">
          <ShieldCheck size={14} /> Two-Factor Authentication
        </h2>
        <p className="text-xs text-zinc-500 mb-4">
          Protect your account with a TOTP authenticator app (Google Authenticator, Authy, 1Password, etc.).
        </p>

        {totpMsg && (
          <div className="mb-4 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
            {totpMsg}
          </div>
        )}

        {totpEnabled ? (
          <div>
            <div className="flex items-center gap-2 mb-4 text-sm text-green-700 font-medium">
              <ShieldCheck size={16} /> 2FA is enabled
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">Enter TOTP code to disable</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value)}
                  placeholder="000000"
                  className="w-40 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-mono text-center focus:outline-none focus:ring-2 focus:ring-red-500"
                />
                <button
                  onClick={async () => {
                    setTotpLoading(true);
                    try {
                      await disable2fa(disableCode);
                      setTotpEnabled(false);
                      setDisableCode("");
                      setTotpMsg("2FA has been disabled.");
                    } catch (e: unknown) {
                      setTotpMsg(e instanceof Error ? e.message : "Failed to disable 2FA");
                    } finally {
                      setTotpLoading(false);
                    }
                  }}
                  disabled={totpLoading || disableCode.length < 6}
                  className="rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  {totpLoading ? "…" : "Disable 2FA"}
                </button>
              </div>
            </div>
          </div>
        ) : totpSetup ? (
          <div>
            <p className="text-xs text-zinc-600 mb-3">
              Scan this QR code with your authenticator app, then enter the 6-digit code to activate 2FA.
            </p>
            <div
              className="mb-4 w-48 h-48 border border-zinc-200 rounded-lg overflow-hidden bg-white"
              dangerouslySetInnerHTML={{ __html: totpSetup.qr_svg }}
            />
            <p className="text-xs text-zinc-400 font-mono mb-4 break-all">
              Manual: {totpSetup.secret}
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                placeholder="000000"
                className="w-36 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-mono text-center focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button
                onClick={async () => {
                  setTotpLoading(true);
                  try {
                    await enable2fa(totpCode);
                    setTotpEnabled(true);
                    setTotpSetup(null);
                    setTotpCode("");
                    setTotpMsg("2FA enabled successfully!");
                  } catch (e: unknown) {
                    setTotpMsg(e instanceof Error ? e.message : "Invalid code");
                  } finally {
                    setTotpLoading(false);
                  }
                }}
                disabled={totpLoading || totpCode.length < 6}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {totpLoading ? "Activating…" : "Activate 2FA"}
              </button>
              <button
                onClick={() => { setTotpSetup(null); setTotpCode(""); }}
                className="rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-2 mb-4 text-sm text-zinc-500">
              <ShieldOff size={16} /> 2FA is not enabled
            </div>
            <button
              onClick={async () => {
                setTotpLoading(true);
                setTotpMsg("");
                try {
                  const data = await setup2fa();
                  setTotpSetup(data);
                } catch (e: unknown) {
                  setTotpMsg(e instanceof Error ? e.message : "Setup failed");
                } finally {
                  setTotpLoading(false);
                }
              }}
              disabled={totpLoading}
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <ShieldCheck size={14} /> {totpLoading ? "Setting up…" : "Set up 2FA"}
            </button>
          </div>
        )}
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
