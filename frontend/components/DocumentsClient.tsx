"use client";

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  api,
  deleteRequest,
  uploadFile,
  type ApiError,
  type DocumentRecord,
} from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

const STATUS_COLORS: Record<string, string> = {
  uploaded: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200",
  processing: "bg-amber-200 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100",
  ready: "bg-emerald-200 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100",
  failed: "bg-red-200 text-red-900 dark:bg-red-900/40 dark:text-red-100",
};

const MAX_BYTES = 20 * 1024 * 1024;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function DocumentsClient({ initial }: { initial: DocumentRecord[] }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<DocumentRecord[]>(initial);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    if (file.type !== "application/pdf") {
      setError("Only PDF files are accepted.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(`File exceeds the 20 MB limit (${formatBytes(file.size)}).`);
      return;
    }
    setError(null);
    setUploading(true);
    setProgress(`Uploading ${file.name}...`);
    try {
      const created = await uploadFile<DocumentRecord>(
        "/api/v1/documents/upload",
        file,
      );
      setItems((prev) => [created, ...prev]);
      setProgress("Uploaded. Indexing in background...");
      setTimeout(() => {
        setProgress(null);
        router.refresh();
      }, 1500);
    } catch (err) {
      const e = err as ApiError;
      setError(e.detail || "Upload failed");
      setProgress(null);
    } finally {
      setUploading(false);
    }
  }

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void handleFile(file);
  }

  function onDragOver(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (!dragOver) setDragOver(true);
  }

  function onDragLeave(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (uploading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  function onDelete(doc: DocumentRecord) {
    const toastId = toast(
      `Delete "${doc.filename}"?`,
      {
        description: "The document and its chunks will be removed.",
        duration: Infinity,
        action: {
          label: "Delete",
          onClick: () => {
            void performDelete(doc, toastId);
          },
        },
        cancel: {
          label: "Cancel",
          onClick: () => {
            toast.dismiss(toastId);
          },
        },
      },
    );
  }

  async function performDelete(doc: DocumentRecord, confirmId: string | number) {
    toast.dismiss(confirmId);
    const previous = items;
    setItems((prev) => prev.filter((d) => d.id !== doc.id));

    const loadingId = toast.loading(`Deleting ${doc.filename}…`, {
      description: "Removing the document and its chunks.",
    });

    try {
      await deleteRequest(`/api/v1/documents/${doc.id}`);
      toast.success(`Deleted ${doc.filename}`, {
        id: loadingId,
        description: "The document and its chunks are gone.",
        duration: 4000,
      });
    } catch (err) {
      setItems(previous);
      const e = err as ApiError;
      toast.error(`Could not delete ${doc.filename}`, {
        id: loadingId,
        description: e.detail || "The document is still in your list.",
      });
    }
  }

  async function refreshOne(id: string) {
    try {
      const updated = await api.get<DocumentRecord>(`/api/v1/documents/${id}`);
      setItems((prev) => prev.map((d) => (d.id === id ? updated : d)));
    } catch {
      // ignore
    }
  }

  return (
    <div className="mx-auto mt-8 max-w-3xl space-y-6">
      <label
        onDragOver={onDragOver}
        onDragEnter={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={
          "flex cursor-pointer items-center justify-center rounded-lg border-2 border-dashed p-8 transition " +
          (dragOver
            ? "border-zinc-900 bg-zinc-100 dark:border-zinc-100 dark:bg-zinc-900"
            : "border-zinc-300 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900")
        }
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          onChange={onFile}
          disabled={uploading}
          className="hidden"
        />
        <div className="text-center text-sm">
          <div className="font-medium">
            {uploading
              ? "Uploading…"
              : dragOver
                ? "Drop the PDF to upload"
                : "Drop a PDF here, or click to choose"}
          </div>
          <div className="mt-1 text-zinc-500">PDF up to 20 MB</div>
        </div>
      </label>

      {progress && (
        <p className="text-sm text-zinc-500">{progress}</p>
      )}
      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <ul className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
        {items.length === 0 && (
          <li className="p-6 text-center text-sm text-zinc-500">
            No documents yet. Upload one to get started.
          </li>
        )}
        {items.map((d) => (
          <li key={d.id} className="flex items-center justify-between p-4">
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{d.filename}</div>
              <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                <span>{formatBytes(d.size_bytes)}</span>
                <span>·</span>
                <span>{new Date(d.created_at).toLocaleDateString()}</span>
                {d.error_message && (
                  <>
                    <span>·</span>
                    <span className="truncate text-red-600 dark:text-red-400">
                      {d.error_message}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_COLORS[d.status] ?? ""}`}
              >
                {STATUS_LABELS[d.status] ?? d.status}
              </span>
              {d.status === "processing" && (
                <button
                  type="button"
                  onClick={() => refreshOne(d.id)}
                  className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                >
                  Refresh
                </button>
              )}
              <button
                type="button"
                onClick={() => onDelete(d)}
                className="rounded border border-zinc-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-zinc-700 dark:text-red-400 dark:hover:bg-red-950"
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
