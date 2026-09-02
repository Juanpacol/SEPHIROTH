import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ImageDropzone from "@/components/image-dropzone";
import { api } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>{ui}</LanguageProvider>
    </QueryClientProvider>
  );
}

vi.mock("@/lib/api", () => ({
  api: { uploadImage: vi.fn() },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

const showToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => showToast,
}));

function makeFile(name = "scan.png", type = "image/png") {
  return new File(["fake image bytes"], name, { type });
}

describe("ImageDropzone", () => {
  beforeEach(() => {
    showToast.mockClear();
    vi.mocked(api.uploadImage).mockReset();
    URL.createObjectURL = vi.fn(() => "blob:fake-url");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the drop target with no file selected", () => {
    renderWithClient(<ImageDropzone onUploaded={vi.fn()} />);
    expect(screen.getByText("Drag & drop an image here")).toBeInTheDocument();
  });

  it("previews and uploads a file picked via the hidden input, reporting the returned path", async () => {
    vi.mocked(api.uploadImage).mockResolvedValue({ path: "/tmp/sephiroth-imaging-uploads/abc.png" });
    const onUploaded = vi.fn();
    const { container } = renderWithClient(<ImageDropzone onUploaded={onUploaded} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByAltText("Selected medical image")).toBeInTheDocument();
    expect(screen.getByText("scan.png")).toBeInTheDocument();

    await waitFor(() =>
      expect(onUploaded).toHaveBeenLastCalledWith("/tmp/sephiroth-imaging-uploads/abc.png")
    );
  });

  it("shows a toast and clears the preview when upload fails", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(api.uploadImage).mockRejectedValue(new ApiError(415, "Unsupported file type"));
    const onUploaded = vi.fn();
    const { container } = renderWithClient(<ImageDropzone onUploaded={onUploaded} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile()] } });

    await waitFor(() => expect(showToast).toHaveBeenCalledWith("Unsupported file type", "error"));
    await waitFor(() => expect(screen.getByText("Drag & drop an image here")).toBeInTheDocument());
  });

  it("clears the preview when the remove button is clicked", async () => {
    vi.mocked(api.uploadImage).mockResolvedValue({ path: "/tmp/x.png" });
    const onUploaded = vi.fn();
    const { container } = renderWithClient(<ImageDropzone onUploaded={onUploaded} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile()] } });
    await waitFor(() => expect(onUploaded).toHaveBeenLastCalledWith("/tmp/x.png"));

    fireEvent.click(screen.getByLabelText("Remove image"));

    expect(screen.getByText("Drag & drop an image here")).toBeInTheDocument();
    expect(onUploaded).toHaveBeenLastCalledWith("");
  });
});
