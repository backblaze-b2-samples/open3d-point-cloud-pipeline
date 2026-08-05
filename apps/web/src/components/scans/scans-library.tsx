"use client";

import Link from "next/link";
import { toast } from "sonner";
import { Boxes, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { UploadForm } from "@/components/upload/upload-form";
import { useDeleteFile, useFiles } from "@/lib/queries";

/**
 * Scoped Library for ingested scans — the `raw/` prefix only. This is the
 * sample-specific asset explorer that sits alongside the full-bucket /files
 * explorer, with a point-cloud-typed upload folded in.
 */
export function ScansLibrary() {
  const { data: scans = [], isLoading, error, refetch } = useFiles("raw/", 1000);
  const deleteFile = useDeleteFile();

  const onDelete = async (key: string) => {
    try {
      await deleteFile.mutateAsync(key);
      toast.success("Scan deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="space-y-8">
      <UploadForm />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between border-b border-border py-4 px-5">
          <CardTitle className="card-title">Ingested scans (raw/)</CardTitle>
          {scans.length > 0 && (
            <Button asChild size="sm" variant="outline">
              <Link href="/jobs/new">Create job</Link>
            </Button>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : isLoading ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : scans.length === 0 ? (
            <EmptyState
              icon={Boxes}
              title="No scans ingested yet"
              description="Upload PLY / PCD / LAS / LAZ point clouds above, or run services/api/scripts/seed_samples.py to add synthetic sample scans."
            />
          ) : (
            <ul className="divide-y divide-border">
              {scans.map((scan) => (
                <li
                  key={scan.key}
                  className="flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="stat-icon-wrap">
                      <Boxes className="h-4 w-4" aria-hidden />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {scan.filename}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {scan.size_human} ·{" "}
                        {new Date(scan.uploaded_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <ConfirmDialog
                    title="Delete this scan?"
                    description={`Remove ${scan.filename} from the bucket. Jobs already created from it keep their own artifacts.`}
                    onConfirm={() => onDelete(scan.key)}
                    trigger={
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Delete ${scan.filename}`}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
