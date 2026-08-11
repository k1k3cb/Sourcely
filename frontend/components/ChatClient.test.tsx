import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Source, StreamEvent } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    streamQuery: vi.fn(),
    getChunkText: vi.fn().mockResolvedValue(""),
  };
});

import * as apiMock from "@/lib/api";
import { ChatClient } from "./ChatClient";

const streamQuery = apiMock.streamQuery as unknown as ReturnType<typeof vi.fn>;
const getChunkText = apiMock.getChunkText as unknown as ReturnType<typeof vi.fn>;

function makeSource(): Source {
  return {
    chunk_id: "chunk-1",
    document_id: "doc-1",
    filename: "paper.pdf",
    mime_type: "application/pdf",
    document_url: "https://example.test/paper.pdf",
    snippet: "Snippet.",
    score: 0.81,
    index: 1,
    page_start: 1,
    page_end: 1,
    start_seconds: null,
    end_seconds: null,
    text: null,
  };
}

async function* fromEvents(events: StreamEvent[]) {
  for (const ev of events) yield ev;
}

beforeEach(() => {
  streamQuery.mockReset();
  getChunkText.mockReset();
  getChunkText.mockResolvedValue("");
  // jsdom doesn't implement HTMLMediaElement.play(); provide a stub.
  if (!window.HTMLMediaElement.prototype.play) {
    Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
      value: vi.fn().mockResolvedValue(undefined),
      configurable: true,
    });
  }
});

describe("ChatClient", () => {
  it("streams tokens into the assistant message and finishes on done", async () => {
    const user = userEvent.setup();
    streamQuery.mockImplementation(() =>
      fromEvents([
        { type: "token", t: "Hola " },
        { type: "sources", sources: [makeSource()] },
        { type: "token", t: "mundo" },
        { type: "done" },
      ]),
    );

    render(<ChatClient />);

    const textarea = screen.getByPlaceholderText(/ask a question/i);
    await user.type(textarea, "qué es sourcely{enter}");

    const userMsg = await screen.findByText("qué es sourcely");
    expect(userMsg).toBeInTheDocument();

    const assistant = await screen.findByText("Hola mundo");
    expect(assistant).toBeInTheDocument();

    await waitFor(() => {
      expect(streamQuery).toHaveBeenCalledOnce();
    });
    expect(streamQuery).toHaveBeenCalledWith("qué es sourcely", 5);

    const button = screen.getByRole("button", { name: /view p\.\s*1/i });
    expect(button).toBeInTheDocument();
  });

  it("surfaces an error from the stream as a red assistant message", async () => {
    const user = userEvent.setup();
    streamQuery.mockImplementation(() =>
      fromEvents([{ type: "error", detail: "Backend unavailable" }]),
    );

    render(<ChatClient />);

    const textarea = screen.getByPlaceholderText(/ask a question/i);
    await user.type(textarea, "fallo{enter}");

    const error = await screen.findByText("Backend unavailable");
    expect(error).toBeInTheDocument();
    expect(error.className).toMatch(/text-red/);

    await waitFor(() => {
      expect(streamQuery).toHaveBeenCalledOnce();
    });

    // Input re-enabled after the failed ask.
    await waitFor(() => {
      expect(
        (screen.getByPlaceholderText(/ask a question/i) as HTMLTextAreaElement)
          .disabled,
      ).toBe(false);
    });
  });
});
