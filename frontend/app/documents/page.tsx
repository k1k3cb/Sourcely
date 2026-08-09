import { AppHeader } from "@/components/AppHeader";
import { DocumentsClient } from "@/components/DocumentsClient";
import { apiServerFetch } from "@/lib/auth";
import { getCurrentUserFromCookies } from "@/lib/auth";
import type { DocumentRecord } from "@/lib/api";

export default async function DocumentsPage() {
  const user = await getCurrentUserFromCookies();
  let initial: DocumentRecord[] = [];
  try {
    initial = await apiServerFetch<DocumentRecord[]>("/api/v1/documents");
  } catch {
    // empty list on error
  }
  return (
    <main className="min-h-screen px-6 py-8">
      <AppHeader email={user?.email} active="documents" />
      <DocumentsClient initial={initial} />
    </main>
  );
}
