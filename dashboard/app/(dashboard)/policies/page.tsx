"use client";

import React, { useEffect, useState } from "react";
import {
  getDevices, getDeviceUsers, getAdminAccessRequests,
  createAdminAccessRequest, approveAdminAccess, denyAdminAccess, revokeAdminAccess,
  pushUsbBlock, pushGatekeeper,
  getSoftwareRequests, approveSoftwareRequest, rejectSoftwareRequest,
  type Device, type DeviceUser, type AdminAccessRequest, type SoftwareRequestItem,
} from "@/lib/api";
import { UsbIcon, ShieldAlert, UserCheck, RefreshCw, CheckCircle, XCircle, Clock, Copy, Package } from "lucide-react";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
const STATUS_STYLES: Record<string, string> = {
  pending:  "bg-yellow-100 text-yellow-800",
  approved: "bg-green-100 text-green-800",
  denied:   "bg-red-100 text-red-800",
  revoked:  "bg-zinc-100 text-zinc-600",
  expired:  "bg-zinc-100 text-zinc-600",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? "bg-zinc-100 text-zinc-600"}`}>
      {status}
    </span>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function timeUntil(iso: string | null): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "expired";
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// ---------------------------------------------------------------------------
// Policy toggle card
// ---------------------------------------------------------------------------
function PolicyCard({
  icon, title, description, warning, onPush, pushing,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  warning?: string;
  onPush: () => void;
  pushing: boolean;
}) {
  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-5 flex items-start justify-between gap-4">
      <div className="flex items-start gap-4">
        <div className="p-2.5 bg-zinc-100 rounded-lg text-zinc-700">{icon}</div>
        <div>
          <h3 className="font-medium text-zinc-900">{title}</h3>
          <p className="text-sm text-zinc-400 mt-0.5">{description}</p>
          {warning && <p className="text-xs text-amber-600 mt-1">⚠ {warning}</p>}
        </div>
      </div>
      <button
        onClick={onPush}
        disabled={pushing}
        className="flex-shrink-0 px-4 py-2 text-sm font-medium bg-zinc-900 text-white rounded-lg hover:bg-zinc-700 disabled:opacity-50"
      >
        {pushing ? "Pushing…" : "Push to all"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin access request modal
// ---------------------------------------------------------------------------
function NewRequestModal({
  devices,
  onClose,
  onCreated,
}: {
  devices: Device[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [deviceId, setDeviceId] = useState("");
  const [users, setUsers] = useState<DeviceUser[]>([]);
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const [hours, setHours] = useState(4);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!deviceId) { setUsers([]); setUserId(""); return; }
    getDeviceUsers(deviceId).then(u => {
      const nonAdmin = u.filter(x => !x.is_admin);
      setUsers(nonAdmin);
      setUserId(nonAdmin[0]?.id ?? "");
    });
  }, [deviceId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await createAdminAccessRequest({ device_id: deviceId, device_user_id: userId, reason, duration_hours: hours });
      onCreated();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create request");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold text-zinc-900 mb-4">Request Temporary Admin Access</h2>
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-zinc-700">Device</label>
            <select value={deviceId} onChange={e => setDeviceId(e.target.value)} required
              className="mt-1 w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm">
              <option value="">Select device…</option>
              {devices.map(d => (
                <option key={d.id} value={d.id}>{d.hostname ?? d.serial_number ?? d.udid}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-zinc-700">User to elevate</label>
            <select value={userId} onChange={e => setUserId(e.target.value)} required disabled={!users.length}
              className="mt-1 w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm disabled:bg-zinc-50">
              <option value="">Select user…</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.short_name}{u.full_name ? ` (${u.full_name})` : ""}</option>)}
            </select>
            {deviceId && !users.length && <p className="text-xs text-zinc-400 mt-1">No non-admin users found. Run a device query first.</p>}
          </div>
          <div>
            <label className="text-sm font-medium text-zinc-700">Duration</label>
            <select value={hours} onChange={e => setHours(Number(e.target.value))}
              className="mt-1 w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm">
              {[1, 2, 4, 8, 24, 48, 72].map(h => <option key={h} value={h}>{h}h</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-zinc-700">Reason <span className="text-zinc-400">(optional)</span></label>
            <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2}
              className="mt-1 w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm resize-none"
              placeholder="Why is admin access needed?" />
          </div>
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2 border border-zinc-200 text-sm font-medium rounded-lg hover:bg-zinc-50">
              Cancel
            </button>
            <button type="submit" disabled={loading || !userId}
              className="flex-1 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-700 disabled:opacity-50">
              {loading ? "Creating…" : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Request row
// ---------------------------------------------------------------------------
function RequestRow({ req, onAction }: { req: AdminAccessRequest; onAction: () => void }) {
  const [acting, setActing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState("");

  async function act(fn: () => Promise<unknown>) {
    setActing(true);
    setErr("");
    try { await fn(); onAction(); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); onAction(); }
    finally { setActing(false); }
  }

  function copyCmd() {
    if (req.elevation_command) {
      navigator.clipboard.writeText(req.elevation_command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-zinc-900">{req.username ?? "Unknown user"}</span>
            <span className="text-zinc-300">on</span>
            <span className="text-zinc-600">{req.device_hostname ?? req.device_serial ?? req.device_id}</span>
            <StatusBadge status={req.status} />
            {req.is_currently_admin && <span className="text-xs bg-blue-100 text-blue-700 rounded-full px-2 py-0.5">Admin ✓</span>}
          </div>
          {req.reason && <p className="text-sm text-zinc-500 mt-1">{req.reason}</p>}
          <div className="flex gap-4 mt-1.5 text-xs text-zinc-400">
            <span>Requested {timeAgo(req.requested_at)}</span>
            {req.status === "approved" && req.revoke_at && (
              <span className="text-amber-600 font-medium">Revokes in {timeUntil(req.revoke_at)}</span>
            )}
            <span>{req.duration_hours}h access</span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {req.status === "pending" && (
            <>
              <button onClick={() => act(() => approveAdminAccess(req.id))} disabled={acting}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50">
                <CheckCircle size={12} /> Approve
              </button>
              <button onClick={() => act(() => denyAdminAccess(req.id))} disabled={acting}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
                <XCircle size={12} /> Deny
              </button>
            </>
          )}
          {req.status === "approved" && (
            <button onClick={() => act(() => revokeAdminAccess(req.id))} disabled={acting}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium border border-zinc-200 text-zinc-700 rounded-lg hover:bg-zinc-50 disabled:opacity-50">
              Revoke
            </button>
          )}
        </div>
      </div>

      {/* Elevation command shown after approval */}
      {req.status === "approved" && req.elevation_command && (
        <div className="mt-3 bg-zinc-900 rounded-lg px-3 py-2 flex items-center justify-between gap-3">
          <code className="text-xs text-green-400 font-mono truncate">{req.elevation_command}</code>
          <button onClick={copyCmd} className="flex-shrink-0 text-zinc-400 hover:text-white">
            {copied ? <CheckCircle size={14} className="text-green-400" /> : <Copy size={14} />}
          </button>
        </div>
      )}
      {err && <p className="mt-2 text-xs text-red-600">{err}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function PoliciesPage() {
  const [requests, setRequests] = useState<AdminAccessRequest[]>([]);
  const [softwareRequests, setSoftwareRequests] = useState<SoftwareRequestItem[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [pushing, setPushing] = useState<Record<string, boolean>>({});
  const [toast, setToast] = useState("");
  const [activeTab, setActiveTab] = useState<"admin" | "software">("admin");

  async function load() {
    setLoading(true);
    try {
      const [r, d, sr] = await Promise.all([getAdminAccessRequests(), getDevices(), getSoftwareRequests()]);
      setRequests(r);
      setDevices(d);
      setSoftwareRequests(sr);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  async function handlePush(key: string, fn: () => Promise<{ queued: number }>) {
    setPushing(p => ({ ...p, [key]: true }));
    try {
      const res = await fn();
      showToast(`Queued for ${res.queued} device${res.queued !== 1 ? "s" : ""}`);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Push failed");
    } finally {
      setPushing(p => ({ ...p, [key]: false }));
    }
  }

  const pending = requests.filter(r => r.status === "pending");
  const active  = requests.filter(r => r.status === "approved");
  const history = requests.filter(r => !["pending", "approved"].includes(r.status));

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {toast && (
        <div className="fixed top-4 right-4 bg-zinc-900 text-white text-sm px-4 py-2 rounded-lg shadow-lg z-50">
          {toast}
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Policies</h1>
          <p className="text-sm text-zinc-400 mt-0.5">USB block, app restrictions, and admin access</p>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-zinc-200 rounded-lg hover:bg-zinc-50 disabled:opacity-50">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Restriction policies */}
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-3">Device Restrictions</h2>
      <div className="space-y-3 mb-8">
        <PolicyCard
          icon={<UsbIcon size={18} />}
          title="USB Storage Block"
          description="Prevent mounting of external USB drives, disk images, DVDs and CDs on all enrolled Macs."
          warning="Requires supervised device for full enforcement on macOS 13+."
          pushing={!!pushing.usb}
          onPush={() => handlePush("usb", pushUsbBlock)}
        />
        <PolicyCard
          icon={<ShieldAlert size={18} />}
          title="App Installation Control (Gatekeeper)"
          description="Enforce Gatekeeper to block unidentified software. Allows App Store and signed developer apps."
          pushing={!!pushing.gatekeeper}
          onPush={() => handlePush("gatekeeper", () => pushGatekeeper(true))}
        />
        <PolicyCard
          icon={<ShieldAlert size={18} />}
          title="App Store Only (Strict Gatekeeper)"
          description="Block all apps not from the Mac App Store. Note: blocks Zoom, Slack, and other vendor apps."
          warning="This will prevent installation of most enterprise tools distributed outside the App Store."
          pushing={!!pushing.gatekeeperStrict}
          onPush={() => handlePush("gatekeeperStrict", () => pushGatekeeper(false))}
        />
      </div>

      {/* Requests tabs */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex gap-1 border-b border-zinc-200">
          {(["admin", "software"] as const).map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-700"
              }`}>
              {tab === "admin" ? <><UserCheck size={13} /> Admin Access {pending.length > 0 && <span className="ml-1 bg-amber-500 text-white text-xs rounded-full px-1.5">{pending.length}</span>}</> : <><Package size={13} /> Software Requests {softwareRequests.filter(r => r.status === "pending").length > 0 && <span className="ml-1 bg-blue-500 text-white text-xs rounded-full px-1.5">{softwareRequests.filter(r => r.status === "pending").length}</span>}</>}
            </button>
          ))}
        </div>
        {activeTab === "admin" && <button onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-zinc-900 text-white rounded-lg hover:bg-zinc-700">
          <UserCheck size={14} /> New Request
        </button>}
      </div>

      {/* ── Admin access tab ── */}
      {activeTab === "admin" && (
        <div className="mt-4">
          {pending.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-2">
                <Clock size={14} className="text-yellow-500" />
                <span className="text-xs font-medium text-yellow-700">Pending approval ({pending.length})</span>
              </div>
              <div className="space-y-2">{pending.map(r => <RequestRow key={r.id} req={r} onAction={load} />)}</div>
            </div>
          )}
          {active.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle size={14} className="text-green-500" />
                <span className="text-xs font-medium text-green-700">Active grants ({active.length})</span>
              </div>
              <div className="space-y-2">{active.map(r => <RequestRow key={r.id} req={r} onAction={load} />)}</div>
            </div>
          )}
          {history.length > 0 && (
            <div>
              <p className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-2">History</p>
              <div className="space-y-2">{history.slice(0, 10).map(r => <RequestRow key={r.id} req={r} onAction={load} />)}</div>
            </div>
          )}
          {!loading && requests.length === 0 && (
            <div className="text-center py-12 text-zinc-400 text-sm">No admin access requests yet</div>
          )}
        </div>
      )}

      {/* ── Software requests tab ── */}
      {activeTab === "software" && (
        <div className="mt-4 space-y-2">
          {softwareRequests.length === 0 && !loading && (
            <div className="text-center py-12 text-zinc-400 text-sm">No software requests yet. Users submit requests via the self-service portal.</div>
          )}
          {softwareRequests.map(r => (
            <div key={r.id} className="bg-white border border-zinc-200 rounded-xl p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-zinc-900">{r.software_name}</span>
                    <span className="text-zinc-300">·</span>
                    <span className="text-sm text-zinc-500">{r.requester_name}</span>
                    <span className="text-zinc-300">on</span>
                    <span className="text-sm text-zinc-500">{r.device_hostname ?? r.device_id.slice(0, 8)}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  {r.reason && <p className="text-sm text-zinc-500 mt-1">{r.reason}</p>}
                  <p className="text-xs text-zinc-400 mt-1">{new Date(r.created_at).toLocaleString()}</p>
                </div>
                {r.status === "pending" && (
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button onClick={async () => { try { await approveSoftwareRequest(r.id); showToast(`Installing ${r.software_name}…`); load(); } catch(e: unknown) { showToast(e instanceof Error ? e.message : "Failed"); } }}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700">
                      <CheckCircle size={12} /> Approve & Install
                    </button>
                    <button onClick={async () => { try { await rejectSoftwareRequest(r.id); load(); } catch(e: unknown) { showToast(e instanceof Error ? e.message : "Failed"); } }}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-red-600 text-white rounded-lg hover:bg-red-700">
                      <XCircle size={12} /> Reject
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <NewRequestModal devices={devices} onClose={() => setShowNew(false)} onCreated={load} />
      )}
    </div>
  );
}
