"use client";

import { useRouter } from "next/navigation";

import { api } from "@/lib/api";

export function LogoutButton() {
  const router = useRouter();

  async function onClick() {
    try {
      await api.post("/api/v1/auth/logout");
    } catch {
      // ignore; we'll redirect anyway
    }
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-1 text-sm font-medium text-[var(--foreground)] transition-colors hover:border-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
    >
      Sign out
    </button>
  );
}
