import { describe, expect, it } from "vitest";

import { ACCEPTED_FILE_TYPES, POINT_CLOUD_EXTENSIONS } from "./upload-file-types";

// Mirror of the backend `POINT_CLOUD_EXTENSIONS` in
// services/api/app/service/upload.py. The dropzone allow-list must stay in
// lockstep with what the server accepts; this fails loudly if either drifts.
const BACKEND_POINT_CLOUD_EXTENSIONS = ["ply", "pcd", "las", "laz"];

describe("point-cloud upload types", () => {
  it("covers exactly the backend point-cloud extension set", () => {
    expect(new Set(POINT_CLOUD_EXTENSIONS)).toEqual(
      new Set(BACKEND_POINT_CLOUD_EXTENSIONS)
    );
  });

  it("maps octet-stream to the dot-prefixed point-cloud extensions", () => {
    const exts = ACCEPTED_FILE_TYPES["application/octet-stream"];
    expect(exts).toBeDefined();
    expect(new Set(exts)).toEqual(
      new Set(BACKEND_POINT_CLOUD_EXTENSIONS.map((e) => `.${e}`))
    );
    for (const ext of exts) {
      expect(ext.startsWith(".")).toBe(true);
    }
  });
});
