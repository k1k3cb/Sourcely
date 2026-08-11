import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SourceCard } from "./SourceCard";
import type { Source } from "@/lib/api";

function makePdfSource(): Source {
  return {
    chunk_id: "chunk-1",
    document_id: "doc-1",
    filename: "paper.pdf",
    mime_type: "application/pdf",
    document_url: "https://example.test/paper.pdf",
    snippet: "Findings of the report.",
    score: 0.86,
    index: 1,
    page_start: 4,
    page_end: 4,
    start_seconds: null,
    end_seconds: null,
    text: null,
  };
}

function makeAudioSource(): Source {
  return {
    chunk_id: "chunk-2",
    document_id: "doc-2",
    filename: "interview.mp3",
    mime_type: "audio/mpeg",
    document_url: "https://example.test/interview.mp3",
    snippet: "He said it was around noon.",
    score: 0.71,
    index: 2,
    page_start: null,
    page_end: null,
    start_seconds: 110,
    end_seconds: 139,
    text: null,
  };
}

describe("SourceCard", () => {
  it("renders the PDF deep-link button instead of the audio jump button", () => {
    render(
      <SourceCard
        source={makePdfSource()}
        onSeekAudio={() => {}}
        onStopAudio={() => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: /view p\.\s*4/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/jump to/i)).not.toBeInTheDocument();
  });

  it("renders the audio jump button when idle", () => {
    render(
      <SourceCard
        source={makeAudioSource()}
        onSeekAudio={() => {}}
        onStopAudio={() => {}}
        activeAudioId={null}
      />,
    );
    expect(
      screen.getByRole("button", { name: /jump to 1:50/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /stop/i })).not.toBeInTheDocument();
  });

  it("swaps to the stop button when this chunk is the active audio", () => {
    const source = makeAudioSource();
    const onSeekAudio = vi.fn();
    const onStopAudio = vi.fn();

    render(
      <SourceCard
        source={source}
        onSeekAudio={onSeekAudio}
        onStopAudio={onStopAudio}
        activeAudioId={source.chunk_id}
      />,
    );

    const stop = screen.getByRole("button", { name: /stop/i });
    expect(stop).toBeInTheDocument();
    stop.click();
    expect(onStopAudio).toHaveBeenCalledOnce();

    // Only the stop button should be rendered; no jump-to control.
    expect(screen.queryByText(/jump to/i)).toBeNull();
    expect(onSeekAudio).not.toHaveBeenCalled();
  });
});
