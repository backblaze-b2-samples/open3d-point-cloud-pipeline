import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { JobPreview } from "./job-preview";
import { usePreviewUrl } from "@/lib/queries";

// The preview normally resolves a presigned B2 URL via TanStack Query and paints
// it with next/image. Neither is exercisable in a node unit test, so both are
// mocked: `usePreviewUrl` returns a canned query result and `next/image` renders
// a plain <img>. That leaves the branch logic under test — which state the
// component renders for a given status/previewKey — as the real subject.
vi.mock("@/lib/queries", () => ({ usePreviewUrl: vi.fn() }));
vi.mock("next/image", async () => {
  const { createElement: ce } = await import("react");
  return {
    default: (props: { src?: string; alt?: string }) =>
      ce("img", { src: props.src, alt: props.alt }),
  };
});

const mockUsePreviewUrl = vi.mocked(usePreviewUrl);

function render(props: Parameters<typeof JobPreview>[0]) {
  return renderToStaticMarkup(createElement(JobPreview, props));
}

describe("JobPreview", () => {
  beforeEach(() => {
    // Default: no preview URL resolved (the running/queued/idle states never
    // reach the image branch anyway, since their previewKey is null).
    mockUsePreviewUrl.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof usePreviewUrl>);
  });

  it("renders a distinct in-progress state for a RUNNING job (spinner + stages, not the idle placeholder)", () => {
    const html = render({
      previewKey: null,
      alt: "Preview of Living room scan",
      status: "running",
      registerScans: true,
      meshingMethod: "poisson",
    });

    // Animated spinner + a processing label — the in-progress affordance the
    // idle placeholder lacks.
    expect(html).toContain("animate-spin");
    expect(html).toContain("Processing");
    // The real pipeline stages this job will run, in order.
    expect(html).toContain("Downsample");
    expect(html).toContain("Register scans");
    expect(html).toContain("Mesh surface (Poisson)");
    expect(html).toContain("Render preview");
    // Must NOT collapse into the generic idle placeholder.
    expect(html).not.toContain("No preview yet");
  });

  it("omits the registration stage when the job does not register scans", () => {
    const html = render({
      previewKey: null,
      alt: "Preview of Single scan",
      status: "running",
      registerScans: false,
      meshingMethod: "ball_pivoting",
    });

    expect(html).toContain("Downsample");
    expect(html).toContain("Mesh surface (ball-pivoting)");
    expect(html).toContain("Render preview");
    expect(html).not.toContain("Register scans");
    expect(html).not.toContain("No preview yet");
  });

  it("renders the idle placeholder for a QUEUED (never-run) job, not the in-progress tile", () => {
    // In this app's lifecycle `queued` means "created but not yet run" (an idle
    // job showing a Run button), so it must read as idle — never a spinner.
    const html = render({
      previewKey: null,
      alt: "Preview of Queued scan",
      status: "queued",
      registerScans: false,
      meshingMethod: "poisson",
    });

    expect(html).toContain("No preview yet");
    expect(html).not.toContain("animate-spin");
    expect(html).not.toContain("Processing");
  });

  it("renders the idle placeholder for a job with no preview and no in-progress status", () => {
    const html = render({
      previewKey: null,
      alt: "Preview of Idle scan",
    });

    expect(html).toContain("No preview yet");
    expect(html).not.toContain("animate-spin");
    expect(html).not.toContain("Processing");
  });

  it("paints the rendered preview image once a done job resolves its URL (not the in-progress state)", () => {
    mockUsePreviewUrl.mockReturnValue({
      data: { url: "https://b2.example/jobs/abc/preview.png" },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof usePreviewUrl>);

    const html = render({
      previewKey: "jobs/abc/preview.png",
      alt: "Preview of Done scan",
      status: "done",
    });

    expect(html).toContain("preview.png");
    expect(html).not.toContain("Processing");
    expect(html).not.toContain("No preview yet");
  });
});
