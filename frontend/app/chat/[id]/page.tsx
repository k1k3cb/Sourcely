import { notFound } from "next/navigation";

import { ChatClient } from "@/components/ChatClient";
import { ChatLayout } from "@/components/ChatLayout";
import { getCurrentUserFromCookies } from "@/lib/auth";
import { api, type ConversationDetail } from "@/lib/api";

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getCurrentUserFromCookies();
  if (!user) {
    notFound();
  }
  let conv: ConversationDetail | null = null;
  try {
    conv = await api.get<ConversationDetail>(
      `/api/v1/conversations/${id}`,
    );
  } catch {
    notFound();
  }
  return (
    <ChatLayout activeId={id}>
      <ChatClient initial={conv} />
    </ChatLayout>
  );
}
