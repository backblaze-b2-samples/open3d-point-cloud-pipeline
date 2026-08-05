import { JobEditForm } from "@/components/jobs/job-edit-form";

export default async function EditJobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Edit job</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground text-pretty">
          Update this job&apos;s scans and processing options. Changes take
          effect the next time you run it.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2 max-w-2xl">
        <JobEditForm id={id} />
      </div>
    </div>
  );
}
