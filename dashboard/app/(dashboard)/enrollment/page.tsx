"use client";

import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createEnrollmentToken, importDevicesCsv, csvTemplateUrl, type EnrollmentToken, type ImportResult } from "@/lib/api";
import { Copy, CheckCheck, Plus, Download, QrCode, RefreshCw, Upload, FileText } from "lucide-react";

export default function EnrollmentPage() {
  const [platform, setPlatform] = useState("macos");
  const [reusable, setReusable] = useState(false);
  const [expiresIn, setExpiresIn] = useState(72);
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState<EnrollmentToken | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  // CSV import state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState("");

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await createEnrollmentToken(platform, reusable, expiresIn);
      setToken(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create token");
    } finally {
      setLoading(false);
    }
  }

  async function handleImport(e: React.FormEvent) {
    e.preventDefault();
    if (!csvFile) return;
    setImporting(true);
    setImportResult(null);
    setImportError("");
    try {
      const result = await importDevicesCsv(csvFile);
      setImportResult(result);
      setCsvFile(null);
    } catch (err: unknown) {
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  async function handleCopy() {
    if (!token) return;
    await navigator.clipboard.writeText(token.enrollment_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="p-8 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">Enroll a Device</h1>
        <p className="text-sm text-zinc-500 mt-0.5">
          Generate an enrollment profile and install it on the Mac
        </p>
      </div>

      {!token ? (
        <div className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900"
              >
                <option value="macos">macOS</option>
                <option value="ios">iOS / iPadOS</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1">Expires in</label>
              <select
                value={expiresIn}
                onChange={(e) => setExpiresIn(Number(e.target.value))}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900"
              >
                <option value={24}>24 hours</option>
                <option value={72}>72 hours (3 days)</option>
                <option value={168}>7 days</option>
                <option value={720}>30 days</option>
              </select>
            </div>

            <div className="flex items-center gap-3">
              <input
                id="reusable"
                type="checkbox"
                checked={reusable}
                onChange={(e) => setReusable(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-300"
              />
              <label htmlFor="reusable" className="text-sm text-zinc-700">
                Reusable (multiple devices can use this token)
              </label>
            </div>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            >
              <Plus size={14} />
              {loading ? "Generating…" : "Generate Enrollment Profile"}
            </button>
          </form>
        </div>
      ) : (
        <div className="space-y-4 mb-6">
          {/* QR Code + URL card */}
          <div className="bg-white rounded-xl border border-zinc-200 p-6">
            <div className="flex items-start gap-6">
              <div className="flex-shrink-0 flex flex-col items-center gap-2">
                <div className="p-3 bg-white border border-zinc-200 rounded-lg">
                  <QRCodeSVG value={token.enrollment_url} size={140} />
                </div>
                <p className="text-xs text-zinc-400 text-center">Scan on UTM Mac</p>
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-3">
                  <QrCode size={16} className="text-green-600" />
                  <span className="text-sm font-medium text-zinc-900">Profile ready</span>
                  <span className="text-xs text-zinc-400">
                    {token.reusable ? "Reusable" : "Single-use"} ·{" "}
                    {token.expires_at
                      ? `Expires ${new Date(token.expires_at).toLocaleString()}`
                      : "No expiry"}
                  </span>
                </div>

                <div className="rounded-lg bg-zinc-50 border border-zinc-200 px-3 py-2 mb-3">
                  <p className="text-xs font-mono text-zinc-700 break-all">
                    {token.enrollment_url}
                  </p>
                </div>

                <div className="flex gap-2 flex-wrap">
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
                  >
                    {copied ? (
                      <CheckCheck size={13} className="text-green-600" />
                    ) : (
                      <Copy size={13} />
                    )}
                    {copied ? "Copied!" : "Copy URL"}
                  </button>

                  <a
                    href={token.enrollment_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
                  >
                    <Download size={13} />
                    Download on this Mac
                  </a>

                  <button
                    onClick={() => setToken(null)}
                    className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
                  >
                    <RefreshCw size={13} />
                    New token
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Step-by-step for UTM Mac */}
          <div className="bg-blue-50 rounded-xl border border-blue-200 p-5">
            <p className="text-sm font-medium text-blue-900 mb-3">
              Enrolling your UTM Mac (192.168.64.2)
            </p>
            <ol className="space-y-2 text-sm text-blue-800 list-decimal list-inside">
              <li>
                Open <strong>Safari</strong> on the UTM Mac and go to:
                <span className="block font-mono text-xs bg-blue-100 rounded px-2 py-1 mt-1 break-all">
                  {token.enrollment_url}
                </span>
              </li>
              <li>
                Safari prompts: <em>"This website is trying to download a configuration profile"</em> → tap <strong>Allow</strong>
              </li>
              <li>
                Open <strong>System Settings → Privacy &amp; Security → Profiles</strong>
              </li>
              <li>
                Click the downloaded profile → <strong>Install</strong> → enter Mac password
              </li>
              <li>
                Device appears in the <strong>Devices</strong> tab within ~30 seconds
              </li>
            </ol>
          </div>
        </div>
      )}

      {!token && (
        <div className="rounded-xl border border-zinc-200 bg-white p-6">
          <h2 className="text-sm font-medium text-zinc-900 mb-3">How it works</h2>
          <ol className="space-y-2 text-sm text-zinc-600 list-decimal list-inside">
            <li>Click <strong>Generate Enrollment Profile</strong> above</li>
            <li>A QR code and direct URL will appear</li>
            <li>Open the URL in <strong>Safari</strong> on the Mac to enroll</li>
            <li>
              Install the profile in <strong>System Settings → Privacy &amp; Security → Profiles</strong>
            </li>
            <li>Device appears in the <strong>Devices</strong> list automatically</li>
          </ol>
        </div>
      )}

      {/* ── Bulk CSV import ── */}
      <div className="mt-6 bg-white rounded-xl border border-zinc-200 p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-medium text-zinc-900 flex items-center gap-2">
            <FileText size={14} /> Bulk Import via CSV
          </h2>
          <a
            href={csvTemplateUrl()}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-800 transition-colors"
          >
            <Download size={12} /> Download template
          </a>
        </div>
        <p className="text-xs text-zinc-500 mb-4">
          Pre-stage devices by serial number before they enroll. Required column: <code className="bg-zinc-100 px-1 rounded">serial_number</code>.
          Optional: <code className="bg-zinc-100 px-1 rounded">hostname</code>, <code className="bg-zinc-100 px-1 rounded">model</code>, <code className="bg-zinc-100 px-1 rounded">platform</code>.
        </p>

        <form onSubmit={handleImport} className="space-y-3">
          <label className="flex flex-col items-center justify-center gap-2 w-full rounded-lg border-2 border-dashed border-zinc-300 hover:border-zinc-400 cursor-pointer py-6 transition-colors">
            <Upload size={20} className="text-zinc-400" />
            <span className="text-sm text-zinc-500">
              {csvFile ? csvFile.name : "Click to choose a CSV file"}
            </span>
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => { setCsvFile(e.target.files?.[0] ?? null); setImportResult(null); setImportError(""); }}
            />
          </label>

          {importError && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{importError}</p>
          )}

          {importResult && (
            <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
              <p className="font-medium">Import complete</p>
              <p className="text-xs mt-1">
                {importResult.imported} imported · {importResult.skipped} skipped (already exist)
                {importResult.errors.length > 0 && ` · ${importResult.errors.length} errors`}
              </p>
              {importResult.errors.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-red-700">
                  {importResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={!csvFile || importing}
            className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
          >
            <Upload size={14} />
            {importing ? "Importing…" : "Import Devices"}
          </button>
        </form>
      </div>
    </div>
  );
}
