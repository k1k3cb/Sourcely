import { useMemo } from "react";

import { formatTimestamp, isAudioSource, type Source } from "@/lib/api";

export function sourceLocationLabel(source: Source): string {
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

export function highlightSpans(
  text: string,
  query: string | undefined,
): { value: string; hit: boolean }[] {
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

export function SourceCard({
  source,
  question,
  onSeekAudio,
  onStopAudio,
  activeAudioId,
  textOverride,
}: {
  source: Source;
  question?: string;
  onSeekAudio: (source: Source) => void;
  onStopAudio: () => void;
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
          <>
            {isPlaying ? (
              <button
                type="button"
                onClick={onStopAudio}
                className="rounded border border-red-500 px-2 py-0.5 text-[11px] font-medium text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950"
              >
                ■ stop
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onSeekAudio(source)}
                className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
              >
                ↳ jump to {formatTimestamp(source.start_seconds)}
              </button>
            )}
          </>
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
