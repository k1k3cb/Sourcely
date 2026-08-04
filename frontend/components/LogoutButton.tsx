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
      className="rounded border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
    >
      Sign out
    </button>
  );
}
