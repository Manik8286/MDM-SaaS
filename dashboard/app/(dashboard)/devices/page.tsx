"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getDevices, queryDevice, type Device } from "@/lib/api";
import { RefreshCw, ChevronRight, ShieldCheck, ShieldAlert, ShieldOff } from "lucide-react";

const statusColors: Record<string, string> = {
  enrolled: "bg-green-100 text-green-800",
  pending: "bg-yellow-100 text-yellow-800",
  unenrolled: "bg-zinc-100 text-zinc-600",
};

function StatusBadge({ status }: { status: string }) {
  const cls = statusColors[status] ?? "bg-zinc-100 text-zinc-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function ComplianceBadge({ status }: { status: string }) {
  if (status === "compliant") return <span title="Compliant"><ShieldCheck size={14} className="text-green-600" /></span>;
  if (status === "non_compliant") return <span title="Non-compliant"><ShieldAlert size={14} className="text-red-500" /></span>;
  return <span title="Unknown"><ShieldOff size={14} className="text-zinc-300" /></span>;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [querying, setQuerying] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setDevices(await getDevices());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load devices");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleQuery(id: string) {
    setQuerying(id);
    try {
      await queryDevice(id);
    } finally {
      setQuerying(null);
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Devices</h1>
          <p className="text-sm text-zinc-500 mt-0.5">{devices.length} enrolled</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50">
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Device</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Serial</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">OS</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Status</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Last seen</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">PSSO</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Compliance</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-zinc-400">Loading…</td>
              </tr>
            ) : devices.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-zinc-400">No devices enrolled yet</td>
              </tr>
            ) : (
              devices.map((d) => (
                <tr key={d.id} className="hover:bg-zinc-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-medium text-zinc-900">{d.hostname ?? d.udid.slice(0, 8)}</div>
                    <div className="text-xs text-zinc-400">{d.model ?? d.platform}</div>
                  </td>
                  <td className="px-4 py-3 text-zinc-600 font-mono text-xs">{d.serial_number ?? "—"}</td>
                  <td className="px-4 py-3 text-zinc-600">{d.os_version ?? "—"}</td>
                  <td className="px-4 py-3"><StatusBadge status={d.status} /></td>
                  <td className="px-4 py-3 text-zinc-500">{timeAgo(d.last_checkin)}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${d.psso_status === "active" ? "text-green-700" : "text-zinc-400"}`}>
                      {d.psso_status ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <ComplianceBadge status={d.compliance_status ?? "unknown"} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleQuery(d.id)}
                        disabled={querying === d.id}
                        className="rounded px-2 py-1 text-xs font-medium text-zinc-600 hover:bg-zinc-100 disabled:opacity-50 transition-colors"
                        title="Query device info"
                      >
                        {querying === d.id ? "…" : "Query"}
                      </button>
                      <Link
                        href={`/devices/${d.id}`}
                        className="text-zinc-400 hover:text-zinc-900 transition-colors"
                      >
                        <ChevronRight size={16} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
