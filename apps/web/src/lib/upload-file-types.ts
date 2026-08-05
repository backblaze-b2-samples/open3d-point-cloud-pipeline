/**
 * Client-side allow-list for the point-cloud dropzone, mirroring the backend's
 * `POINT_CLOUD_EXTENSIONS` in `services/api/app/service/upload.py`. The server
 * re-validates every upload (extension + magic bytes) — this only gives instant
 * feedback and filters the OS file picker. Keep the two in sync.
 *
 * Point-cloud formats have no standard MIME type; browsers send
 * `application/octet-stream`, so react-dropzone matches these by EXTENSION.
 */
export const POINT_CLOUD_EXTENSIONS = ["ply", "pcd", "las", "laz"] as const;

export const ACCEPTED_FILE_TYPES: Record<string, string[]> = {
  "application/octet-stream": POINT_CLOUD_EXTENSIONS.map((ext) => `.${ext}`),
};
