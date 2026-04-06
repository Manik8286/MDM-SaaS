"use client";

import { useEffect, useRef, useState } from "react";
import { getPackages, uploadPackage, deletePackage, packageDownloadUrl, SoftwarePackageItem, getApiUrl } from "@/lib/api";
import { Upload, Trash2, Download, Package } from "lucide-react";

function formatBytes(n: number | null) {
  if (!n) return "—";
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function PackagesPage() {
  const [packages, setPackages] = useState<SoftwarePackageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // Upload form state
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [description, setDescription] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  function showToast(msg: string) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  async function load() {
    try { setPackages(await getPackages()); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "Failed to load"); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload() {
    if (!selectedFile || !name) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("name", name);
      fd.append("version", version);
      fd.append("description", description);
      fd.append("file", selectedFile);
      await uploadPackage(fd);
      showToast(`${name} uploaded successfully`);
      setName(""); setVersion(""); setDescription(""); setSelectedFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(pkg: SoftwarePackageItem) {
    if (!confirm(`Delete "${pkg.name}"? This cannot be undone.`)) return;
    try {
      await deletePackage(pkg.id);
      showToast(`${pkg.name} deleted`);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Delete failed");
    }
  }

  function getInstallCommand(pkg: SoftwarePackageItem): string {
    const token = typeof window !== "undefined" ? localStorage.getItem("mdm_token") || "$AGENT_TOKEN" : "$AGENT_TOKEN";
    const url = `${getApiUrl()}/api/v1/packages/${pkg.id}/download`;
    const ext = pkg.pkg_type === "dmg" ? "dmg" : "pkg";
    const file = `/tmp/install_${pkg.id.slice(0, 8)}.${ext}`;
    if (ext === "pkg") {
      return `curl -sL -H "Authorization: Bearer ${token}" "${url}" -o ${file} && installer -pkg ${file} -target / && rm ${file}`;
    }
    const vol = pkg.name.replace(/[^a-zA-Z0-9 ]/g, "").trim();
    return `curl -sL -H "Authorization: Bearer ${token}" "${url}" -o ${file} && hdiutil attach ${file} -nobrowse -quiet && cp -R "/Volumes/${vol}/${pkg.name}.app" /Applications/ && hdiutil detach "/Volumes/${vol}" -quiet && rm ${file}`;
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-zinc-900 text-white text-sm px-4 py-2.5 rounded-xl shadow-lg">
          {toast}
        </div>
      )}

      <div>
        <h1 className="text-xl font-semibold text-zinc-900">Software Packages</h1>
        <p className="text-sm text-zinc-500 mt-0.5">Upload PKG or DMG installers. The agent downloads and installs them on approved requests.</p>
      </div>

      {/* Upload form */}
      <div className="bg-white rounded-xl border border-zinc-200 p-5 space-y-4">
        <h2 className="text-sm font-semibold text-zinc-900">Upload Package</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-zinc-700 mb-1">Name *</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Google Chrome"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-700 mb-1">Version</label>
            <input value={version} onChange={e => setVersion(e.target.value)} placeholder="e.g. 124.0"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-700 mb-1">Description</label>
          <input value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional"
            className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-700 mb-1">File (.pkg or .dmg) *</label>
          <input ref={fileRef} type="file" accept=".pkg,.dmg"
            onChange={e => setSelectedFile(e.target.files?.[0] || null)}
            className="w-full text-sm text-zinc-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-zinc-900 file:text-white hover:file:bg-zinc-700" />
        </div>
        <button onClick={handleUpload} disabled={uploading || !selectedFile || !name}
          className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50">
          <Upload size={14} />
          {uploading ? "Uploading…" : "Upload Package"}
        </button>
      </div>

      {/* Package list */}
      <div className="bg-white rounded-xl border border-zinc-200">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-semibold text-zinc-900">Uploaded Packages ({packages.length})</h2>
        </div>
        {loading ? (
          <p className="text-sm text-zinc-400 p-5">Loading…</p>
        ) : packages.length === 0 ? (
          <div className="p-8 text-center">
            <Package size={32} className="text-zinc-300 mx-auto mb-2" />
            <p className="text-sm text-zinc-400">No packages uploaded yet.</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-100">
            {packages.map(pkg => (
              <div key={pkg.id} className="px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-zinc-900">{pkg.name}</p>
                      {pkg.version && <span className="text-xs text-zinc-400">v{pkg.version}</span>}
                      <span className="text-xs bg-zinc-100 text-zinc-600 px-1.5 py-0.5 rounded font-mono">.{pkg.pkg_type}</span>
                    </div>
                    {pkg.description && <p className="text-xs text-zinc-500 mt-0.5">{pkg.description}</p>}
                    <p className="text-xs text-zinc-400 mt-0.5">{pkg.filename} · {formatBytes(pkg.file_size)} · {new Date(pkg.uploaded_at).toLocaleDateString()}</p>
                    <div className="mt-2 bg-zinc-50 rounded-lg px-3 py-2">
                      <p className="text-xs text-zinc-500 mb-1 font-medium">Install command (run as root):</p>
                      <code className="text-xs text-zinc-700 break-all">{getInstallCommand(pkg)}</code>
                    </div>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <a href={packageDownloadUrl(pkg.id)}
                      className="flex items-center gap-1 rounded-lg border border-zinc-200 px-2.5 py-1.5 text-xs text-zinc-600 hover:bg-zinc-50">
                      <Download size={12} /> Download
                    </a>
                    <button onClick={() => handleDelete(pkg)}
                      className="flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50">
                      <Trash2 size={12} /> Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
