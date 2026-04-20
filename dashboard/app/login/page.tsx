"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setToken, setApiUrl, getApiUrl } from "@/lib/api";

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

  useEffect(() => {
    // Resolve the local dev URL now that window is available
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
          <p className="mt-1.5 text-xs text-zinc-400 font-mono truncate">
            {apiUrl}
          </p>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">
            {error}
          </p>
        )}

        {/* Microsoft SSO — primary and only sign-in method */}
        <button
          type="button"
          onClick={handleMicrosoftLogin}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 rounded-lg bg-[#0078D4] hover:bg-[#106EBE] px-4 py-3 text-sm font-medium text-white transition-colors disabled:opacity-50"
        >
          <MicrosoftIcon />
          {loading ? "Redirecting…" : "Sign in with Microsoft"}
        </button>

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
