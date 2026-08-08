import Link from "next/link";

import { ChatClient } from "@/components/ChatClient";
import { LogoutButton } from "@/components/LogoutButton";
import { getCurrentUserFromCookies } from "@/lib/auth";

export default async function ChatPage() {
  const user = await getCurrentUserFromCookies();
  return (
    <main className="min-h-screen px-6 py-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold">Chat</h1>
          <Link
            href="/documents"
            className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            Documents
          </Link>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-zinc-500">{user?.email}</span>
          <LogoutButton />
        </div>
      </header>
      <ChatClient />
    </main>
  );
}
