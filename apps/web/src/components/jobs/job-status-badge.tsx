import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { JobStatus } from "@open3d-point-cloud-pipeline/shared";

const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
};

// Done gets a green tint via a className override (no dedicated success variant).
const CLASSNAMES: Record<JobStatus, string> = {
  queued: "",
  running: "",
  done: "bg-[var(--brand-b2)] text-white",
  failed: "",
};

const VARIANTS: Record<JobStatus, "default" | "secondary" | "destructive"> = {
  queued: "secondary",
  running: "default",
  done: "default",
  failed: "destructive",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge variant={VARIANTS[status]} className={CLASSNAMES[status]}>
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {LABELS[status]}
    </Badge>
  );
}
