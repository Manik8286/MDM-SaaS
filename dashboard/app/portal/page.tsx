"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

async function portalRequest<T>(apiBase: string, token: string, path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiBase}/api/v1/portal${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

interface DeviceInfo {
  device_id: string;
  hostname: string | null;
  model: string | null;
  os_version: string | null;
  users: { id: string; short_name: string; full_name: string | null; is_admin: boolean }[];
}

interface CatalogItem {
  id: string;
  name: string;
  category: string;
  icon: string;
  description: string;
}

interface SoftwareRequest {
  id: string;
  software_name: string;
  status: string;
  reason: string | null;
  created_at: string;
}

interface AdminRequest {
  id: string;
  status: string;
  reason: string | null;
  duration_hours: number;
  requested_at: string;
  revoke_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  pending:    "bg-amber-50 text-amber-700 border-amber-200",
  approved:   "bg-green-50 text-green-700 border-green-200",
  rejected:   "bg-red-50 text-red-700 border-red-200",
  installing: "bg-blue-50 text-blue-700 border-blue-200",
  completed:  "bg-green-50 text-green-700 border-green-200",
  failed:     "bg-red-50 text-red-700 border-red-200",
  denied:     "bg-red-50 text-red-700 border-red-200",
  revoked:    "bg-zinc-50 text-zinc-500 border-zinc-200",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full border capitalize ${STATUS_COLORS[status] ?? "bg-zinc-50 text-zinc-500 border-zinc-200"}`}>
      {status}
    </span>
  );
}

function PortalContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const apiBase = (searchParams.get("api") || "http://localhost:8000").replace(/\/$/, "");

  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [softwareRequests, setSoftwareRequests] = useState<SoftwareRequest[]>([]);
  const [adminRequests, setAdminRequests] = useState<AdminRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"software" | "admin" | "status">("software");

  // Forms
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedSoftware, setSelectedSoftware] = useState<CatalogItem | null>(null);
  const [customSoftware, setCustomSoftware] = useState("");
  const [softwareReason, setSoftwareReason] = useState("");
  const [adminReason, setAdminReason] = useState("");
  const [adminDuration, setAdminDuration] = useState(4);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState("");

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  }

  async function load() {
    if (!token) { setError("No device token. Access this page via the MDM Agent tab in the dashboard."); setLoading(false); return; }
    try {
      const [d, c, sr, ar] = await Promise.all([
        portalRequest<DeviceInfo>(apiBase, token, "/me"),
        portalRequest<CatalogItem[]>(apiBase, token, "/catalog"),
        portalRequest<SoftwareRequest[]>(apiBase, token, "/software-requests"),
        portalRequest<AdminRequest[]>(apiBase, token, "/admin-requests"),
      ]);
      setDevice(d);
      setCatalog(c);
      setSoftwareRequests(sr);
      setAdminRequests(ar);
      if (d.users.length > 0) setSelectedUser(d.users.find(u => !u.is_admin)?.short_name || d.users[0].short_name);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [token]);

  async function submitSoftwareRequest() {
    if (!selectedUser) return showToast("Select your username first");
    const name = selectedSoftware?.name || customSoftware;
    if (!name) return showToast("Select or enter a software name");
    setSubmitting(true);
    try {
      await portalRequest(apiBase, token, "/software-requests", {
        method: "POST",
        body: JSON.stringify({
          requester_name: selectedUser,
          software_id: selectedSoftware?.id || undefined,
          software_name: selectedSoftware ? undefined : customSoftware,
          reason: softwareReason || undefined,
        }),
      });
      showToast(`Request submitted for ${name}. An admin will review shortly.`);
      setSelectedSoftware(null);
      setCustomSoftware("");
      setSoftwareReason("");
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false); }
  }

  async function submitAdminRequest() {
    if (!selectedUser) return showToast("Select your username first");
    setSubmitting(true);
    try {
      await portalRequest(apiBase, token, "/admin-requests", {
        method: "POST",
        body: JSON.stringify({
          requester_name: selectedUser,
          reason: adminReason || undefined,
          duration_hours: adminDuration,
        }),
      });
      showToast("Admin access request submitted. An admin will review shortly.");
      setAdminReason("");
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center">
      <div className="text-zinc-400 text-sm">Loading…</div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-6">
      <div className="bg-white rounded-xl border border-red-200 p-6 max-w-md text-center">
        <div className="text-3xl mb-3">⚠️</div>
        <p className="text-sm font-medium text-red-700 mb-1">Unable to connect</p>
        <p className="text-xs text-zinc-500">{error}</p>
      </div>
    </div>
  );

  const categories = [...new Set(catalog.map(c => c.category))];

  return (
    <div className="min-h-screen bg-zinc-50">
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-zinc-900 text-white text-sm px-4 py-2.5 rounded-xl shadow-lg max-w-sm">
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="bg-white border-b border-zinc-200 px-6 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-zinc-900">IT Self-Service Portal</h1>
            <p className="text-xs text-zinc-400">{device?.hostname ?? "Your Mac"} · {device?.model}</p>
          </div>
          {device && device.users.length > 0 && (
            <select
              value={selectedUser}
              onChange={e => setSelectedUser(e.target.value)}
              className="text-sm border border-zinc-300 rounded-lg px-3 py-1.5 bg-white text-zinc-700"
            >
              {device.users.map(u => (
                <option key={u.id} value={u.short_name}>
                  {u.full_name || u.short_name}{u.is_admin ? " (admin)" : ""}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white border-b border-zinc-200">
        <div className="max-w-2xl mx-auto flex gap-1 px-6">
          {(["software", "admin", "status"] as const).map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-700"
              }`}>
              {tab === "software" ? "📦 Request Software" : tab === "admin" ? "🔑 Admin Access" : "📋 My Requests"}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-6 py-6 space-y-6">

        {/* ── Software tab ── */}
        {activeTab === "software" && (
          <>
            <div className="bg-white rounded-xl border border-zinc-200 p-5">
              <h2 className="text-sm font-semibold text-zinc-900 mb-4">Software Catalog</h2>
              {categories.map(cat => (
                <div key={cat} className="mb-4">
                  <p className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-2">{cat}</p>
                  <div className="grid grid-cols-2 gap-2">
                    {catalog.filter(c => c.category === cat).map(item => (
                      <button key={item.id}
                        onClick={() => setSelectedSoftware(selectedSoftware?.id === item.id ? null : item)}
                        className={`flex items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
                          selectedSoftware?.id === item.id
                            ? "border-zinc-900 bg-zinc-50"
                            : "border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50"
                        }`}>
                        <span className="text-2xl">{item.icon}</span>
                        <div>
                          <p className="text-sm font-medium text-zinc-900">{item.name}</p>
                          <p className="text-xs text-zinc-400 line-clamp-1">{item.description}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}

              <div className="border-t border-zinc-100 pt-4 mt-2">
                <p className="text-xs text-zinc-500 mb-2">Not in the list? Request custom software:</p>
                <input
                  value={customSoftware}
                  onChange={e => { setCustomSoftware(e.target.value); setSelectedSoftware(null); }}
                  placeholder="e.g. Adobe Photoshop"
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                />
              </div>
            </div>

            {(selectedSoftware || customSoftware) && (
              <div className="bg-white rounded-xl border border-zinc-200 p-5">
                <h2 className="text-sm font-semibold text-zinc-900 mb-3">
                  Request: {selectedSoftware?.name || customSoftware}
                </h2>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-zinc-700 mb-1">Reason (optional)</label>
                    <textarea
                      value={softwareReason}
                      onChange={e => setSoftwareReason(e.target.value)}
                      placeholder="Why do you need this software?"
                      rows={2}
                      className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm resize-none"
                    />
                  </div>
                  <button onClick={submitSoftwareRequest} disabled={submitting}
                    className="w-full rounded-xl bg-zinc-900 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50">
                    {submitting ? "Submitting…" : "Submit Request"}
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Admin access tab ── */}
        {activeTab === "admin" && (
          <div className="bg-white rounded-xl border border-zinc-200 p-5">
            <h2 className="text-sm font-semibold text-zinc-900 mb-1">Request Admin Access</h2>
            <p className="text-xs text-zinc-500 mb-4">
              Admin access gives you temporary elevated privileges to install software or make system changes.
              An IT admin must approve your request.
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-700 mb-1">Reason</label>
                <textarea
                  value={adminReason}
                  onChange={e => setAdminReason(e.target.value)}
                  placeholder="e.g. Need to install Zoom for a client meeting"
                  rows={3}
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm resize-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-700 mb-1">Duration</label>
                <div className="flex gap-2">
                  {[1, 2, 4, 8, 24].map(h => (
                    <button key={h} onClick={() => setAdminDuration(h)}
                      className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors ${
                        adminDuration === h
                          ? "border-zinc-900 bg-zinc-900 text-white"
                          : "border-zinc-200 text-zinc-700 hover:bg-zinc-50"
                      }`}>
                      {h}h
                    </button>
                  ))}
                </div>
              </div>

              <button onClick={submitAdminRequest} disabled={submitting || !adminReason}
                className="w-full rounded-xl bg-zinc-900 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50">
                {submitting ? "Submitting…" : "Request Admin Access"}
              </button>
            </div>
          </div>
        )}

        {/* ── Status tab ── */}
        {activeTab === "status" && (
          <div className="space-y-4">
            <div className="bg-white rounded-xl border border-zinc-200 p-5">
              <h2 className="text-sm font-semibold text-zinc-900 mb-3">Software Requests</h2>
              {softwareRequests.length === 0 ? (
                <p className="text-sm text-zinc-400">No requests yet.</p>
              ) : (
                <div className="divide-y divide-zinc-100">
                  {softwareRequests.map(r => (
                    <div key={r.id} className="flex items-center justify-between py-3">
                      <div>
                        <p className="text-sm font-medium text-zinc-900">{r.software_name}</p>
                        {r.reason && <p className="text-xs text-zinc-400">{r.reason}</p>}
                        <p className="text-xs text-zinc-300 mt-0.5">{new Date(r.created_at).toLocaleString()}</p>
                      </div>
                      <StatusBadge status={r.status} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white rounded-xl border border-zinc-200 p-5">
              <h2 className="text-sm font-semibold text-zinc-900 mb-3">Admin Access Requests</h2>
              {adminRequests.length === 0 ? (
                <p className="text-sm text-zinc-400">No requests yet.</p>
              ) : (
                <div className="divide-y divide-zinc-100">
                  {adminRequests.map(r => (
                    <div key={r.id} className="flex items-center justify-between py-3">
                      <div>
                        <p className="text-sm font-medium text-zinc-900">{r.reason || "Admin access"}</p>
                        <p className="text-xs text-zinc-400">{r.duration_hours}h · {new Date(r.requested_at).toLocaleString()}</p>
                        {r.status === "approved" && r.revoke_at && (
                          <p className="text-xs text-green-600 font-medium">Active until {new Date(r.revoke_at).toLocaleString()}</p>
                        )}
                      </div>
                      <StatusBadge status={r.status} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PortalPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-zinc-50 flex items-center justify-center text-zinc-400 text-sm">Loading…</div>}>
      <PortalContent />
    </Suspense>
  );
}
