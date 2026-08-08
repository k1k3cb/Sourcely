const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiError = {
  status: number;
  detail: string;
};

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const isFormData =
    typeof FormData !== "undefined" && init.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (!isFormData && init.body !== undefined && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore
    }
    const err: ApiError = { status: res.status, detail };
    throw err;
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
};

export async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<T>(path, { method: "POST", body: form });
}

export async function deleteRequest<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
}

export type CurrentUser = {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
};

export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export type DocumentRecord = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  page_count: number | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  signed_url?: string | null;
};

export type Source = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  snippet: string;
  score: number;
};

export type StreamEvent =
  | { type: "token"; t: string }
  | { type: "sources"; sources: Source[] }
  | { type: "done" }
  | { type: "error"; detail: string };

export async function* streamQuery(
  question: string,
  k = 5,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_URL}/api/v1/query/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k }),
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore
    }
    const err: ApiError = { status: res.status, detail };
    throw err;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Parse SSE events separated by blank lines
    let sepIdx;
    while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sepIdx);
      buffer = buffer.slice(sepIdx + 2);
      const ev = parseSseBlock(block);
      if (ev) yield ev;
    }
  }
}

function parseSseBlock(block: string): StreamEvent | null {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!data) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(data);
  } catch {
    return null;
  }
  if (event === "token" && typeof (parsed as { t?: unknown }).t === "string") {
    return { type: "token", t: (parsed as { t: string }).t };
  }
  if (event === "sources") {
    const sources = (parsed as { sources?: Source[] }).sources ?? [];
    return { type: "sources", sources };
  }
  if (event === "done") return { type: "done" };
  if (event === "error") {
    return { type: "error", detail: String((parsed as { detail?: unknown }).detail ?? "Unknown error") };
  }
  return null;
}

export async function getChunk(
  documentId: string,
  chunkId: string,
): Promise<{
  id: string;
  document_id: string;
  page_start: number;
  page_end: number;
  text: string;
  token_count: number;
}> {
  return apiFetch(`/api/v1/documents/${documentId}/chunks/${chunkId}`);
}

export type QuerySource = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  snippet: string;
  score: number;
};

export type QueryResponse = {
  answer: string;
  sources: QuerySource[];
};
