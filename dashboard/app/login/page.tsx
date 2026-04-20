"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setToken, setApiUrl, getApiUrl, login, validate2fa } from "@/lib/api";

function getDevUrl() {
  if (typeof window === "undefined") return "http://localhost:8000";
  return `http://${window.location.hostname}:8000`;
}

const ENVIRONMENTS = [
  { label: "Production", url: "https://mdm.strativon.click" },
  { label: "Local", url: "" }, // resolved at runtime via getDevUrl()
];

function MicrosoftIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
      <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
    </svg>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [apiUrl, setApiUrlState] = useState(ENVIRONMENTS[0].url);

  // 2FA state
  const [step, setStep] = useState<"login" | "password" | "2fa">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tempToken, setTempToken] = useState("");
  const [totpCode, setTotpCode] = useState("");

  useEffect(() => {
    ENVIRONMENTS[1].url = getDevUrl();
    setApiUrlState(getApiUrl());
  }, []);

  function handleEnvChange(url: string) {
    setApiUrlState(url);
    setApiUrl(url);
  }

  // Handle SSO redirect: /login?token=... or /login?error=...
  useEffect(() => {
    const token = searchParams.get("token");
    const err = searchParams.get("error");
    if (token) {
      setToken(token);
      router.replace("/devices");
    } else if (err === "not_authorized") {
      setError("Your Microsoft account is not authorised to access this dashboard. Contact your administrator to be added.");
    } else if (err === "no_tenant") {
      setError("Your Microsoft account is not linked to any MDM tenant. Contact your administrator.");
    } else if (err === "inactive") {
      setError("Your account is inactive. Contact your administrator.");
    }
  }, [searchParams, router]);

  function handleMicrosoftLogin() {
    setLoading(true);
    const origin = encodeURIComponent(window.location.origin);
    window.location.href = `${apiUrl}/api/v1/auth/sso/entra/login?dashboard_origin=${origin}`;
  }

  async function handlePasswordLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await login(email, password);
      if (res.requires_2fa && res.temp_token) {
        setTempToken(res.temp_token);
        setStep("2fa");
      } else if (res.access_token) {
        setToken(res.access_token);
        router.replace("/devices");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handle2faSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await validate2fa(tempToken, totpCode.replace(/\s/g, ""));
      setToken(res.access_token);
      router.replace("/devices");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid code");
      setTotpCode("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-zinc-200 p-8">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-zinc-900">MDM Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-500">Sign in to manage your devices</p>
        </div>

        {/* Environment selector */}
        <div className="mb-6">
          <label className="block text-xs font-medium text-zinc-500 mb-1.5 uppercase tracking-wide">
            Environment
          </label>
          <div className="flex rounded-lg border border-zinc-200 overflow-hidden">
            {ENVIRONMENTS.map((env) => (
              <button
                key={env.label}
                type="button"
                onClick={() => handleEnvChange(env.url)}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  apiUrl === env.url
                    ? "bg-zinc-900 text-white"
                    : "bg-white text-zinc-600 hover:bg-zinc-50"
                }`}
              >
                {env.label}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-zinc-400 font-mono truncate">{apiUrl}</p>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">{error}</p>
        )}

        {/* Step: 2FA TOTP */}
        {step === "2fa" ? (
          <form onSubmit={handle2faSubmit} className="space-y-4">
            <div className="text-center mb-2">
              <div className="w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-zinc-800">Two-Factor Authentication</p>
              <p className="text-xs text-zinc-500 mt-1">Enter the 6-digit code from your authenticator app</p>
            </div>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9 ]*"
              maxLength={7}
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              placeholder="000 000"
              autoFocus
              className="w-full rounded-lg border border-zinc-300 px-4 py-3 text-center text-2xl font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="submit"
              disabled={loading || totpCode.replace(/\s/g, "").length < 6}
              className="w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              onClick={() => { setStep("password"); setTotpCode(""); setError(""); }}
              className="w-full text-xs text-zinc-400 hover:text-zinc-600"
            >
              ← Back to login
            </button>
          </form>
        ) : step === "password" ? (
          /* Step: email + password login */
          <form onSubmit={handlePasswordLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
            <button
              type="button"
              onClick={() => { setStep("login"); setError(""); }}
              className="w-full text-xs text-zinc-400 hover:text-zinc-600"
            >
              ← Back
            </button>
          </form>
        ) : (
          /* Step: default — Microsoft SSO or password */
          <div className="space-y-3">
            <button
              type="button"
              onClick={handleMicrosoftLogin}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 rounded-lg bg-[#0078D4] hover:bg-[#106EBE] px-4 py-3 text-sm font-medium text-white transition-colors disabled:opacity-50"
            >
              <MicrosoftIcon />
              {loading ? "Redirecting…" : "Sign in with Microsoft"}
            </button>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-zinc-200" />
              </div>
              <div className="relative flex justify-center text-xs text-zinc-400">
                <span className="bg-white px-2">or</span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setStep("password")}
              className="w-full rounded-lg border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              Sign in with password
            </button>
          </div>
        )}

        <p className="mt-4 text-center text-xs text-zinc-400">
          Authenticate with your organisation&apos;s Microsoft Entra ID account
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
