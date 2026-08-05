"use client";

import { useState } from "react";
import Image from "next/image";
import { Boxes, Loader2 } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { usePreviewUrl } from "@/lib/queries";
import type { JobStatus, MeshingMethod } from "@open3d-point-cloud-pipeline/shared";

function PlaceholderTile({ label }: { label: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-muted text-muted-foreground">
      <Boxes className="h-6 w-6" aria-hidden />
      <span className="text-xs">{label}</span>
    </div>
  );
}

/**
 * In-progress state for a running job. The backend runs the pipeline in
 * a subprocess and streams NO per-stage progress, so this is deliberately
 * INDETERMINATE (a spinner + pulsing bar, never a fabricated percentage). It
 * lists the exact stages this job will run so the main content area shows real
 * work is underway — distinct from both the idle "No preview yet" placeholder
 * and the error state.
 */
function ProcessingTile({
  registerScans,
  meshingMethod,
}: {
  registerScans?: boolean;
  meshingMethod?: MeshingMethod;
}) {
  const meshLabel =
    meshingMethod === "ball_pivoting"
      ? "Mesh surface (ball-pivoting)"
      : meshingMethod === "poisson"
        ? "Mesh surface (Poisson)"
        : "Mesh surface (Poisson or ball-pivoting)";
  const stages = [
    "Downsample & outlier removal",
    ...(registerScans ? ["Register scans (FPFH/RANSAC + ICP)"] : []),
    meshLabel,
    "Render preview",
  ];
  const label = "Processing…";
  return (
    <div
      role="status"
      className="flex h-full w-full flex-col items-center justify-center gap-3 bg-muted p-4 text-muted-foreground"
    >
      <div className="flex items-center gap-2 text-foreground">
        <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="h-1 w-40 overflow-hidden rounded-full bg-border">
        <div className="h-full w-full animate-pulse bg-primary/60" />
      </div>
      <ol className="space-y-1 text-xs">
        {stages.map((stage) => (
          <li key={stage} className="flex items-center gap-2">
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50"
              aria-hidden
            />
            {stage}
          </li>
        ))}
      </ol>
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
  status,
  registerScans,
  meshingMethod,
}: {
  previewKey: string | null;
  alt: string;
  sizes?: string;
  // Optional so the jobs-list thumbnail (which passes only `previewKey`) keeps
  // compiling. When present, a running job renders a distinct in-progress
  // state instead of the generic "No preview yet" placeholder.
  status?: JobStatus;
  registerScans?: boolean;
  meshingMethod?: MeshingMethod;
}) {
  const { data, isLoading, isError } = usePreviewUrl(
    previewKey ?? undefined,
    !!previewKey
  );
  const [imgState, setImgState] = useState<"loading" | "ready" | "error">("loading");

  // A running job is actively producing its preview — show the pipeline
  // stages, not the idle placeholder. This wins over a stale preview from a
  // previous run so a re-run reads as "working" too. A `queued` job has been
  // created but not yet run (an idle job with a Run button), so it falls
  // through to the "No preview yet" placeholder rather than this tile.
  if (status === "running")
    return (
      <ProcessingTile
        registerScans={registerScans}
        meshingMethod={meshingMethod}
      />
    );

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
        // Load eagerly: this <img> mounts in place when a job polls
        // running->done, and the default lazy loading fails to trigger on that
        // conditional mount (the image stays at naturalWidth 0 until a fresh
        // navigation). Eager loading paints it as soon as the URL resolves.
        loading="eager"
        className={`object-contain ${imgState === "ready" ? "" : "opacity-0"}`}
        onLoad={() => setImgState("ready")}
        onError={() => setImgState("error")}
      />
      {imgState === "loading" && <Skeleton className="absolute inset-0" />}
    </div>
  );
}
