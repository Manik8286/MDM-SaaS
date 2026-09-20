"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, LogOut } from "lucide-react";
import { logout } from "@/lib/api";

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("mdm_token")) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  if (!ready) return null;

  return (
    <div className="min-h-screen bg-zinc-50">
      <header className="bg-white border-b border-zinc-200">
        <div className="max-w-6xl mx-auto px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 size={18} className="text-zinc-900" />
            <span className="text-base font-semibold text-zinc-900">Platform Admin</span>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-sm font-medium text-zinc-500 hover:text-zinc-900 transition-colors"
          >
            <LogOut size={14} />
            Sign out
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
