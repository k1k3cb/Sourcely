import { getCurrentUserFromCookies } from "@/lib/auth";
import { LogoutButton } from "@/components/LogoutButton";

export default async function DocumentsPage() {
  const user = await getCurrentUserFromCookies();
  return (
    <main className="min-h-screen px-6 py-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <h1 className="text-xl font-semibold">Documents</h1>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-zinc-500">{user?.email}</span>
          <LogoutButton />
        </div>
      </header>
      <section className="mx-auto mt-8 max-w-3xl rounded-lg border border-dashed border-zinc-300 p-12 text-center text-sm text-zinc-500 dark:border-zinc-700">
        Document upload will land here. (Etapa 2)
      </section>
    </main>
  );
}
