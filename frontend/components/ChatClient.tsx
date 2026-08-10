"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import {
  api,
  formatTimestamp,
  getChunkText,
  isAudioSource,
  streamQuery,
  type ApiError,
  type Source,
  type StreamEvent,
} from "@/lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  sources?: Source[];
  error?: string;
  question?: string;
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

function highlightSpans(text: string, query: string | undefined): { value: string; hit: boolean }[] {
  if (!query || !text) return [{ value: text, hit: false }];
  const queryWords = Array.from(
    new Set(
      query
        .toLowerCase()
        .split(/\W+/u)
        .filter((w) => w.length >= 4),
    ),
  );
  if (queryWords.length === 0) return [{ value: text, hit: false }];
  const lower = text.toLowerCase();
  const ranges: Array<[number, number]> = [];
  for (const w of queryWords) {
    let from = 0;
    while (true) {
      const i = lower.indexOf(w, from);
      if (i === -1) break;
      ranges.push([i, i + w.length]);
      from = i + w.length;
    }
  }
  if (ranges.length === 0) return [{ value: text, hit: false }];
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) {
      last[1] = Math.max(last[1], r[1]);
    } else {
      merged.push([r[0], r[1]]);
    }
  }
  const out: { value: string; hit: boolean }[] = [];
  let cursor = 0;
  for (const [s, e] of merged) {
    if (s > cursor) out.push({ value: text.slice(cursor, s), hit: false });
    out.push({ value: text.slice(s, e), hit: true });
    cursor = e;
  }
  if (cursor < text.length) out.push({ value: text.slice(cursor), hit: false });
  return out;
}

function SourceCard({
  source,
  question,
  onSeekAudio,
  activeAudioId,
  textOverride,
}: {
  source: Source;
  question?: string;
  onSeekAudio: (source: Source) => void;
  activeAudioId?: string | null;
  textOverride?: string | null;
}) {
  const audio = isAudioSource(source);
  const locationLabel = sourceLocationLabel(source);
  const scorePct = Math.max(0, Math.min(100, Math.round(source.score * 100)));
  const body = textOverride ?? source.snippet;
  const parts = useMemo(() => highlightSpans(body, question), [body, question]);
  const isPlaying = activeAudioId === source.chunk_id;

  function openDocument() {
    if (!source.document_url) return;
    if (audio) return;
    const page = source.page_start ?? 1;
    const hash = `#page=${page}`;
    window.open(`${source.document_url}${hash}`, "_blank", "noopener,noreferrer");
  }

  return (
    <li className="rounded-md border border-zinc-200 p-3 text-xs dark:border-zinc-800">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">
          [{source.index ?? "·"}] {source.filename}
        </span>
        <span className="shrink-0 text-zinc-500">
          {locationLabel} · {scorePct}%
        </span>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
        {parts.map((p, i) =>
          p.hit ? (
            <mark
              key={i}
              className="rounded bg-yellow-200 px-0.5 text-zinc-900 dark:bg-yellow-500/40 dark:text-zinc-50"
            >
              {p.value}
            </mark>
          ) : (
            <span key={i}>{p.value}</span>
          ),
        )}
      </p>
      <div className="mt-2 flex items-center gap-2">
        {audio && source.start_seconds != null && (
          <button
            type="button"
            onClick={() => onSeekAudio(source)}
            className={
              "rounded border px-2 py-0.5 text-[11px] font-medium transition " +
              (isPlaying
                ? "border-emerald-500 text-emerald-700 dark:text-emerald-300"
                : "border-zinc-300 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900")
            }
          >
            {isPlaying ? "▶ playing" : `↳ jump to ${formatTimestamp(source.start_seconds)}`}
          </button>
        )}
        {!audio && source.document_url && source.page_start != null && (
          <button
            type="button"
            onClick={openDocument}
            className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
          >
            ↳ view p. {source.page_start}
          </button>
        )}
      </div>
    </li>
  );
}

export function ChatClient() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [activeAudioId, setActiveAudioId] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

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
    const assistantId = newId();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      text: "",
      streaming: true,
      question: trimmed,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setPending(true);

    let finalSources: Source[] = [];
    try {
      const stream = streamQuery(trimmed, 5);
      for await (const ev of stream) {
        applyEvent(ev, assistantId, setMessages, (sources) => {
          finalSources = sources;
        });
      }
      // After the stream finishes, lazily hydrate `text` on each source so
      // the user sees the full chunk instead of the 240-char snippet.
      if (finalSources.length > 0) {
        await hydrateSourcesText(finalSources);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, sources: finalSources, streaming: false }
              : m,
          ),
        );
      } else {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        );
      }
    } catch (err) {
      const e = err as ApiError;
      if (e && typeof e.status === "number") {
        console.error("[chat] stream failed", e.status, e.detail);
      } else {
        console.error("[chat] stream failed", err);
      }
      const detail =
        (e && typeof e.detail === "string" && e.detail) ||
        (e && typeof e.status === "number"
          ? `Request failed (${e.status}).`
          : "Network error. Is the backend running on :8000?");
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, text: "", error: detail, streaming: false }
            : m,
        ),
      );
    } finally {
      setPending(false);
    }
  }

  function onSeekAudio(source: Source) {
    if (source.start_seconds == null || !source.document_url) return;
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.src !== source.document_url) {
      audio.src = source.document_url;
    }
    audio.currentTime = source.start_seconds;
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        // Autoplay can be blocked; user can click again.
      });
    }
    setActiveAudioId(source.chunk_id);
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
                  {m.streaming && (
                    <span
                      aria-hidden="true"
                      className="ml-0.5 inline-block h-3 w-1.5 translate-y-0.5 animate-pulse bg-zinc-400"
                    />
                  )}
                </p>
                {m.sources && m.sources.length > 0 && (
                  <ul className="mt-3 space-y-2">
                    {m.sources.map((s) => (
                      <SourceCard
                        key={s.chunk_id}
                        source={s}
                        question={m.question}
                        onSeekAudio={onSeekAudio}
                        activeAudioId={activeAudioId}
                        textOverride={s.text ?? null}
                      />
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

      <audio
        ref={audioRef}
        onPause={() => setActiveAudioId(null)}
        onEnded={() => setActiveAudioId(null)}
        preload="none"
        className="hidden"
      />
    </div>
  );
}

function applyEvent(
  ev: StreamEvent,
  assistantId: string,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  setSources: (sources: Source[]) => void,
) {
  if (ev.type === "token") {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId ? { ...m, text: m.text + ev.t } : m,
      ),
    );
    return;
  }
  if (ev.type === "sources") {
    setSources(ev.sources);
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId ? { ...m, sources: ev.sources } : m,
      ),
    );
    return;
  }
  if (ev.type === "error") {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId
          ? { ...m, text: "", error: ev.detail, streaming: false }
          : m,
      ),
    );
    return;
  }
  if (ev.type === "done") {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId ? { ...m, streaming: false } : m,
      ),
    );
  }
}

async function hydrateSourcesText(sources: Source[]) {
  await Promise.all(
    sources.map(async (s) => {
      if (s.text && s.text.length > 0) return;
      try {
        const text = await getChunkText(s.document_id, s.chunk_id);
        s.text = text;
      } catch {
        s.text = s.snippet;
      }
    }),
  );
}
