"use client";

import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createEnrollmentToken, type EnrollmentToken } from "@/lib/api";
import { Copy, CheckCheck, Plus, Download, QrCode, RefreshCw } from "lucide-react";

export default function EnrollmentPage() {
  const [platform, setPlatform] = useState("macos");
  const [reusable, setReusable] = useState(false);
  const [expiresIn, setExpiresIn] = useState(72);
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState<EnrollmentToken | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

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
    </div>
  );
}
