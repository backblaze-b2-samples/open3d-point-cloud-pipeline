import { ScansLibrary } from "@/components/scans/scans-library";

export default function ScansPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Scans</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground text-pretty">
          Ingest LiDAR &amp; photogrammetry point clouds (PLY, PCD, LAS, LAZ) into
          Backblaze B2. This scoped Library shows the <code>raw/</code> prefix —
          the source scans your processing jobs run on.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <ScansLibrary />
      </div>
    </div>
  );
}
