"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Monitor, Shield, QrCode, LogOut, Settings, ScrollText, ShieldCheck, Lock, Package, Users, Layers, Moon, Sun } from "lucide-react";
import { logout } from "@/lib/api";

const nav = [
  { href: "/devices", label: "Devices", icon: Monitor },
  { href: "/groups", label: "Groups", icon: Layers },
  { href: "/profiles", label: "Profiles", icon: Shield },
  { href: "/compliance", label: "Compliance", icon: ShieldCheck },
  { href: "/policies", label: "Policies", icon: Lock },
  { href: "/packages", label: "Packages", icon: Package },
  { href: "/enrollment", label: "Enrollment", icon: QrCode },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
  { href: "/users", label: "Team", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [dark, setDark] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && !localStorage.getItem("mdm_token")) {
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
    const saved = localStorage.getItem("mdm_dark") === "1";
    setDark(saved);
    document.documentElement.classList.toggle("dark", saved);
  }, []);

  function toggleDark() {
    const next = !dark;
    setDark(next);
    localStorage.setItem("mdm_dark", next ? "1" : "0");
    document.documentElement.classList.toggle("dark", next);
  }

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="flex h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-white dark:bg-zinc-900 border-r border-zinc-200 dark:border-zinc-800 flex flex-col">
        <div className="px-5 py-5 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
          <span className="text-base font-semibold text-zinc-900 dark:text-zinc-100">MDM Console</span>
          <button onClick={toggleDark} className="p-1 rounded text-zinc-400 hover:text-zinc-700 dark:text-zinc-500 dark:hover:text-zinc-200">
            {dark ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                }`}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="px-3 py-4 border-t border-zinc-200 dark:border-zinc-800">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 w-full rounded-lg text-sm font-medium text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 transition-colors"
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
