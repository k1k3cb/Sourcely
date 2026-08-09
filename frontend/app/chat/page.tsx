import { AppHeader } from "@/components/AppHeader";
import { ChatClient } from "@/components/ChatClient";
import { getCurrentUserFromCookies } from "@/lib/auth";

export default async function ChatPage() {
  const user = await getCurrentUserFromCookies();
  return (
    <main className="min-h-screen px-6 py-8">
      <AppHeader email={user?.email} active="chat" />
      <ChatClient />
    </main>
  );
}
