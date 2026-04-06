"use client";

import { useEffect, useState, use, useRef } from "react";
import {
  getDevice, lockDevice, eraseDevice, restartDevice, queryDevice,
  getDeviceApps, getDeviceUpdates, getDeviceCompliance, scanDevice, installUpdates,
  getDeviceUsers, refreshDeviceUsers, getAgentToken, pushUsbBlockDevice, removeUsbBlockDevice, pushPssoDevice,
  type Device, type InstalledApp, type DeviceUpdate, type ComplianceStatus, type DeviceUser,
} from "@/lib/api";
import {
  ArrowLeft, Lock, Trash2, RefreshCw, Search, Loader2, CheckCircle2,
  Clock, X, ShieldCheck, ShieldAlert, ShieldOff, Download, Package, Users, Terminal, Copy, Check,
} from "lucide-react";
import Link from "next/link";

// ── Small helpers ────────────────────────────────────────────────────────────

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</dt>
      <dd className="mt-1 text-sm text-zinc-900">{value ?? "—"}</dd>
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  enrolled: "bg-green-100 text-green-800 border-green-200",
  pending: "bg-yellow-100 text-yellow-800 border-yellow-200",
  unenrolled: "bg-zinc-100 text-zinc-600 border-zinc-200",
  wiped: "bg-red-100 text-red-700 border-red-200",
  spare: "bg-purple-100 text-purple-700 border-purple-200",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? "bg-zinc-100 text-zinc-600 border-zinc-200";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border ${cls}`}>
      {status}
    </span>
  );
}

function ComplianceBadge({ status }: { status: string }) {
  if (status === "compliant") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5">
      <ShieldCheck size={11} /> Compliant
    </span>
  );
  if (status === "non_compliant") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-full px-2.5 py-0.5">
      <ShieldAlert size={11} /> Non-compliant
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 bg-zinc-50 border border-zinc-200 rounded-full px-2.5 py-0.5">
      <ShieldOff size={11} /> Unknown
    </span>
  );
}

// ── Lock modal ────────────────────────────────────────────────────────────────

function LockModal({ onConfirm, onCancel }: { onConfirm: (pin: string, msg: string) => void; onCancel: () => void }) {
  const [pin, setPin] = useState("");
  const [message, setMessage] = useState("");
  const pinOk = /^\d{6}$/.test(pin);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-zinc-900">Lock Device</h2>
          <button onClick={onCancel}><X size={16} className="text-zinc-400 hover:text-zinc-700" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-700 mb-1">6-digit PIN <span className="text-red-500">*</span></label>
            <input type="text" inputMode="numeric" maxLength={6} value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="123456"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm font-mono tracking-widest"
              autoFocus />
            <p className="text-xs text-zinc-400 mt-1">Required by macOS to unlock the device.</p>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-700 mb-1">Lock message (optional)</label>
            <input type="text" value={message} onChange={(e) => setMessage(e.target.value)}
              placeholder="Contact IT: 1800-XXX-XXXX"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          </div>
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onCancel} className="flex-1 rounded-lg border border-zinc-300 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50">Cancel</button>
          <button onClick={() => onConfirm(pin, message)} disabled={!pinOk}
            className="flex-1 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-40">
            Lock Device
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DeviceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [device, setDevice] = useState<Device | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [polling, setPolling] = useState(false);
  const [showLockModal, setShowLockModal] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "patch" | "users" | "agent">("overview");

  // Agent tab state
  const [agentInfo, setAgentInfo] = useState<{ device_id: string; agent_token: string; server_url: string; bootstrap_url: string } | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  async function loadAgentToken() {
    setAgentLoading(true);
    try { setAgentInfo(await getAgentToken(id)); }
    catch (err: unknown) { showToast(`Error: ${err instanceof Error ? err.message : "unknown"}`); }
    finally { setAgentLoading(false); }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // Users tab state
  const [deviceUsers, setDeviceUsers] = useState<DeviceUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [refreshingUsers, setRefreshingUsers] = useState(false);

  async function loadUsers() {
    setUsersLoading(true);
    try { setDeviceUsers(await getDeviceUsers(id)); }
    finally { setUsersLoading(false); }
  }

  async function handleRefreshUsers() {
    setRefreshingUsers(true);
    try {
      await refreshDeviceUsers(id);
      setToast("UserList command queued — users will update after device checks in");
      setTimeout(() => setToast(""), 4000);
    } finally { setRefreshingUsers(false); }
  }

  useEffect(() => { if (activeTab === "users") loadUsers(); }, [activeTab]);

  // Patch tab state
  const [compliance, setCompliance] = useState<ComplianceStatus | null>(null);
  const [apps, setApps] = useState<InstalledApp[]>([]);
  const [updates, setUpdates] = useState<DeviceUpdate[]>([]);
  const [appSearch, setAppSearch] = useState("");
  const [patchLoading, setPatchLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);

  async function load(): Promise<Device | undefined> {
    try {
      const d = await getDevice(id);
      setDevice(d);
      return d;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load device");
    } finally {
      setLoading(false);
    }
  }

  async function loadPatch() {
    setPatchLoading(true);
    try {
      const [c, a, u] = await Promise.all([getDeviceCompliance(id), getDeviceApps(id), getDeviceUpdates(id)]);
      setCompliance(c); setApps(a); setUpdates(u);
    } catch { /* ignore */ }
    finally { setPatchLoading(false); }
  }

  useEffect(() => { load(); }, [id]);
  useEffect(() => { if (activeTab === "patch") loadPatch(); }, [activeTab]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  function showToast(msg: string) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  function startPolling(prevDevice: Device) {
    setPolling(true); pollCountRef.current = 0;
    pollRef.current = setInterval(async () => {
      pollCountRef.current++;
      const updated = await load();
      const changed = updated && (
        updated.serial_number !== prevDevice.serial_number ||
        updated.os_version !== prevDevice.os_version ||
        updated.last_checkin !== prevDevice.last_checkin
      );
      if (changed || pollCountRef.current >= 24) {
        if (pollRef.current) clearInterval(pollRef.current);
        setPolling(false);
        if (changed) showToast("✓ Device info updated");
      }
    }, 5000);
  }

  function startScanPolling(prevCompliance: ComplianceStatus | null) {
    setScanning(true); pollCountRef.current = 0;
    pollRef.current = setInterval(async () => {
      pollCountRef.current++;
      const [c, a, u] = await Promise.all([getDeviceCompliance(id), getDeviceApps(id), getDeviceUpdates(id)]);
      setCompliance(c); setApps(a); setUpdates(u);
      const changed = c.compliance_checked_at !== prevCompliance?.compliance_checked_at ||
        c.total_app_count !== prevCompliance?.total_app_count;
      if (changed || pollCountRef.current >= 36) {
        if (pollRef.current) clearInterval(pollRef.current);
        setScanning(false);
        if (changed) showToast("✓ Scan results updated");
      }
    }, 5000);
  }

  async function runAction(name: string, fn: () => Promise<unknown>) {
    setAction(name);
    if (pollRef.current) { clearInterval(pollRef.current); setPolling(false); }
    try {
      await fn();
      showToast(`${name} command sent to device`);
      if (name === "Query" && device) startPolling(device);
    } catch (err: unknown) {
      showToast(`Error: ${err instanceof Error ? err.message : "unknown"}`);
    } finally { setAction(null); }
  }

  async function handleScan() {
    try {
      await scanDevice(id);
      showToast("Scan queued — waiting for device…");
      startScanPolling(compliance);
    } catch (err: unknown) {
      showToast(`Error: ${err instanceof Error ? err.message : "unknown"}`);
    }
  }

  async function handleInstall(keys: string[]) {
    try {
      await installUpdates(id, keys);
      showToast(`Install queued for ${keys.length} update(s)`);
      setSelectedKeys(new Set());
    } catch (err: unknown) {
      showToast(`Error: ${err instanceof Error ? err.message : "unknown"}`);
    }
  }

  const filteredApps = apps.filter(a =>
    a.name.toLowerCase().includes(appSearch.toLowerCase()) ||
    (a.bundle_id?.toLowerCase().includes(appSearch.toLowerCase()))
  );

  if (loading) return <div className="p-8 text-zinc-500">Loading…</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (!device) return null;

  return (
    <div className="p-8 max-w-4xl">
      {showLockModal && <LockModal
        onConfirm={(pin, msg) => { setShowLockModal(false); runAction("Lock", () => lockDevice(id, pin, msg || undefined)); }}
        onCancel={() => setShowLockModal(false)}
      />}

      {toast && <div className="fixed top-4 right-4 z-40 rounded-lg bg-zinc-900 text-white text-sm px-4 py-2 shadow-lg">{toast}</div>}

      {/* Header */}
      <div className="mb-6">
        <Link href="/devices" className="flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 mb-4 transition-colors">
          <ArrowLeft size={14} /> Back to devices
        </Link>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-semibold text-zinc-900">{device.hostname ?? device.udid.slice(0, 8)}</h1>
          <ComplianceBadge status={device.compliance_status ?? "unknown"} />
          {polling && (
            <span className="flex items-center gap-1.5 text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2.5 py-0.5">
              <Loader2 size={11} className="animate-spin" /> Waiting for device…
            </span>
          )}
        </div>
        <p className="text-sm text-zinc-500 mt-0.5">{device.model ?? device.platform}</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-zinc-200">
        {(["overview", "patch", "users", "agent"] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-700"
            }`}>
            {tab === "overview" ? "Overview" : tab === "patch" ? "Patch & Compliance" : tab === "users" ? "Users" : "Agent"}
          </button>
        ))}
      </div>

      {/* ── Overview tab ── */}
      {activeTab === "overview" && (
        <>
          <div className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-zinc-900">Device Information</h2>
              <button onClick={() => load()} className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-800">
                <RefreshCw size={12} /> Refresh
              </button>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
              <Field label="Serial Number" value={device.serial_number} />
              <Field label="OS Version" value={device.os_version} />
              <Field label="Model" value={device.model} />
              <Field label="Platform" value={device.platform} />
              <div>
                <dt className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Status</dt>
                <dd className="mt-1"><StatusBadge status={device.status} /></dd>
              </div>
              <Field label="PSSO Status" value={device.psso_status} />
              <Field label="Enrolled" value={device.enrolled_at ? new Date(device.enrolled_at).toLocaleString() : null} />
              <Field label="Last Check-in" value={device.last_checkin ? new Date(device.last_checkin).toLocaleString() : null} />
              <Field label="UDID" value={device.udid} />
            </dl>
          </div>

          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <h2 className="text-sm font-medium text-zinc-900 mb-4">Remote Actions</h2>
            <div className="grid grid-cols-2 gap-3">
              <button onClick={() => runAction("Query", () => queryDevice(id))} disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-zinc-300 px-4 py-3 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50">
                {polling ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
                {action === "Query" ? "Queuing…" : polling ? "Waiting for Mac…" : "Query Device Info"}
              </button>
              <button onClick={() => runAction("Restart", () => restartDevice(id))} disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-zinc-300 px-4 py-3 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50">
                <RefreshCw size={15} />
                {action === "Restart" ? "Queuing…" : "Restart Device"}
              </button>
              <button onClick={() => setShowLockModal(true)} disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50">
                <Lock size={15} /> {action === "Lock" ? "Sending…" : "Lock Device"}
              </button>
              <button onClick={() => { if (confirm("Erase this device? Cannot be undone.")) runAction("Erase", () => eraseDevice(id)); }}
                disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50">
                <Trash2 size={15} /> {action === "Erase" ? "Queuing…" : "Erase Device"}
              </button>
              <button onClick={() => { if (confirm("Block USB storage on this device?")) runAction("UsbBlock", () => pushUsbBlockDevice(id)); }}
                disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-orange-300 bg-orange-50 px-4 py-3 text-sm font-medium text-orange-700 hover:bg-orange-100 disabled:opacity-50">
                <ShieldAlert size={15} /> {action === "UsbBlock" ? "Queuing…" : "Block USB"}
              </button>
              <button onClick={() => { if (confirm("Remove USB block from this device?")) runAction("UsbUnblock", () => removeUsbBlockDevice(id)); }}
                disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-zinc-300 bg-zinc-50 px-4 py-3 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50">
                <ShieldOff size={15} /> {action === "UsbUnblock" ? "Queuing…" : "Remove USB Block"}
              </button>
              <button onClick={() => { if (confirm("Push Platform SSO (Entra ID) profile to this device?")) runAction("PushPsso", () => pushPssoDevice(id)); }}
                disabled={!!action || polling}
                className="flex items-center justify-center gap-2 rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50">
                <ShieldCheck size={15} /> {action === "PushPsso" ? "Queuing…" : "Push PSSO"}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Patch & Compliance tab ── */}
      {activeTab === "patch" && (
        <div className="space-y-6">
          {/* Compliance summary */}
          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-zinc-900">Compliance Summary</h2>
              <button onClick={handleScan} disabled={scanning}
                className="flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50">
                {scanning ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
                {scanning ? "Scanning…" : "Scan for updates"}
              </button>
            </div>

            {patchLoading ? (
              <div className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={14} className="animate-spin" /> Loading…</div>
            ) : compliance ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <ComplianceBadge status={compliance.compliance_status} />
                  {compliance.compliance_checked_at && (
                    <span className="text-xs text-zinc-400">
                      Last checked {new Date(compliance.compliance_checked_at).toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
                    <p className="text-xs text-zinc-500 mb-1">FileVault</p>
                    <p className={`text-sm font-medium ${compliance.is_encrypted === true ? "text-green-700" : compliance.is_encrypted === false ? "text-red-600" : "text-zinc-400"}`}>
                      {compliance.is_encrypted === true ? "✓ Enabled" : compliance.is_encrypted === false ? "✗ Disabled" : "— Unknown"}
                    </p>
                  </div>
                  <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
                    <p className="text-xs text-zinc-500 mb-1">Supervised</p>
                    <p className={`text-sm font-medium ${compliance.is_supervised === true ? "text-green-700" : compliance.is_supervised === false ? "text-zinc-400" : "text-zinc-400"}`}>
                      {compliance.is_supervised === true ? "✓ Yes" : compliance.is_supervised === false ? "No" : "— Unknown"}
                    </p>
                  </div>
                  <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
                    <p className="text-xs text-zinc-500 mb-1">Pending Updates</p>
                    <p className={`text-sm font-medium ${compliance.critical_update_count > 0 ? "text-red-600" : "text-green-700"}`}>
                      {compliance.total_update_count} total · {compliance.critical_update_count} critical
                    </p>
                  </div>
                  <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-4 py-3">
                    <p className="text-xs text-zinc-500 mb-1">Installed Apps</p>
                    <p className="text-sm font-medium text-zinc-900">{compliance.total_app_count} apps</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-zinc-400">No compliance data yet. Click <strong>Scan for updates</strong> to collect data from the device.</p>
            )}
          </div>

          {/* OS Updates */}
          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-zinc-900">
                Pending OS Updates
                {updates.length > 0 && <span className="ml-2 text-xs text-zinc-400">({updates.length})</span>}
              </h2>
              {selectedKeys.size > 0 && (
                <button onClick={() => { if (confirm(`Install ${selectedKeys.size} update(s)?`)) handleInstall([...selectedKeys]); }}
                  className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">
                  <Download size={12} /> Install Selected ({selectedKeys.size})
                </button>
              )}
            </div>
            {updates.length === 0 ? (
              <p className="text-sm text-zinc-400">{compliance ? "No pending updates." : "Run a scan to check for updates."}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-100">
                      <th className="text-left py-2 pr-3 w-8">
                        <input type="checkbox" className="rounded"
                          checked={selectedKeys.size === updates.length}
                          onChange={(e) => setSelectedKeys(e.target.checked ? new Set(updates.map(u => u.product_key)) : new Set())} />
                      </th>
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Name</th>
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Version</th>
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Critical</th>
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Restart</th>
                      <th className="text-left py-2 text-xs font-medium text-zinc-500">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {updates.map(u => (
                      <tr key={u.product_key} className="border-b border-zinc-50 hover:bg-zinc-50">
                        <td className="py-2 pr-3">
                          <input type="checkbox" className="rounded"
                            checked={selectedKeys.has(u.product_key)}
                            onChange={(e) => {
                              const next = new Set(selectedKeys);
                              e.target.checked ? next.add(u.product_key) : next.delete(u.product_key);
                              setSelectedKeys(next);
                            }} />
                        </td>
                        <td className="py-2 pr-4 text-zinc-900">{u.human_readable_name ?? u.product_key}</td>
                        <td className="py-2 pr-4 text-zinc-500">{u.version ?? "—"}</td>
                        <td className="py-2 pr-4">
                          {u.is_critical ? <span className="text-xs text-red-600 font-medium">Critical</span> : <span className="text-xs text-zinc-400">No</span>}
                        </td>
                        <td className="py-2 pr-4">
                          {u.restart_required ? <span className="text-xs text-amber-600">Required</span> : <span className="text-xs text-zinc-400">No</span>}
                        </td>
                        <td className="py-2">
                          <button onClick={() => { if (confirm(`Install ${u.human_readable_name ?? u.product_key}?`)) handleInstall([u.product_key]); }}
                            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800">
                            <Download size={11} /> Install
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Installed Apps */}
          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-zinc-900">
                Installed Applications
                {apps.length > 0 && <span className="ml-2 text-xs text-zinc-400">({apps.length})</span>}
              </h2>
              {apps.length > 0 && (
                <div className="relative">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
                  <input value={appSearch} onChange={(e) => setAppSearch(e.target.value)}
                    placeholder="Search apps…"
                    className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-zinc-300 w-48 focus:outline-none focus:ring-1 focus:ring-zinc-400" />
                </div>
              )}
            </div>
            {apps.length === 0 ? (
              <p className="text-sm text-zinc-400">Run a scan to collect the installed applications list.</p>
            ) : (
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white">
                    <tr className="border-b border-zinc-100">
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Name</th>
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Bundle ID</th>
                      <th className="text-left py-2 pr-4 text-xs font-medium text-zinc-500">Version</th>
                      <th className="text-left py-2 text-xs font-medium text-zinc-500">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredApps.map((app, i) => (
                      <tr key={i} className="border-b border-zinc-50 hover:bg-zinc-50">
                        <td className="py-1.5 pr-4 text-zinc-900">{app.name}</td>
                        <td className="py-1.5 pr-4 text-zinc-400 font-mono text-xs">{app.bundle_id ?? "—"}</td>
                        <td className="py-1.5 pr-4 text-zinc-500">{app.short_version ?? app.version ?? "—"}</td>
                        <td className="py-1.5 text-zinc-400 text-xs">{app.source ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredApps.length === 0 && appSearch && (
                  <p className="text-sm text-zinc-400 py-4 text-center">No apps match "{appSearch}"</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Users tab ── */}
      {activeTab === "users" && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-medium text-zinc-900 flex items-center gap-2">
                  <Users size={15} /> Local Users
                  {deviceUsers.length > 0 && <span className="text-xs text-zinc-400">({deviceUsers.length})</span>}
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">Local accounts on this Mac</p>
              </div>
              <button
                onClick={handleRefreshUsers}
                disabled={refreshingUsers}
                className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 disabled:opacity-50 transition-colors"
              >
                <RefreshCw size={12} className={refreshingUsers ? "animate-spin" : ""} />
                {refreshingUsers ? "Queuing…" : "Refresh from device"}
              </button>
            </div>

            {usersLoading ? (
              <div className="flex items-center gap-2 text-sm text-zinc-400 py-6">
                <Loader2 size={14} className="animate-spin" /> Loading…
              </div>
            ) : deviceUsers.length === 0 ? (
              <div className="py-6">
                <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800 mb-4">
                  <p className="font-medium mb-1">Apple MDM limitation</p>
                  <p className="text-xs">The <code>UserList</code> MDM command only returns network/directory users (Active Directory, LDAP). It does not return local macOS accounts. This Mac returned an empty list because it is not domain-joined.</p>
                </div>
                <p className="text-xs text-zinc-500">
                  The device owner can be inferred from the device name: <strong className="text-zinc-700">{device?.hostname}</strong>
                </p>
              </div>
            ) : (
              <div className="divide-y divide-zinc-100">
                {deviceUsers.map((u) => (
                  <div key={u.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-zinc-100 flex items-center justify-center text-sm font-semibold text-zinc-600">
                        {u.full_name ? u.full_name[0].toUpperCase() : u.short_name[0].toUpperCase()}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-zinc-900">
                            {u.full_name || u.short_name}
                          </span>
                          {u.is_logged_in && (
                            <span className="inline-flex items-center rounded-full bg-green-50 border border-green-200 px-2 py-0.5 text-xs text-green-700">
                              Active
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-zinc-400 font-mono">{u.short_name}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {u.has_secure_token && (
                        <span className="inline-flex items-center rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs text-blue-700">
                          Secure Token
                        </span>
                      )}
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border ${
                        u.is_admin
                          ? "bg-orange-50 border-orange-200 text-orange-700"
                          : "bg-zinc-50 border-zinc-200 text-zinc-600"
                      }`}>
                        {u.is_admin ? "Admin" : "Standard"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-500 space-y-2">
            <p className="font-medium text-zinc-700">Managing user privileges</p>
            <p><strong>For Entra ID (cloud) users:</strong> Go to <strong>Settings → Push PSSO Profile</strong> and set Admin Groups to the Entra group whose members should get local admin rights on the Mac.</p>
            <p><strong>For local accounts:</strong> Use the <strong>Agent tab</strong> to install the MDM management agent — it enables automatic admin elevation via the Policies page.</p>
          </div>
        </div>
      )}

      {/* ── Agent tab ── */}
      {activeTab === "agent" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <div className="flex items-center gap-2 mb-1">
              <Terminal size={15} className="text-zinc-600" />
              <h2 className="text-sm font-medium text-zinc-900">MDM Management Agent</h2>
            </div>
            <p className="text-xs text-zinc-500 mb-5">
              Installs a lightweight root daemon that polls for jobs every 30s.
              Once installed, admin elevation and revocation happen automatically — no manual login required.
            </p>

            {!agentInfo ? (
              <button onClick={loadAgentToken} disabled={agentLoading}
                className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50">
                {agentLoading ? <Loader2 size={14} className="animate-spin" /> : <Terminal size={14} />}
                {agentLoading ? "Generating…" : "Generate Install Command"}
              </button>
            ) : (() => {
              const jwt = typeof window !== "undefined" ? localStorage.getItem("mdm_token") : "";
              // Use -G -d to pass auth — avoids ? in the URL (zsh glob) and quotes (smart-quote issues)
              const oneLiner = `curl -sSLG -d auth=${jwt} ${agentInfo.bootstrap_url} | sudo bash`;
              return (
                <div className="space-y-5">
                  <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800">
                    <p className="font-medium">One-time install — run as admin on the Mac</p>
                    <p className="mt-0.5">Open Terminal on the Mac while logged in as the admin account and run the command below.</p>
                  </div>

                  <div>
                    <p className="text-xs font-medium text-zinc-700 mb-1.5">Install command</p>
                    <div className="relative rounded-lg bg-zinc-900 px-4 py-3 pr-10">
                      <code className="text-xs text-green-400 font-mono break-all">{oneLiner}</code>
                      <button onClick={() => copyToClipboard(oneLiner)}
                        className="absolute top-2 right-2 rounded p-1 hover:bg-zinc-700">
                        {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} className="text-zinc-400" />}
                      </button>
                    </div>
                    <p className="text-xs text-zinc-400 mt-1.5">The command downloads and installs the agent in one step. No pkg file needed.</p>
                  </div>

                  <div>
                    <p className="text-xs font-medium text-zinc-700 mb-1.5">Verify installation</p>
                    <div className="rounded-lg bg-zinc-900 px-4 py-3">
                      <code className="text-xs text-green-400 font-mono whitespace-pre">{`sudo launchctl list | grep mdmsaas\ntail -f /var/log/mdm-agent.log`}</code>
                    </div>
                  </div>

                  <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
                    <p className="font-medium mb-1">After install</p>
                    <ul className="list-disc list-inside space-y-0.5">
                      <li>Go to <strong>Policies</strong> and approve an admin access request</li>
                      <li>The agent runs <code>dseditgroup</code> automatically within 30 seconds</li>
                      <li>A UserList refresh confirms the elevation in the Users tab</li>
                      <li>Revoke works the same way — no manual steps needed</li>
                    </ul>
                    <p className="mt-1 font-medium">Share this portal URL with the user:</p>
                    {(() => {
                      const portalUrl = `${agentInfo.server_url}/api/v1/portal?token=${agentInfo.agent_token}`;
                      return (
                        <div className="mt-1 flex items-center gap-2">
                          <code className="text-xs break-all">{portalUrl}</code>
                          <button onClick={() => copyToClipboard(portalUrl)}
                            className="flex-shrink-0 rounded p-1 hover:bg-blue-100">
                            {copied ? <Check size={12} className="text-green-600" /> : <Copy size={12} className="text-blue-600" />}
                          </button>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
