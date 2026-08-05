# Product

## Register

product

## Users

3D-scanning engineers, AEC/BIM professionals, and robotics/AV perception teams who
work with LiDAR and photogrammetry point clouds. Their context: they have raw scans
(PLY / PCD / LAS / LAZ) and want a reproducible, storage-backed pipeline that turns
them into meshes and previews, with every artifact durably kept in object storage —
without standing up a database or a second AI service. Developers and AI coding agents
also use it as a reference for wiring Open3D processing to Backblaze B2.

## Product Purpose

A B2-backed 3D point-cloud processing pipeline (Next.js 16 + React 19 + Tailwind v4 +
shadcn/ui frontend, FastAPI + Open3D backend). Users ingest raw scans into Backblaze
B2, then run an on-device Open3D pipeline — downsample → optional multi-scan
registration → surface meshing → offscreen preview render — and every artifact
(processed cloud, mesh, preview PNG, job manifest) is written back to B2. It
demonstrates B2 as the storage layer for the largest single artifacts in a 3D
workflow, where one source cloud fans out into several derived objects (heavy,
structured write-amplification). Success = a user can clone it, seed synthetic scans,
run a job, and see real meshes and previews stored in their own bucket. Processing is
CPU-only and needs no second API key.

## Brand Personality

Confident, precise, quietly professional. Voice is direct and free of hype. The
interface should feel like a modern engineering tool for 3D data — considered, calm,
trustworthy — not a marketing showpiece. It carries craft through restraint: the data
(clouds, meshes, previews, metrics) is the hero, not decorative chrome.

## Anti-references

- **Generic AI/SaaS slop.** No gradient text, hero-metric templates, identical
  icon-card grids, tracked uppercase eyebrows, or decorative glassmorphism. These are
  the exact 2026 AI tells this kit exists to help builders avoid.
- **Over-branded / loud.** No heavy brand-color drenching, decorative motion, or flashy
  effects. It is scaffolding to be rebranded, not a hero page.
- **Toy / prototype feel.** No missing states, inconsistent components, or placeholder
  polish. Must read as production-grade.
- **Enterprise-drab.** No Bootstrap-era gray boxes or dense-but-lifeless admin-panel
  look. Considered, like modern dev tools (Linear, GitHub Primer, Stripe).

## Design Principles

- **Production-grade throughout.** Every screen models the quality a real 3D tool
  needs — no half-shipped states, no placeholder polish.
- **Consistent, token-driven design.** Identity lives in tokens (`globals.css`);
  screens are built from the shared UI kit so the look stays coherent across Scans,
  Jobs, the explorer, and the dashboard.
- **Earned familiarity over novelty.** Use standard, trusted affordances (top bar +
  side nav, command palette, data tables). The tool disappears into the task.
- **Every state is designed.** Default, hover, focus, active, disabled, loading (skeleton),
  empty (teaches the interface), and error (says what's wrong + offers retry) — never
  half-shipped.
- **Consistency is the feature.** One button vocabulary, one form-control set, one icon
  style across every screen. Divergence is a bug.

## Accessibility & Inclusion

Target **WCAG 2.1 AA**. Body text ≥ 4.5:1, large/bold text ≥ 3:1, visible focus
indicators on every interactive element, full keyboard navigation, correct semantic
landmarks and heading order, labelled form controls, and a `prefers-reduced-motion`
alternative for every animation. Full light and dark theme parity.
