import Link from "next/link";

import { DocumentsClient } from "@/components/DocumentsClient";
import { LogoutButton } from "@/components/LogoutButton";
import { api, type DocumentRecord } from "@/lib/api";
import { getCurrentUserFromCookies } from "@/lib/auth";

export default async function DocumentsPage() {
  const user = await getCurrentUserFromCookies();
  let initial: DocumentRecord[] = [];
  try {
    initial = await api.get<DocumentRecord[]>("/api/v1/documents");
  } catch {
    // empty list on error
  }
  return (
    <main className="min-h-screen px-6 py-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold">Documents</h1>
          <Link
            href="/chat"
            className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            Chat
          </Link>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-zinc-500">{user?.email}</span>
          <LogoutButton />
        </div>
      </header>
      <DocumentsClient initial={initial} />
    </main>
  );
}
