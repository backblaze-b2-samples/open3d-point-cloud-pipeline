// Finds a usable Python interpreter for scripts/doctor.mjs and scripts/setup.mjs.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { parseSemver } from "./semver.mjs";

// Floor: the API and its native deps (Open3D 0.19) need CPython >= 3.11.
export const REQUIRED_PYTHON_MINOR = 11;

// Ceiling: Open3D 0.19 publishes wheels only up to CPython 3.12. A newer
// interpreter (3.13/3.14 — what a bare `python3` often is on a dev box) has NO
// open3d wheel, so `pip install` would fail with a source build. Refuse those
// so setup/doctor pick a version that can actually install the API deps.
const MAX_PYTHON_MINOR = 12;

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

// The version the API is pinned to (services/api/.python-version). We prefer an
// interpreter that matches this exactly before falling back to anything else in
// the supported [REQUIRED..MAX] window.
function pinnedMinor() {
  try {
    const raw = readFileSync(
      resolve(REPO_ROOT, "services/api/.python-version"),
      "utf8",
    ).trim();
    const version = parseSemver(raw);
    return version ? version.minor : null;
  } catch {
    return null;
  }
}

// uv-managed interpreters are not on PATH by default, but `uv python find`
// prints the absolute path to one. This lets a dev box whose bare `python3` is
// too new still resolve the pinned 3.12 that `uv python install 3.12` provided.
function uvManagedPython(minor) {
  if (minor === null) return null;
  const result = spawnSync("uv", ["python", "find", `3.${minor}`], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error || result.status !== 0) return null;
  const path = (result.stdout ?? "").trim();
  return path || null;
}

/**
 * @returns {{bin: string, text: string, version: object}|null} null when the
 * binary is absent, exits non-zero, or prints no recognizable version. A broken
 * shim (the macOS `xcode-select` stub, `pyenv` with no version set) writes noise
 * to stderr and exits non-zero; treating that noise as a version made the caller
 * report "<noise> is too old" instead of "Python is not on PATH".
 */
function readVersion(bin) {
  const result = spawnSync(bin, ["--version"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });

  if (result.error || result.status !== 0) return null;

  // Python 2 prints --version to stderr, Python 3 to stdout.
  const text = `${result.stdout ?? ""} ${result.stderr ?? ""}`.trim();
  const version = text ? parseSemver(text) : null;
  if (!version) return null;

  return { bin, text, version };
}

function inSupportedWindow(version) {
  return (
    version.major === 3 &&
    version.minor >= REQUIRED_PYTHON_MINOR &&
    version.minor <= MAX_PYTHON_MINOR
  );
}

export function findPython() {
  const pinned = pinnedMinor();

  // Order matters: the pinned versioned name and the uv-managed pinned
  // interpreter come first so a box whose bare `python3` is too new still
  // resolves the version that can install the API deps. Then the versioned
  // names for the supported window, then the generic shims.
  const candidates = [
    pinned !== null ? `python3.${pinned}` : null,
    uvManagedPython(pinned),
    "python3.12",
    "python3.11",
    "python3",
    "python",
  ].filter(Boolean);

  const found = [];
  const seenBins = new Set();
  for (const bin of candidates) {
    if (seenBins.has(bin)) continue;
    seenBins.add(bin);
    const candidate = readVersion(bin);
    if (!candidate) continue;
    found.push(candidate);
  }

  // 1) Exact match on the pinned version wins.
  if (pinned !== null) {
    const exact = found.find(
      (c) => c.version.major === 3 && c.version.minor === pinned,
    );
    if (exact) return { python: exact, found };
  }

  // 2) Otherwise the first interpreter inside the supported [REQUIRED..MAX]
  //    window — this excludes an interpreter that is too new to have wheels.
  const compatible = found.find((c) => inSupportedWindow(c.version));
  if (compatible) return { python: compatible, found };

  return { python: null, found };
}
