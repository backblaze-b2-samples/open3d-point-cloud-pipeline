"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Download,
  Pencil,
  Play,
  RotateCw,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { getDownloadUrl } from "@/lib/api-client";
import { startBrowserDownload } from "@/lib/browser-download";
import { useDeleteJob, useJob, useRunJob } from "@/lib/queries";
import type { Job, JobArtifact } from "@open3d-point-cloud-pipeline/shared";
import { JobPreview } from "./job-preview";
import { JobStatusBadge } from "./job-status-badge";

async function downloadArtifact(artifact: JobArtifact) {
  try {
    const { url } = await getDownloadUrl(artifact.key);
    const filename = artifact.key.split("/").pop() ?? artifact.name;
    startBrowserDownload(url, filename);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Download failed");
  }
}

export function JobDetail({ id }: { id: string }) {
  const router = useRouter();
  const { data: job, isLoading, error, refetch } = useJob(id);
  const runJob = useRunJob();
  const deleteJob = useDeleteJob();

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !job) return <Skeleton className="h-96 w-full rounded-md" />;

  const busy = job.status === "running" || runJob.isPending;

  const onRun = async () => {
    try {
      await runJob.mutateAsync(job.id);
      toast.success("Processing started");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start the run");
    }
  };

  const onDelete = async () => {
    try {
      await deleteJob.mutateAsync(job.id);
      toast.success("Job deleted");
      router.push("/jobs");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-5">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="page-title truncate">{job.name}</h1>
            <JobStatusBadge status={job.status} />
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {job.source_keys.length} source scan
            {job.source_keys.length === 1 ? "" : "s"} · updated{" "}
            {new Date(job.updated_at).toLocaleString()}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onRun} disabled={busy} size="sm">
            {job.status === "done" || job.status === "failed" ? (
              <RotateCw className="h-3.5 w-3.5" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {job.status === "done" || job.status === "failed" ? "Re-run" : "Run"}
          </Button>
          <Button asChild size="sm" variant="outline" disabled={busy}>
            <Link href={`/jobs/${job.id}/edit`}>
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Link>
          </Button>
          <ConfirmDialog
            title="Delete this job?"
            description="This removes the job manifest and all of its artifacts (processed cloud, mesh, preview) from B2. This cannot be undone."
            onConfirm={onDelete}
            trigger={
              <Button size="sm" variant="outline" className="text-destructive">
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            }
          />
        </div>
      </div>

      {job.status === "failed" && job.error && (
        <Alert variant="destructive">
          <AlertTitle>Processing failed</AlertTitle>
          <AlertDescription>{job.error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <div className="relative aspect-video bg-muted">
            <JobPreview
              previewKey={job.preview_key}
              alt={`Preview of ${job.name}`}
              sizes="(max-width: 1024px) 100vw, 600px"
              status={job.status}
              registerScans={job.register_scans}
              meshingMethod={job.meshing_method}
            />
          </div>
        </Card>

        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Configuration</CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            <ConfigRow label="Meshing method" value={job.meshing_method} />
            <ConfigRow
              label="Registration"
              value={job.register_scans ? "On" : "Off"}
            />
            <ConfigRow label="Voxel size" value={String(job.voxel_size)} />
            <div className="pt-2">
              <p className="text-xs font-medium text-muted-foreground">Sources</p>
              <ul className="mt-1 space-y-0.5">
                {job.source_keys.map((key) => (
                  <li key={key} className="truncate font-mono text-xs">
                    {key}
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      {job.status === "done" && (
        <>
          <MetricsCard job={job} />
          <ArtifactsCard job={job} />
        </>
      )}
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium capitalize">{value}</span>
    </div>
  );
}

function MetricsCard({ job }: { job: Job }) {
  const m = job.metrics;
  const rows: [string, string][] = [
    ["Source points", m.source_points.toLocaleString()],
    ["Processed points", m.downsampled_points.toLocaleString()],
    ["Mesh vertices", m.mesh_vertices.toLocaleString()],
    ["Mesh triangles", m.mesh_triangles.toLocaleString()],
    ["Registered", m.registered ? "Yes" : "No"],
    ["Run time", `${m.duration_seconds}s`],
  ];
  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Run metrics</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        <div className="mb-4 rounded-md border border-border bg-muted/40 p-4">
          <p className="text-xs font-medium text-muted-foreground">
            Write amplification
          </p>
          <p className="stat-value">{m.write_amplification}×</p>
          <p className="text-xs text-muted-foreground">
            {m.artifact_bytes.toLocaleString()} bytes of artifacts from{" "}
            {m.source_bytes.toLocaleString()} bytes of source — one scan fans out
            into processed cloud + mesh + preview on B2.
          </p>
        </div>
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between border-b border-border py-1.5"
            >
              <span className="text-sm text-muted-foreground">{label}</span>
              <span className="text-sm font-medium tabular-nums">{value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ArtifactsCard({ job }: { job: Job }) {
  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Artifacts on B2</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        <ul className="space-y-2">
          {job.artifacts.map((artifact) => (
            <li
              key={artifact.key}
              className="flex items-center justify-between gap-3 rounded-md border border-border p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium capitalize">
                  {artifact.name.replace("_", " ")}
                </p>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {artifact.key} · {artifact.size_human}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => downloadArtifact(artifact)}
              >
                <Download className="h-3.5 w-3.5" />
                Download
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
