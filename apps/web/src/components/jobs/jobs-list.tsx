"use client";

import Link from "next/link";
import { Plus, Workflow } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useJobs } from "@/lib/queries";
import { JobPreview } from "./job-preview";
import { JobStatusBadge } from "./job-status-badge";

export function JobsList() {
  const { data: jobs = [], isLoading, error, refetch } = useJobs();

  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={Workflow}
            title="No processing jobs yet"
            description="Create a job to downsample, optionally register, and mesh your scans — every artifact is written back to B2."
            action={
              <Button asChild size="sm">
                <Link href="/jobs/new">
                  <Plus className="h-3.5 w-3.5" />
                  New job
                </Link>
              </Button>
            }
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {jobs.map((job) => (
        <Link key={job.id} href={`/jobs/${job.id}`} className="group">
          <Card className="card-hover overflow-hidden">
            <div className="relative aspect-video bg-muted">
              <JobPreview previewKey={job.preview_key} alt={`Preview of ${job.name}`} />
            </div>
            <CardContent className="space-y-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate font-semibold group-hover:text-primary">
                  {job.name}
                </p>
                <JobStatusBadge status={job.status} />
              </div>
              <p className="text-xs text-muted-foreground">
                {job.source_keys.length} source
                {job.source_keys.length === 1 ? "" : "s"} · {job.meshing_method}
                {job.register_scans ? " · registered" : ""}
              </p>
              {job.status === "done" && (
                <p className="text-xs text-muted-foreground">
                  {job.metrics.mesh_triangles.toLocaleString()} triangles ·{" "}
                  {job.metrics.write_amplification}× write amp
                </p>
              )}
              {job.status === "failed" && job.error && (
                <p className="truncate text-xs text-destructive">{job.error}</p>
              )}
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
