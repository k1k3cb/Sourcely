import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const toastMock = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({
  toast: toastMock,
  Toaster: () => null,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    uploadFile: vi.fn(),
    deleteRequest: vi.fn(),
    api: { get: vi.fn(), post: vi.fn() },
  };
});

import * as apiMock from "@/lib/api";
import { DocumentsClient } from "./DocumentsClient";

const uploadFile = apiMock.uploadFile as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  uploadFile.mockReset();
  toastMock.mockReset();
});

function dispatchFileUpload(input: HTMLInputElement, file: File) {
  Object.defineProperty(input, "files", {
    value: [file],
    configurable: true,
  });
  fireEvent.change(input);
}

describe("DocumentsClient", () => {
  it("rejects non-accepted files without calling the upload endpoint", async () => {
    render(<DocumentsClient initial={[]} />);

    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    expect(input).toBeTruthy();

    dispatchFileUpload(
      input,
      new File(["hello"], "notes.txt", { type: "text/plain" }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/unsupported file type/i),
      ).toBeInTheDocument();
    });

    expect(uploadFile).not.toHaveBeenCalled();
  });
});
