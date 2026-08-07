import { AppHeader } from "@/components/AppHeader";
import { DocumentsClient } from "@/components/DocumentsClient";
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
      <AppHeader email={user?.email} active="documents" />
      <DocumentsClient initial={initial} />
    </main>
  );
}
