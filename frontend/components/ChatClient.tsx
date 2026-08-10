"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { api, formatTimestamp, isAudioSource, type ApiError, type QueryResponse, type Source } from "@/lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  error?: string;
};

const SUGGESTIONS = [
  "What is this document about?",
  "Summarize the key points.",
  "List the main conclusions.",
];

function newId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function sourceLocationLabel(source: Source): string {
  if (isAudioSource(source)) {
    const start = formatTimestamp(source.start_seconds);
    const end = formatTimestamp(source.end_seconds);
    if (start && end) return `${start} – ${end}`;
    if (start) return `${start}`;
  }
  if (source.page_start != null) {
    return source.page_start === source.page_end
      ? `p. ${source.page_start}`
      : `pp. ${source.page_start}–${source.page_end}`;
  }
  return "";
}

function SourceCard({
  source,
}: {
  source: Source;
}) {
  const locationLabel = sourceLocationLabel(source);
  const scorePct = Math.max(0, Math.min(100, Math.round(source.score * 100)));
  return (
    <li className="rounded-md border border-zinc-200 p-3 text-xs dark:border-zinc-800">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{source.filename}</span>
        <span className="shrink-0 text-zinc-500">
          {locationLabel} · {scorePct}%
        </span>
      </div>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">{source.snippet}</p>
    </li>
  );
}

export function ChatClient() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || pending) return;
    setInput("");
    const userMsg: Message = { id: newId(), role: "user", text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setPending(true);
    try {
      const res = await api.post<QueryResponse>("/api/v1/query", {
        question: trimmed,
        k: 5,
      });
      const assistant: Message = {
        id: newId(),
        role: "assistant",
        text: res.answer,
        sources: res.sources,
      };
      setMessages((prev) => [...prev, assistant]);
    } catch (err) {
      const e = err as ApiError;
      const assistant: Message = {
        id: newId(),
        role: "assistant",
        text: "",
        error: e.detail || "The query failed. Try again.",
      };
      setMessages((prev) => [...prev, assistant]);
    } finally {
      setPending(false);
    }
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void ask(input);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask(input);
    }
  }

  return (
    <div className="mx-auto mt-6 flex h-[calc(100vh-9rem)] max-w-3xl flex-col">
      <div
        ref={scrollerRef}
        className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
      >
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-zinc-500">
              Ask a question about your uploaded documents.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => ask(s)}
                  disabled={pending}
                  className="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <article
            key={m.id}
            className={
              m.role === "user"
                ? "ml-auto max-w-[80%] rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "mr-auto max-w-[90%] space-y-2 text-sm"
            }
          >
            {m.role === "user" ? (
              <p className="whitespace-pre-wrap">{m.text}</p>
            ) : m.error ? (
              <p className="text-red-600 dark:text-red-400">{m.error}</p>
            ) : (
              <>
                <p className="whitespace-pre-wrap text-zinc-700 dark:text-zinc-200">
                  {m.text}
                </p>
                {m.sources && m.sources.length > 0 && (
                  <ul className="mt-3 space-y-2">
                    {m.sources.map((s) => (
                      <SourceCard key={s.chunk_id} source={s} />
                    ))}
                  </ul>
                )}
              </>
            )}
          </article>
        ))}

        {pending && (
          <p className="text-xs text-zinc-500">Searching your documents…</p>
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="mt-3 flex items-end gap-2 rounded-lg border border-zinc-200 p-2 dark:border-zinc-800"
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question…"
          rows={1}
          disabled={pending}
          className="flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-zinc-400"
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {pending ? "Sending…" : "Send"}
        </button>
      </form>
    </div>
  );
}
