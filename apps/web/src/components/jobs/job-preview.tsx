"use client";

import { useState } from "react";
import Image from "next/image";
import { Boxes } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { usePreviewUrl } from "@/lib/queries";

function PlaceholderTile({ label }: { label: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-muted text-muted-foreground">
      <Boxes className="h-6 w-6" aria-hidden />
      <span className="text-xs">{label}</span>
    </div>
  );
}

/**
 * Preview PNG for a job, served from B2 via a short-lived presigned URL. The
 * PNG is rendered by the pipeline and stored at jobs/<id>/preview.png, so this
 * is proof of the "rendered previews served from B2" feature.
 */
export function JobPreview({
  previewKey,
  alt,
  sizes = "(max-width: 768px) 100vw, 320px",
}: {
  previewKey: string | null;
  alt: string;
  sizes?: string;
}) {
  const { data, isLoading, isError } = usePreviewUrl(
    previewKey ?? undefined,
    !!previewKey
  );
  const [imgState, setImgState] = useState<"loading" | "ready" | "error">("loading");

  if (!previewKey) return <PlaceholderTile label="No preview yet" />;
  if (isLoading || !data) return <Skeleton className="h-full w-full" />;
  if (isError || imgState === "error")
    return <PlaceholderTile label="Preview unavailable" />;

  return (
    <div key={data.url} className="relative h-full w-full">
      <Image
        src={data.url}
        alt={alt}
        fill
        sizes={sizes}
        unoptimized
        className={`object-contain ${imgState === "ready" ? "" : "opacity-0"}`}
        onLoad={() => setImgState("ready")}
        onError={() => setImgState("error")}
      />
      {imgState === "loading" && <Skeleton className="absolute inset-0" />}
    </div>
  );
}
