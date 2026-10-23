"use client";

/** The picture behind an imaging event. The preview endpoint wants the JWT, which an `<img src>` cannot send,
 * so it is fetched as a blob (cached, one request per study) and shown from an object URL. While it loads, and
 * if it cannot be had, a quiet placeholder with the image icon stands in: the event reads fine without it. */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Image as ImageIcon } from "lucide-react";
import { api } from "@/lib/api";

export default function EventThumb({
  path,
  alt,
  className = "h-14 w-14",
}: {
  path: string;
  alt: string;
  /** Size and shape; the picture fills it. */
  className?: string;
}) {
  const { data: blob } = useQuery({
    queryKey: ["image-preview", path],
    queryFn: () => api.imagePreviewBlob(path),
    staleTime: Infinity,
    retry: false,
  });
  const [url, setUrl] = useState<string | null>(null);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    if (!blob) return;
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    setBroken(false);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  return (
    <span
      className={`media-edge relative flex shrink-0 items-center justify-center overflow-hidden rounded-xl bg-primary-soft/40 ${className}`}
    >
      {url && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element -- an object URL, not a file Next can optimise
        <img src={url} alt={alt} onError={() => setBroken(true)} className="h-full w-full object-cover" />
      ) : (
        <ImageIcon size={18} strokeWidth={1.5} aria-hidden className="text-muted" />
      )}
    </span>
  );
}
