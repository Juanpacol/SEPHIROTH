"use client";

/** Drag-and-drop replacement for typing a server-side file path on
 * `/imaging`. Shows an instant client-side preview via `URL.createObjectURL`
 * the moment a file is dropped/picked — before the upload round trip even
 * finishes — then uploads it and reports back the server path
 * `analyzeImage`/`describeImage` still expect (see `api.uploadImage`). */

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileImage, Loader2, UploadCloud, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/toast";

const ACCEPTED = ".png,.jpg,.jpeg,.gif,.webp,.bmp";

export default function ImageDropzone({
  onUploaded,
}: {
  onUploaded: (path: string) => void;
}) {
  const showToast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadImage(file),
    onSuccess: (res) => onUploaded(res.path),
    onError: (err) => {
      showToast(err instanceof ApiError ? err.message : "Could not upload the image.", "error");
      clear();
    },
  });

  // Revoke the blob URL when replaced or on unmount — otherwise each drop
  // leaks the previous preview's memory for the life of the tab.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewUrl]);

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
    setFileName(file.name);
    onUploaded(""); // clear any previously-uploaded path while this one is in flight
    upload.mutate(file);
  };

  const clear = () => {
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setFileName(null);
    onUploaded("");
    if (inputRef.current) inputRef.current.value = "";
  };

  if (previewUrl) {
    return (
      <div className="relative h-full min-h-[220px] w-full">
        <img
          src={previewUrl}
          alt="Selected medical image"
          className="max-h-[420px] w-full rounded-lg object-contain"
        />
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 rounded-b-lg bg-ink/70 px-3 py-2 text-xs text-white">
          <span className="min-w-0 flex-1 truncate">{fileName}</span>
          {upload.isPending && (
            <span className="flex items-center gap-1 shrink-0">
              <Loader2 size={13} className="animate-spin" /> Uploading…
            </span>
          )}
          <button
            onClick={clear}
            aria-label="Remove image"
            className="shrink-0 rounded-full p-1 hover:bg-white/20"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFile(e.dataTransfer.files?.[0]);
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      className={`flex h-full min-h-[220px] w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
        dragOver ? "border-primary bg-primary-soft/50" : "border-line/70 hover:border-primary/50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      {dragOver ? <FileImage size={28} className="text-primary" /> : <UploadCloud size={28} className="text-muted" />}
      <p className="text-sm font-medium">Drag & drop an image here</p>
      <p className="text-xs text-muted">or click to browse — from your Downloads or anywhere else</p>
      <p className="text-xs text-muted">PNG, JPG, GIF, WEBP, or BMP</p>
    </div>
  );
}
