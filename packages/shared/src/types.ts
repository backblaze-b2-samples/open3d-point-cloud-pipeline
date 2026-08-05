export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  /** Set when a format-specific extractor was skipped or failed (e.g. an image
   *  above the decompression-bomb decode limit). Core fields stay exact. */
  metadata_warning: string | null;
  // Image-specific
  image_width: number | null;
  image_height: number | null;
  exif: Record<string, string> | null;
  // PDF-specific
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  // Audio/Video
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// --- Point-cloud processing jobs (primary entity) --------------------------

export type MeshingMethod = "poisson" | "ball_pivoting";
export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobArtifact {
  name: string; // "processed_cloud" | "mesh" | "preview"
  kind: string; // "cloud" | "mesh" | "image"
  key: string;
  size_bytes: number;
  size_human: string;
}

export interface JobMetrics {
  source_points: number;
  downsampled_points: number;
  mesh_vertices: number;
  mesh_triangles: number;
  registered: boolean;
  source_bytes: number;
  artifact_bytes: number;
  write_amplification: number;
  duration_seconds: number;
}

export interface Job {
  id: string;
  name: string;
  source_keys: string[];
  meshing_method: MeshingMethod;
  register_scans: boolean;
  voxel_size: number;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  error: string | null;
  metrics: JobMetrics;
  artifacts: JobArtifact[];
  preview_key: string | null;
}

/** POST /jobs body. */
export interface JobCreate {
  name: string;
  source_keys: string[];
  meshing_method: MeshingMethod;
  register_scans: boolean;
  voxel_size: number;
}

/** PATCH /jobs/{id} body — every field optional. */
export type JobUpdate = Partial<JobCreate>;

export interface JobStats {
  total_jobs: number;
  queued: number;
  running: number;
  done: number;
  failed: number;
  source_bytes: number;
  source_bytes_human: string;
  artifact_bytes: number;
  artifact_bytes_human: string;
  artifact_count: number;
  write_amplification: number;
}
