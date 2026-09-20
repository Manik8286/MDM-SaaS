"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { signup, setToken, startCheckout, setApiUrl, getApiUrl } from "@/lib/api";
import { Shield, CheckCircle, Loader2, Settings, CreditCard } from "lucide-react";

function getDevUrl() {
  if (typeof window === "undefined") return "http://localhost:8000";
  return `http://${window.location.hostname}:8000`;
}

const TRIAL_FEATURES = [
  "5-day free trial on any plan",
  "Apple MDM enrollment & remote actions",
  "Microsoft Entra ID + PSSO",
  "Compliance & patch management",
  "Cancel anytime during the trial",
];

const PLAN_OPTIONS = [
  { key: "starter" as const, name: "Starter", price: 199, devices: 25 },
  { key: "professional" as const, name: "Professional", price: 499, devices: 100 },
];

function SignupForm() {
  const searchParams = useSearchParams();
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [plan, setPlan] = useState<"starter" | "professional">("starter");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [apiUrlInput, setApiUrlInput] = useState("");
  const [showApiConfig, setShowApiConfig] = useState(false);

  useEffect(() => { setApiUrlInput(getApiUrl()); }, []);

  useEffect(() => {
    const requested = searchParams.get("plan");
    if (requested === "starter" || requested === "professional") {
      setPlan(requested);
    }
  }, [searchParams]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await signup(orgName, email, password, plan);
      setToken(result.access_token);
      // Account is created but locked (no devices) until Stripe confirms
      // the card — send the browser straight to hosted Checkout to start
      // the 5-day trial.
      await startCheckout(plan);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Signup failed");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 flex">
      {/* Left — value prop */}
      <div className="hidden lg:flex lg:w-1/2 bg-zinc-900 flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-white" />
          <span className="text-white font-semibold text-lg">MDM Console</span>
        </div>

        <div>
          <h1 className="text-3xl font-bold text-white leading-tight mb-4">
            Manage every Mac and Windows device<br />from one console.
          </h1>
          <p className="text-zinc-400 text-sm mb-8">
            Built for IT teams that ship fast. Enroll devices, enforce compliance,
            push Entra SSO — all from a single dashboard.
          </p>
          <ul className="space-y-3">
            {TRIAL_FEATURES.map((f) => (
              <li key={f} className="flex items-center gap-3 text-sm text-zinc-300">
                <CheckCircle size={16} className="text-green-400 flex-shrink-0" />
                {f}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-zinc-600">
          Already have an account?{" "}
          <Link href="/login" className="text-zinc-400 hover:text-white transition-colors">
            Sign in →
          </Link>
        </p>
      </div>

      {/* Right — signup form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <Shield size={20} className="text-zinc-900" />
            <span className="font-semibold text-zinc-900">MDM Console</span>
          </div>

          <div className="flex items-center justify-between mb-1">
            <h2 className="text-xl font-semibold text-zinc-900">Start your free trial</h2>
            <button onClick={() => setShowApiConfig(!showApiConfig)}
              className="text-xs text-zinc-400 hover:text-zinc-600 flex items-center gap-1">
              <Settings size={11} /> API
            </button>
          </div>
          <p className="text-sm text-zinc-500 mb-4">5 days free, then billed monthly · cancel anytime</p>

          {showApiConfig && (
            <div className="mb-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2">
              <p className="text-xs font-medium text-zinc-600">API Server</p>
              <input
                type="text"
                value={apiUrlInput}
                onChange={(e) => setApiUrlInput(e.target.value)}
                className="w-full rounded border border-zinc-300 px-2 py-1.5 text-xs font-mono text-zinc-800 focus:outline-none focus:ring-1 focus:ring-zinc-400"
              />
              <div className="flex gap-2">
                {[{ label: "Local", url: getDevUrl() }, { label: "Production", url: "https://mdm.strativon.click" }].map(p => (
                  <button key={p.label} type="button"
                    onClick={() => { setApiUrlInput(p.url); setApiUrl(p.url); }}
                    className="text-xs rounded border border-zinc-200 px-2 py-1 text-zinc-500 hover:bg-white">
                    {p.label}
                  </button>
                ))}
                <button type="button"
                  onClick={() => { setApiUrl(apiUrlInput); setShowApiConfig(false); }}
                  className="ml-auto text-xs rounded bg-zinc-900 text-white px-2 py-1 hover:bg-zinc-700">
                  Apply
                </button>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-700 mb-2">
                Choose a plan
              </label>
              <div className="grid grid-cols-2 gap-2">
                {PLAN_OPTIONS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => setPlan(p.key)}
                    className={`text-left rounded-lg border px-3 py-2 transition-colors ${
                      plan === p.key
                        ? "border-zinc-900 bg-zinc-50 ring-1 ring-zinc-900"
                        : "border-zinc-200 hover:border-zinc-300"
                    }`}
                  >
                    <p className="text-sm font-semibold text-zinc-900">{p.name}</p>
                    <p className="text-xs text-zinc-500">
                      ${p.price}/mo · {p.devices} devices
                    </p>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-700 mb-1">
                Organisation name
              </label>
              <input
                type="text"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Acme Corp"
                required
                autoFocus
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-700 mb-1">
                Work email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-700 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                required
                minLength={8}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <CreditCard size={14} />}
              {loading ? "Redirecting to secure checkout…" : "Continue to payment"}
            </button>
          </form>

          <p className="mt-4 text-xs text-zinc-400 text-center">
            You&apos;ll enter your card on Stripe&apos;s secure checkout. Nothing is charged for 5 days —
            cancel anytime before then and you won&apos;t be billed. By continuing you agree to our{" "}
            <Link href="/terms" className="underline hover:text-zinc-600">Terms of Service</Link> and{" "}
            <Link href="/privacy" className="underline hover:text-zinc-600">Privacy Policy</Link>.
          </p>

          <p className="mt-6 text-sm text-zinc-500 text-center">
            Already have an account?{" "}
            <Link href="/login" className="text-zinc-900 font-medium hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function SignupPage() {
  return (
    <Suspense>
      <SignupForm />
    </Suspense>
  );
}
