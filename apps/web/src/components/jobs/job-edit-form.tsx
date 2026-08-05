"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { useJob } from "@/lib/queries";
import { JobForm } from "./job-form";

/** Loads a job by id and hands it to JobForm pre-filled for editing. */
export function JobEditForm({ id }: { id: string }) {
  const { data: job, isLoading, error, refetch } = useJob(id);

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !job) return <Skeleton className="h-96 w-full rounded-md" />;

  return <JobForm job={job} />;
}
