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

export type QueryResponse = {
  answer: string;
  sources: Source[];
};
