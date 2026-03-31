"use client";

import { useEffect, useState } from "react";
import { getAuditLogs, type AuditLog } from "@/lib/api";
import { RefreshCw } from "lucide-react";

const ACTION_COLORS: Record<string, string> = {
  "device.lock":    "bg-orange-100 text-orange-700",
  "device.erase":   "bg-red-100 text-red-700",
  "device.restart": "bg-yellow-100 text-yellow-700",
  "device.query":   "bg-blue-100 text-blue-700",
  "device.delete":  "bg-red-100 text-red-700",
  "auth.login":     "bg-green-100 text-green-700",
  "profile.psso_push": "bg-purple-100 text-purple-700",
};

function ActionBadge({ action }: { action: string }) {
  const cls = ACTION_COLORS[action] ?? "bg-zinc-100 text-zinc-600";
  const label = action.replace(".", " · ");
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

const RESOURCE_TYPES = ["", "device", "user", "profile"];
const ACTIONS = [
  "", "device.lock", "device.erase", "device.restart",
  "device.query", "device.delete", "auth.login", "profile.psso_push",
];

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [action, setAction] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await getAuditLogs({
        resource_type: resourceType || undefined,
        action: action || undefined,
        limit: 200,
      });
      setLogs(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [resourceType, action]);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Audit Log</h1>
          <p className="text-sm text-zinc-500 mt-0.5">{logs.length} events</p>
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

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <select
          value={resourceType}
          onChange={(e) => setResourceType(e.target.value)}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-900"
        >
          <option value="">All resources</option>
          {RESOURCE_TYPES.filter(Boolean).map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-900"
        >
          <option value="">All actions</option>
          {ACTIONS.filter(Boolean).map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
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
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Time</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Action</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Actor</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Resource</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">IP</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-zinc-400">Loading…</td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-zinc-400">No audit events yet</td>
              </tr>
            ) : (
              logs.map((l) => (
                <>
                  <tr
                    key={l.id}
                    className="hover:bg-zinc-50 transition-colors cursor-pointer"
                    onClick={() => setExpanded(expanded === l.id ? null : l.id)}
                  >
                    <td className="px-4 py-3">
                      <span className="text-zinc-700" title={formatDate(l.created_at)}>
                        {timeAgo(l.created_at)}
                      </span>
                      <div className="text-xs text-zinc-400">{formatDate(l.created_at)}</div>
                    </td>
                    <td className="px-4 py-3"><ActionBadge action={l.action} /></td>
                    <td className="px-4 py-3 text-zinc-600">{l.actor_email ?? <span className="text-zinc-300">system</span>}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-zinc-500">{l.resource_type}</span>
                      {l.resource_id && (
                        <div className="text-xs text-zinc-400 font-mono">{l.resource_id.slice(0, 8)}…</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-400 text-xs font-mono">{l.ip_address ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-zinc-400">
                      {l.changes
                        ? Object.entries(l.changes)
                            .filter(([k]) => k !== "command_uuid")
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(" · ") || "—"
                        : "—"}
                    </td>
                  </tr>
                  {expanded === l.id && l.changes && (
                    <tr key={`${l.id}-expanded`} className="bg-zinc-50">
                      <td colSpan={6} className="px-4 py-3">
                        <pre className="text-xs text-zinc-600 bg-white border border-zinc-200 rounded-lg p-3 overflow-x-auto">
                          {JSON.stringify(l.changes, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
