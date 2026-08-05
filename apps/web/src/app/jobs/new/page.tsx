import { JobForm } from "@/components/jobs/job-form";

export default function NewJobPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">New job</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground text-pretty">
          Configure a processing job. Pick the source scans, choose a meshing
          method, and create it — then press Run on the job to process on-device
          with Open3D.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2 max-w-2xl">
        <JobForm />
      </div>
    </div>
  );
}
