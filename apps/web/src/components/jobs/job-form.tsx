"use client";

import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import Link from "next/link";
import { Boxes } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { useCreateJob, useFiles, useUpdateJob } from "@/lib/queries";
import type { Job } from "@open3d-point-cloud-pipeline/shared";

const schema = z.object({
  name: z.string().min(1, "Give the job a name").max(120),
  source_keys: z.array(z.string()).min(1, "Select at least one scan to process"),
  meshing_method: z.enum(["poisson", "ball_pivoting"]),
  register_scans: z.boolean(),
  // Kept as a string field (parsed on submit) like the settings-form number
  // fields, so the input never fights react-hook-form over number coercion.
  voxel_size: z
    .string()
    .regex(/^\d*\.?\d+$/, "Enter a positive number")
    .refine((v) => {
      const n = Number(v);
      return n > 0 && n <= 10;
    }, "Between 0 and 10"),
});

type JobFormValues = z.infer<typeof schema>;

function toDefaults(job?: Job): JobFormValues {
  return {
    name: job?.name ?? "",
    source_keys: job?.source_keys ?? [],
    meshing_method: job?.meshing_method ?? "poisson",
    register_scans: job?.register_scans ?? false,
    voxel_size: job ? String(job.voxel_size) : "0.02",
  };
}

export function JobForm({ job }: { job?: Job }) {
  const isEdit = Boolean(job);
  const router = useRouter();
  const { data: scans = [], isLoading: scansLoading } = useFiles("raw/", 1000);
  const createJob = useCreateJob();
  const updateJob = useUpdateJob(job?.id ?? "");

  const form = useForm<JobFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toDefaults(job),
  });

  // useWatch (not form.watch) so the React Compiler can memoize this component.
  const selected = useWatch({ control: form.control, name: "source_keys" });
  const canRegister = selected.length >= 2;

  const onSubmit = async (values: JobFormValues) => {
    const payload = {
      name: values.name,
      source_keys: values.source_keys,
      meshing_method: values.meshing_method,
      // Registration only takes effect with >= 2 sources.
      register_scans: values.register_scans && values.source_keys.length >= 2,
      voxel_size: Number(values.voxel_size),
    };
    try {
      if (isEdit && job) {
        await updateJob.mutateAsync(payload);
        toast.success("Job updated");
        router.push(`/jobs/${job.id}`);
      } else {
        const created = await createJob.mutateAsync(payload);
        toast.success("Job created", {
          description: "Open it and press Run to process the scans.",
        });
        router.push(`/jobs/${created.id}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the job");
    }
  };

  const submitting = createJob.isPending || updateJob.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">
              {isEdit ? "Edit job" : "New processing job"}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={
                        isEdit ? undefined : "e.g. Warehouse scan — east wing"
                      }
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="source_keys"
              render={() => (
                <FormItem>
                  <FormLabel>Source scans</FormLabel>
                  <FormDescription>
                    Pick one or more ingested scans from the{" "}
                    <code>raw/</code> prefix. Registration needs at least two.
                  </FormDescription>
                  {scansLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-9 w-full" />
                      <Skeleton className="h-9 w-full" />
                    </div>
                  ) : scans.length === 0 ? (
                    <EmptyState
                      icon={Boxes}
                      title="No scans in the bucket yet"
                      description="Upload point clouds on the Scans page, or run services/api/scripts/seed_samples.py to add synthetic ones."
                      action={
                        <Button asChild size="sm" variant="outline">
                          <Link href="/scans">Go to Scans</Link>
                        </Button>
                      }
                    />
                  ) : (
                    <div className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-border p-2">
                      {scans.map((scan) => (
                        <ScanCheckbox
                          key={scan.key}
                          label={scan.filename}
                          hint={scan.size_human}
                          checked={selected.includes(scan.key)}
                          onToggle={(on) => {
                            const next = on
                              ? [...selected, scan.key]
                              : selected.filter((k) => k !== scan.key);
                            form.setValue("source_keys", next, {
                              shouldValidate: true,
                            });
                          }}
                        />
                      ))}
                    </div>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="meshing_method"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Meshing method</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-60">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="poisson">Poisson (watertight)</SelectItem>
                      <SelectItem value="ball_pivoting">
                        Ball pivoting (surface)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  {!isEdit && (
                    <FormDescription>
                      Poisson is the default and works well for the sample scans.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="register_scans"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-md border border-border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>Register scans</FormLabel>
                    <FormDescription>
                      {canRegister
                        ? "Align the selected scans (FPFH + RANSAC, ICP refine) before meshing."
                        : "Select two or more scans to enable multi-scan registration."}
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value && canRegister}
                      disabled={!canRegister}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="voxel_size"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Voxel size</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      className="w-40 font-mono tabular-nums"
                      {...field}
                    />
                  </FormControl>
                  {!isEdit && (
                    <FormDescription>
                      0.02 — leave the default for the sample scans. Larger values
                      downsample more aggressively.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting
              ? "Saving..."
              : isEdit
                ? "Save changes"
                : "Create job"}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function ScanCheckbox({
  label,
  hint,
  checked,
  onToggle,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onToggle: (on: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded px-2 py-1.5 hover:bg-muted/60">
      <Checkbox
        checked={checked}
        onCheckedChange={(v) => onToggle(v === true)}
      />
      <span className="min-w-0 flex-1 truncate text-sm">{label}</span>
      <span className="text-xs text-muted-foreground">{hint}</span>
    </label>
  );
}
