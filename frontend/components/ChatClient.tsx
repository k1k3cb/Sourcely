"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import {
  streamQuery,
  type Source,
  type StreamEvent,
} from "@/lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  pending?: boolean;
  error?: string;
};

function newId() {
  return Math.random().toString(36).slice(2);
}

function SourceButton({
  source,
  onClick,
}: {
  source: Source;
  onClick: (s: Source) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(source)}
      className="block w-full rounded border border-zinc-200 px-3 py-2 text-left text-xs hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
    >
      <div className="font-medium">{source.filename}</div>
      <div className="text-zinc-500">
        p.{source.page_start} · score {source.score.toFixed(2)}
      </div>
      <div className="mt-1 line-clamp-2 text-zinc-600 dark:text-zinc-400">
        {source.snippet}
      </div>
    </button>
  );
}

function CitationPanel({
  source,
  onClose,
}: {
  source: Source;
  onClose: () => void;
}) {
  return (
    <div className="mt-2 rounded border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between">
        <div className="font-medium">
          {source.filename}, p.{source.page_start}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          aria-label="Close citation"
        >
          x
        </button>
      </div>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-zinc-700 dark:text-zinc-200">
        {source.snippet}
      </pre>
    </div>
  );
}

function applyEvent(
  ev: StreamEvent,
  assistantId: string,
  onToken: (delta: string) => void,
  onSources: (sources: Source[]) => void,
) {
  if (ev.type === "token") onToken(ev.t);
  else if (ev.type === "sources") onSources(ev.sources);
}

export function ChatClient({ initialQuestion }: { initialQuestion?: string }) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(initialQuestion ?? "");
  const [pending, setPending] = useState(false);
  const [activeSource, setActiveSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const question = input.trim();
    if (!question || pending) return;
    setError(null);
    setInput("");

    const userMsg: Message = { id: newId(), role: "user", text: question };
    const assistantId = newId();
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", text: "", pending: true },
    ]);
    setPending(true);

    let acc = "";
    try {
      const stream = streamQuery(question, 5);
      for await (const ev of stream) {
        applyEvent(
          ev,
          assistantId,
          (delta) => {
            acc += delta;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, text: acc, pending: false }
                  : m,
              ),
            );
          },
          (srcs) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, sources: srcs } : m,
              ),
            );
          },
        );
      }
    } catch (err) {
      const detail = (err as { detail?: string }).detail ?? "Request failed";
      setError(detail);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, text: acc, error: detail, pending: false }
            : m,
        ),
      );
    } finally {
      setPending(false);
      router.refresh();
    }
  }

  return (
    <div className="mx-auto mt-6 flex max-w-3xl flex-col gap-4">
      <div className="flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="rounded-lg border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
            Ask anything about your uploaded documents. Answers cite the
            source page.
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={
              m.role === "user"
                ? "self-end max-w-[80%] rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "self-start max-w-[90%] rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm dark:border-zinc-800 dark:bg-zinc-950"
            }
          >
            <div className="whitespace-pre-wrap">
              {m.text || (m.pending ? "Thinking..." : "")}
            </div>
            {m.error && (
              <div className="mt-2 text-xs text-red-600 dark:text-red-400">
                {m.error}
              </div>
            )}
            {m.sources && m.sources.length > 0 && (
              <div className="mt-3 flex flex-col gap-2">
                <div className="text-xs font-medium text-zinc-500">
                  Sources ({m.sources.length})
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {m.sources.map((s) => (
                    <SourceButton
                      key={s.chunk_id}
                      source={s}
                      onClick={setActiveSource}
                    />
                  ))}
                </div>
                {activeSource &&
                  m.sources.some(
                    (s) => s.chunk_id === activeSource.chunk_id,
                  ) && (
                    <CitationPanel
                      source={activeSource}
                      onClose={() => setActiveSource(null)}
                    />
                  )}
              </div>
            )}
          </div>
        ))}
      </div>
      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          disabled={pending}
          className="flex-1 rounded border border-zinc-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {pending ? "Sending..." : "Send"}
        </button>
      </form>
    </div>
  );
}
