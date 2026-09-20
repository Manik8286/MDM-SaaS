import Link from "next/link";
import {
  Shield,
  CheckCircle,
  ArrowRight,
  Monitor,
  ShieldCheck,
  ScrollText,
  QrCode,
  Lock,
  Zap,
  KeyRound,
} from "lucide-react";

const FEATURES = [
  {
    icon: Monitor,
    title: "Apple MDM enrollment & remote actions",
    description: "Enroll Mac devices, push config profiles, lock, wipe, and query devices — all from one console.",
  },
  {
    icon: KeyRound,
    title: "Microsoft Entra ID + Platform SSO",
    description: "Built-in support for macOS PSSO with Entra — passwordless sign-in and auto-provisioned Mac accounts.",
  },
  {
    icon: ShieldCheck,
    title: "Compliance & patch management",
    description: "Enforce security policies, track OS and patch status, and flag non-compliant devices automatically.",
  },
  {
    icon: ScrollText,
    title: "Full audit trail",
    description: "Every command, profile push, and config change is logged and exportable for security review.",
  },
  {
    icon: Lock,
    title: "Config profiles & policies",
    description: "Build and deploy configuration profiles and device policies to groups of devices at once.",
  },
  {
    icon: QrCode,
    title: "Fast self-serve enrollment",
    description: "Generate enrollment links or QR codes so users and IT can enroll devices in minutes.",
  },
];

const PLANS = [
  {
    key: "starter" as const,
    name: "Starter",
    price: 199,
    devices: 25,
    features: ["25 devices", "Entra SSO / PSSO", "Compliance reporting", "Email support"],
    highlighted: false,
  },
  {
    key: "professional" as const,
    name: "Professional",
    price: 499,
    devices: 100,
    features: ["100 devices", "Everything in Starter", "Audit log export", "Priority support"],
    highlighted: true,
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-white">
      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/90 backdrop-blur">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield size={20} className="text-zinc-900" />
            <span className="font-semibold text-zinc-900">MDM Console</span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm text-zinc-600">
            <a href="#features" className="hover:text-zinc-900 transition-colors">Features</a>
            <a href="#pricing" className="hover:text-zinc-900 transition-colors">Pricing</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm font-medium text-zinc-600 hover:text-zinc-900 transition-colors">
              Sign in
            </Link>
            <Link
              href="/signup"
              className="text-sm font-medium text-white bg-zinc-900 rounded-lg px-4 py-2 hover:bg-zinc-700 transition-colors"
            >
              Start free trial
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <section className="bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 py-24 text-center">
          <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight max-w-3xl mx-auto">
            Manage every Mac device from one console
          </h1>
          <p className="mt-5 text-lg text-zinc-400 max-w-2xl mx-auto">
            Built for IT teams that ship fast. Enroll devices, enforce compliance, and push
            Microsoft Entra SSO — without the enterprise MDM price tag.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/signup"
              className="flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 transition-colors"
            >
              Start your 5-day free trial <ArrowRight size={16} />
            </Link>
            <a
              href="#pricing"
              className="flex items-center gap-2 rounded-lg border border-zinc-700 px-6 py-3 text-sm font-medium text-white hover:bg-zinc-800 transition-colors"
            >
              View pricing
            </a>
          </div>
          <p className="mt-4 text-xs text-zinc-500">Card required · billed after 5 days · cancel anytime</p>
        </div>
      </section>

      {/* ── Features ────────────────────────────────────────────────────── */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-12">
          <h2 className="text-2xl font-semibold text-zinc-900">Everything you need to manage devices</h2>
          <p className="mt-2 text-sm text-zinc-500">One dashboard for enrollment, compliance, and security.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map(({ icon: Icon, title, description }) => (
            <div key={title} className="rounded-xl border border-zinc-200 p-6 hover:border-zinc-300 transition-colors">
              <div className="w-9 h-9 rounded-lg bg-zinc-900 flex items-center justify-center mb-4">
                <Icon size={16} className="text-white" />
              </div>
              <h3 className="text-sm font-semibold text-zinc-900 mb-1.5">{title}</h3>
              <p className="text-sm text-zinc-500 leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Pricing ─────────────────────────────────────────────────────── */}
      <section id="pricing" className="bg-zinc-50 border-y border-zinc-200">
        <div className="max-w-6xl mx-auto px-6 py-20">
          <div className="text-center mb-12">
            <h2 className="text-2xl font-semibold text-zinc-900">Simple, per-device pricing</h2>
            <p className="mt-2 text-sm text-zinc-500">
              Every plan starts with a 5-day free trial. Card required upfront — you&apos;re only billed if you keep it.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-4xl mx-auto lg:max-w-none">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`rounded-xl border bg-white p-6 flex flex-col ${
                  plan.highlighted ? "border-zinc-900 ring-1 ring-zinc-900" : "border-zinc-200"
                }`}
              >
                {plan.highlighted && (
                  <span className="self-start mb-3 text-xs font-medium text-white bg-zinc-900 rounded-full px-2.5 py-1">
                    Most popular
                  </span>
                )}
                <h3 className="text-base font-semibold text-zinc-900">{plan.name}</h3>
                <p className="mt-2 flex items-baseline gap-1">
                  <span className="text-3xl font-bold text-zinc-900">${plan.price}</span>
                  <span className="text-sm text-zinc-400">/month</span>
                </p>
                <ul className="mt-5 space-y-2 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-zinc-600">
                      <CheckCircle size={14} className="text-green-500 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/signup?plan=${plan.key}`}
                  className={`mt-6 flex items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
                    plan.highlighted
                      ? "bg-zinc-900 text-white hover:bg-zinc-700"
                      : "border border-zinc-300 text-zinc-900 hover:bg-zinc-50"
                  }`}
                >
                  <Zap size={14} /> Start free trial
                </Link>
              </div>
            ))}

            {/* Enterprise */}
            <div className="rounded-xl border border-zinc-200 bg-white p-6 flex flex-col">
              <h3 className="text-base font-semibold text-zinc-900">Enterprise</h3>
              <p className="mt-2 text-3xl font-bold text-zinc-900">Custom</p>
              <ul className="mt-5 space-y-2 flex-1">
                {["Unlimited devices", "Custom SLA", "SSO", "Dedicated support"].map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-zinc-600">
                    <CheckCircle size={14} className="text-green-500 flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <a
                href="mailto:sales@strativon.click"
                className="mt-6 flex items-center justify-center gap-1.5 rounded-lg border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-900 hover:bg-zinc-50 transition-colors"
              >
                Contact sales
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ── Final CTA ───────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-20 text-center">
        <h2 className="text-2xl font-semibold text-zinc-900">Ready to get your fleet under management?</h2>
        <p className="mt-2 text-sm text-zinc-500">Set up your first device in minutes.</p>
        <Link
          href="/signup"
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-6 py-3 text-sm font-semibold text-white hover:bg-zinc-700 transition-colors"
        >
          Start your 5-day free trial <ArrowRight size={16} />
        </Link>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-zinc-200">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-zinc-500 text-sm">
            <Shield size={16} />
            <span>MDM Console</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-zinc-400">
            <Link href="/terms" className="hover:text-zinc-600 transition-colors">Terms</Link>
            <Link href="/privacy" className="hover:text-zinc-600 transition-colors">Privacy</Link>
            <span>© {new Date().getFullYear()} MDM Console. All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
