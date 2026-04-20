"use client";

import { useEffect, useState } from "react";
import {
  listGroups, createGroup, deleteGroup, listGroupDevices, addDevicesToGroup,
  removeDeviceFromGroup, bulkActionGroup, getDevices,
  type DeviceGroupItem, type Device,
} from "@/lib/api";
import { Plus, Trash2, ChevronDown, ChevronUp, Lock, RotateCw, Search, Users } from "lucide-react";

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

const COLORS = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444",
  "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16",
];

export default function GroupsPage() {
  const [groups, setGroups] = useState<DeviceGroupItem[]>([]);
  const [allDevices, setAllDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [groupDevices, setGroupDevices] = useState<Record<string, Device[]>>({});
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newColor, setNewColor] = useState(COLORS[0]);
  const [creating, setCreating] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [showAddDevices, setShowAddDevices] = useState<string | null>(null);
  const [addSelected, setAddSelected] = useState<Set<string>>(new Set());

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [gs, devs] = await Promise.all([listGroups(), getDevices()]);
      setGroups(gs);
      setAllDevices(devs);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function toggleExpand(groupId: string) {
    if (expanded === groupId) {
      setExpanded(null);
      return;
    }
    setExpanded(groupId);
    if (!groupDevices[groupId]) {
      try {
        const devs = await listGroupDevices(groupId);
        setGroupDevices((prev) => ({ ...prev, [groupId]: devs }));
      } catch {
        setGroupDevices((prev) => ({ ...prev, [groupId]: [] }));
      }
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await createGroup(newName.trim(), newDesc.trim() || undefined, newColor);
      setNewName("");
      setNewDesc("");
      setNewColor(COLORS[0]);
      setShowCreate(false);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create group");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(groupId: string, name: string) {
    if (!confirm(`Delete group "${name}"?`)) return;
    try {
      await deleteGroup(groupId);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete group");
    }
  }

  async function handleBulk(groupId: string, action: string) {
    if (action === "erase") {
      if (!confirm("Erase all devices in this group? This cannot be undone.")) return;
    }
    try {
      const result = await bulkActionGroup(groupId, action);
      setActionMsg(`${action}: ${result.queued} command(s) queued`);
      setTimeout(() => setActionMsg(""), 4000);
    } catch (err: unknown) {
      setActionMsg(err instanceof Error ? err.message : "Action failed");
    }
  }

  async function handleRemoveDevice(groupId: string, deviceId: string) {
    try {
      await removeDeviceFromGroup(groupId, deviceId);
      setGroupDevices((prev) => ({
        ...prev,
        [groupId]: (prev[groupId] || []).filter((d) => d.id !== deviceId),
      }));
      setGroups((prev) =>
        prev.map((g) => g.id === groupId ? { ...g, member_count: g.member_count - 1 } : g)
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to remove device");
    }
  }

  async function handleAddDevices(groupId: string) {
    if (addSelected.size === 0) return;
    try {
      const result = await addDevicesToGroup(groupId, Array.from(addSelected));
      setActionMsg(`Added ${result.added} device(s) to group`);
      setAddSelected(new Set());
      setShowAddDevices(null);
      const devs = await listGroupDevices(groupId);
      setGroupDevices((prev) => ({ ...prev, [groupId]: devs }));
      await load();
      setTimeout(() => setActionMsg(""), 4000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add devices");
    }
  }

  const alreadyInGroup = (groupId: string) =>
    new Set((groupDevices[groupId] || []).map((d) => d.id));

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Device Groups</h1>
          <p className="text-sm text-zinc-500 mt-0.5">{groups.length} groups</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
        >
          <Plus size={14} /> New Group
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      {actionMsg && (
        <div className="mb-4 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">{actionMsg}</div>
      )}

      {/* Create group form */}
      {showCreate && (
        <div className="mb-6 rounded-xl border border-zinc-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-zinc-800 mb-4">New Group</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">Name</label>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Engineering Laptops"
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-600 mb-1">Description (optional)</label>
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Engineering team devices"
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-xs font-medium text-zinc-600 mb-2">Color</label>
            <div className="flex gap-2">
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() => setNewColor(c)}
                  className={`w-6 h-6 rounded-full border-2 transition-all ${newColor === c ? "border-zinc-900 scale-110" : "border-transparent"}`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create"}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center text-zinc-400 py-16">Loading…</div>
      ) : groups.length === 0 ? (
        <div className="text-center text-zinc-400 py-16">
          <Users size={40} className="mx-auto mb-3 text-zinc-200" />
          <p>No groups yet. Create one to organize your devices.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.id} className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
              {/* Group header */}
              <div className="flex items-center gap-4 px-5 py-4">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: group.color }} />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-zinc-900">{group.name}</div>
                  {group.description && (
                    <div className="text-xs text-zinc-500 mt-0.5">{group.description}</div>
                  )}
                </div>
                <span className="text-xs text-zinc-500 bg-zinc-100 rounded-full px-2.5 py-0.5">
                  {group.member_count} device{group.member_count !== 1 ? "s" : ""}
                </span>
                {/* Bulk actions */}
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handleBulk(group.id, "query")}
                    title="Query all"
                    className="p-1.5 rounded text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition-colors"
                  >
                    <Search size={13} />
                  </button>
                  <button
                    onClick={() => handleBulk(group.id, "restart")}
                    title="Restart all"
                    className="p-1.5 rounded text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition-colors"
                  >
                    <RotateCw size={13} />
                  </button>
                  <button
                    onClick={() => handleBulk(group.id, "lock")}
                    title="Lock all"
                    className="p-1.5 rounded text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition-colors"
                  >
                    <Lock size={13} />
                  </button>
                </div>
                <button
                  onClick={() => handleDelete(group.id, group.name)}
                  title="Delete group"
                  className="p-1.5 rounded text-zinc-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                >
                  <Trash2 size={13} />
                </button>
                <button
                  onClick={() => toggleExpand(group.id)}
                  className="p-1.5 rounded text-zinc-400 hover:bg-zinc-100 transition-colors"
                >
                  {expanded === group.id ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>
              </div>

              {/* Expanded: devices in group */}
              {expanded === group.id && (
                <div className="border-t border-zinc-100 bg-zinc-50/50">
                  {/* Add devices */}
                  <div className="px-5 py-3 border-b border-zinc-100">
                    {showAddDevices === group.id ? (
                      <div>
                        <p className="text-xs font-medium text-zinc-600 mb-2">Select devices to add:</p>
                        <div className="max-h-40 overflow-y-auto space-y-1 mb-3">
                          {allDevices
                            .filter((d) => !alreadyInGroup(group.id).has(d.id))
                            .map((d) => (
                              <label key={d.id} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-zinc-100 rounded px-2 py-1">
                                <input
                                  type="checkbox"
                                  checked={addSelected.has(d.id)}
                                  onChange={() => {
                                    setAddSelected((prev) => {
                                      const next = new Set(prev);
                                      if (next.has(d.id)) next.delete(d.id);
                                      else next.add(d.id);
                                      return next;
                                    });
                                  }}
                                  className="rounded border-zinc-300 text-indigo-600"
                                />
                                <span className="font-medium text-zinc-800">{d.hostname ?? d.udid.slice(0, 8)}</span>
                                <span className="text-zinc-400 text-xs">{d.serial_number}</span>
                              </label>
                            ))}
                          {allDevices.filter((d) => !alreadyInGroup(group.id).has(d.id)).length === 0 && (
                            <p className="text-xs text-zinc-400 px-2">All devices are already in this group</p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleAddDevices(group.id)}
                            disabled={addSelected.size === 0}
                            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                          >
                            Add {addSelected.size > 0 ? `(${addSelected.size})` : ""}
                          </button>
                          <button
                            onClick={() => { setShowAddDevices(null); setAddSelected(new Set()); }}
                            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => { setShowAddDevices(group.id); setAddSelected(new Set()); }}
                        className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        <Plus size={12} /> Add devices
                      </button>
                    )}
                  </div>

                  {/* Device list */}
                  {(groupDevices[group.id] || []).length === 0 ? (
                    <p className="px-5 py-4 text-xs text-zinc-400">No devices in this group yet.</p>
                  ) : (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-zinc-100">
                          <th className="px-5 py-2 text-left font-medium text-zinc-500">Device</th>
                          <th className="px-5 py-2 text-left font-medium text-zinc-500">Serial</th>
                          <th className="px-5 py-2 text-left font-medium text-zinc-500">OS</th>
                          <th className="px-5 py-2 text-left font-medium text-zinc-500">Status</th>
                          <th className="px-5 py-2 text-left font-medium text-zinc-500">Last seen</th>
                          <th className="px-5 py-2"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-50">
                        {(groupDevices[group.id] || []).map((d) => (
                          <tr key={d.id} className="hover:bg-zinc-100/50">
                            <td className="px-5 py-2 font-medium text-zinc-800">{d.hostname ?? d.udid?.slice(0, 8)}</td>
                            <td className="px-5 py-2 font-mono text-zinc-500">{d.serial_number ?? "—"}</td>
                            <td className="px-5 py-2 text-zinc-500">{d.os_version ?? "—"}</td>
                            <td className="px-5 py-2 text-zinc-500">{d.status}</td>
                            <td className="px-5 py-2 text-zinc-400">{timeAgo(d.last_checkin)}</td>
                            <td className="px-5 py-2 text-right">
                              <button
                                onClick={() => handleRemoveDevice(group.id, d.id)}
                                className="text-zinc-400 hover:text-red-500 transition-colors"
                                title="Remove from group"
                              >
                                <Trash2 size={12} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
