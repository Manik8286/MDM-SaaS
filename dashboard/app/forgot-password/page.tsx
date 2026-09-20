"use client";

import { useState } from "react";
import Link from "next/link";
import { forgotPassword } from "@/lib/api";
import { Shield, Loader2, CheckCircle } from "lucide-react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-8">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 mb-8 justify-center">
          <Shield size={20} className="text-zinc-900" />
          <span className="font-semibold text-zinc-900">MDM Console</span>
        </div>

        {sent ? (
          <div className="text-center">
            <CheckCircle size={32} className="text-green-500 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-zinc-900 mb-1">Check your email</h2>
            <p className="text-sm text-zinc-500 mb-6">
              If an account exists for <span className="font-medium text-zinc-700">{email}</span>,
              we&apos;ve sent a link to reset your password. It expires in 1 hour.
            </p>
            <Link href="/login" className="text-sm font-medium text-zinc-900 hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : (
          <>
            <h2 className="text-xl font-semibold text-zinc-900 mb-1 text-center">Forgot password?</h2>
            <p className="text-sm text-zinc-500 mb-6 text-center">
              Enter your email and we&apos;ll send you a reset link.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-700 mb-1">Work email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  autoFocus
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
                />
              </div>

              {error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="flex items-center justify-center gap-2 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 transition-colors"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : null}
                {loading ? "Sending…" : "Send reset link"}
              </button>
            </form>

            <p className="mt-6 text-sm text-zinc-500 text-center">
              <Link href="/login" className="text-zinc-900 font-medium hover:underline">
                Back to sign in
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
