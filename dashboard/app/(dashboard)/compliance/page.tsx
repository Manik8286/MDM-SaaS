"use client";

import React, { useEffect, useState } from "react";
import {
  getComplianceSummary, getCompliancePolicies, evaluatePolicy, downloadComplianceReport,
  type FleetSummary, type CompliancePolicy,
} from "@/lib/api";
import { RefreshCw, ShieldCheck, ShieldAlert, ShieldOff, ChevronDown, ChevronUp, Play, Download } from "lucide-react";

const FRAMEWORK_LABELS: Record<string, string> = {
  iso27001: "ISO 27001",
  pci_dss: "PCI DSS v4",
  custom: "Custom",
};

const FRAMEWORK_COLORS: Record<string, string> = {
  iso27001: "bg-blue-100 text-blue-800",
  pci_dss: "bg-purple-100 text-purple-800",
  custom: "bg-zinc-100 text-zinc-700",
};

function StatusBadge({ status }: { status: string }) {
  if (status === "compliant") return (
    <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-green-100 text-green-800">
      <ShieldCheck size={12} /> Compliant
    </span>
  );
  if (status === "non_compliant") return (
    <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-red-100 text-red-800">
      <ShieldAlert size={12} /> Non-compliant
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-zinc-100 text-zinc-600">
      <ShieldOff size={12} /> Unknown
    </span>
  );
}

function RuleRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex justify-between text-xs py-1 border-b border-zinc-50 last:border-0">
      <span className="text-zinc-600">{label}</span>
      <span className="font-mono text-zinc-800">{String(value)}</span>
    </div>
  );
}

function PolicyCard({ policy, onEvaluate }: { policy: CompliancePolicy; onEvaluate: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [running, setRunning] = useState(false);

  async function handleEvaluate() {
    setRunning(true);
    try { await onEvaluate(policy.id); } finally { setRunning(false); }
  }

  const ruleLabels: Record<string, string> = {
    filevault_required: "FileVault encryption",
    firewall_required: "Firewall enabled",
    gatekeeper_required: "Gatekeeper enabled",
    max_checkin_age_hours: "Max check-in age (hours)",
    critical_updates_allowed: "Critical updates allowed",
    psso_required: "Platform SSO required",
    screen_lock_required: "Screen lock required",
  };

  return (
    <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
      <div className="px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${FRAMEWORK_COLORS[policy.framework] ?? FRAMEWORK_COLORS.custom}`}>
            {FRAMEWORK_LABELS[policy.framework] ?? policy.framework}
          </span>
          <div>
            <h3 className="font-medium text-zinc-900">{policy.name}</h3>
            {policy.description && <p className="text-xs text-zinc-400 mt-0.5">{policy.description}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleEvaluate}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-zinc-900 text-white rounded-lg hover:bg-zinc-700 disabled:opacity-50"
          >
            <Play size={11} /> {running ? "Running…" : "Evaluate"}
          </button>
          <button onClick={() => setExpanded(!expanded)} className="p-1.5 text-zinc-400 hover:text-zinc-700">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>
      {expanded && (
        <div className="px-5 pb-4 border-t border-zinc-100">
          <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider mt-3 mb-2">Rules</p>
          {Object.entries(policy.rules).map(([k, v]) => (
            <RuleRow key={k} label={ruleLabels[k] ?? k} value={v} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CompliancePage() {
  const [summary, setSummary] = useState<FleetSummary | null>(null);
  const [policies, setPolicies] = useState<CompliancePolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [s, p] = await Promise.all([getComplianceSummary(), getCompliancePolicies()]);
      setSummary(s);
      setPolicies(p);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleEvaluate(policyId: string) {
    await evaluatePolicy(policyId);
    await load();
  }

  const compliantPct = summary && summary.total_devices > 0
    ? Math.round((summary.compliant / summary.total_devices) * 100)
    : 0;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Compliance</h1>
          <p className="text-sm text-zinc-400 mt-0.5">ISO 27001 &amp; PCI DSS device compliance</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={async () => { setExporting(true); try { await downloadComplianceReport(); } finally { setExporting(false); } }}
            disabled={exporting}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-white border border-zinc-200 rounded-lg hover:bg-zinc-50 disabled:opacity-50"
          >
            <Download size={14} /> {exporting ? "Exporting…" : "Export CSV"}
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-white border border-zinc-200 rounded-lg hover:bg-zinc-50 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
      )}

      {/* Fleet summary cards */}
      {summary && (
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-white border border-zinc-200 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Total Devices</p>
            <p className="text-3xl font-bold text-zinc-900 mt-1">{summary.total_devices}</p>
          </div>
          <div className="bg-white border border-zinc-200 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Compliant</p>
            <p className="text-3xl font-bold text-green-600 mt-1">{summary.compliant}</p>
          </div>
          <div className="bg-white border border-zinc-200 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Non-Compliant</p>
            <p className="text-3xl font-bold text-red-500 mt-1">{summary.non_compliant}</p>
          </div>
          <div className="bg-white border border-zinc-200 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Compliance Rate</p>
            <p className={`text-3xl font-bold mt-1 ${compliantPct >= 80 ? "text-green-600" : "text-red-500"}`}>
              {compliantPct}%
            </p>
          </div>
        </div>
      )}

      {/* Compliance bar */}
      {summary && summary.total_devices > 0 && (
        <div className="mb-8 bg-white border border-zinc-200 rounded-xl p-5">
          <p className="text-sm font-medium text-zinc-700 mb-3">Fleet Compliance Overview</p>
          <div className="flex h-4 rounded-full overflow-hidden gap-0.5">
            {summary.compliant > 0 && (
              <div
                className="bg-green-500 transition-all"
                style={{ width: `${(summary.compliant / summary.total_devices) * 100}%` }}
                title={`${summary.compliant} compliant`}
              />
            )}
            {summary.non_compliant > 0 && (
              <div
                className="bg-red-500 transition-all"
                style={{ width: `${(summary.non_compliant / summary.total_devices) * 100}%` }}
                title={`${summary.non_compliant} non-compliant`}
              />
            )}
            {summary.unknown > 0 && (
              <div
                className="bg-zinc-200 transition-all"
                style={{ width: `${(summary.unknown / summary.total_devices) * 100}%` }}
                title={`${summary.unknown} unknown`}
              />
            )}
          </div>
          <div className="flex gap-4 mt-2 text-xs text-zinc-500">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> Compliant</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Non-compliant</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-zinc-300 inline-block" /> Unknown</span>
          </div>
        </div>
      )}

      {/* Policies */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-700 uppercase tracking-wider">Policies</h2>
        <span className="text-xs text-zinc-400">{policies.length} active</span>
      </div>

      {loading && policies.length === 0 ? (
        <div className="text-center py-12 text-zinc-400 text-sm">Loading…</div>
      ) : (
        <div className="space-y-3">
          {policies.map((p) => (
            <PolicyCard key={p.id} policy={p} onEvaluate={handleEvaluate} />
          ))}
        </div>
      )}
    </div>
  );
}
