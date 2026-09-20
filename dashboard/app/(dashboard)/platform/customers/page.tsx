"use client";

import { useEffect, useState } from "react";
import { getPlatformTenants, type PlatformTenant } from "@/lib/api";
import { ExternalLink } from "lucide-react";

const BILLING_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  trialing: "bg-blue-100 text-blue-700",
  past_due: "bg-amber-100 text-amber-700",
  canceled: "bg-red-100 text-red-700",
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  suspended: "bg-red-100 text-red-700",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function PlatformCustomersPage() {
  const [tenants, setTenants] = useState<PlatformTenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getPlatformTenants()
      .then(setTenants)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load customers"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-zinc-400">Loading…</div>;

  const totalMrr = tenants.filter((t) => t.billing_status === "active").length;

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-xl font-semibold text-zinc-900 mb-1">Customers</h1>
      <p className="text-sm text-zinc-500 mb-8">
        Every tenant on the platform, across all organizations — not scoped to your own company.
      </p>

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-zinc-200 p-4">
          <div className="text-xs text-zinc-500 mb-1">Total customers</div>
          <div className="text-2xl font-semibold text-zinc-900">{tenants.length}</div>
        </div>
        <div className="bg-white rounded-xl border border-zinc-200 p-4">
          <div className="text-xs text-zinc-500 mb-1">Paying (active billing)</div>
          <div className="text-2xl font-semibold text-zinc-900">{totalMrr}</div>
        </div>
        <div className="bg-white rounded-xl border border-zinc-200 p-4">
          <div className="text-xs text-zinc-500 mb-1">Trialing</div>
          <div className="text-2xl font-semibold text-zinc-900">
            {tenants.filter((t) => t.billing_status === "trialing").length}
          </div>
        </div>
      </div>

      <section className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 text-xs font-medium text-zinc-500 uppercase tracking-wide">
              <th className="px-5 py-3 text-left">Customer</th>
              <th className="px-5 py-3 text-left">Plan</th>
              <th className="px-5 py-3 text-left">Billing</th>
              <th className="px-5 py-3 text-left">Devices</th>
              <th className="px-5 py-3 text-left">Users</th>
              <th className="px-5 py-3 text-left">Trial ends</th>
              <th className="px-5 py-3 text-left">Created</th>
              <th className="px-5 py-3 text-left">Stripe</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-50">
            {tenants.map((t) => (
              <tr key={t.id} className="hover:bg-zinc-50">
                <td className="px-5 py-3">
                  <div className="font-medium text-zinc-900">{t.name}</div>
                  <div className="text-xs text-zinc-400 font-mono">{t.slug}</div>
                </td>
                <td className="px-5 py-3 text-zinc-700 capitalize">{t.plan}</td>
                <td className="px-5 py-3">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${BILLING_COLORS[t.billing_status] ?? "bg-zinc-100 text-zinc-500"}`}>
                    {t.billing_status}
                  </span>
                  {t.status !== "active" && (
                    <span className={`ml-1 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[t.status] ?? "bg-zinc-100 text-zinc-500"}`}>
                      {t.status}
                    </span>
                  )}
                </td>
                <td className="px-5 py-3 text-zinc-700">
                  {t.device_count} / {t.plan_device_limit}
                </td>
                <td className="px-5 py-3 text-zinc-700">{t.user_count}</td>
                <td className="px-5 py-3 text-zinc-500">{formatDate(t.trial_ends_at)}</td>
                <td className="px-5 py-3 text-zinc-500">{formatDate(t.created_at)}</td>
                <td className="px-5 py-3">
                  {t.stripe_customer_id ? (
                    <a
                      href={`https://dashboard.stripe.com/customers/${t.stripe_customer_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-900 font-mono"
                    >
                      {t.stripe_customer_id} <ExternalLink size={12} />
                    </a>
                  ) : (
                    <span className="text-xs text-zinc-300">—</span>
                  )}
                </td>
              </tr>
            ))}
            {tenants.length === 0 && (
              <tr>
                <td colSpan={8} className="px-5 py-8 text-center text-zinc-400 text-sm">
                  No customers yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
