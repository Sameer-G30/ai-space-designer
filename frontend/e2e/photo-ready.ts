// Decide whether the Playwright photo step can run. This file does not download weights or images.

// Existence checks for local files.
import { existsSync, readFileSync } from "node:fs";

// Paths stay inside this repo.
import path from "node:path";

// `npm run test:e2e` runs with frontend/ as the working directory. The repo root is its parent.
export const repoRoot = path.resolve(process.cwd(), "..");

// Photo used in the Phase 7b worker example. It is a SUN RGB-D test-split JPEG already on disk.
const preferredRelative = "datasets/processed/sun_rgbd/images/test/sun_00030.jpg";

// How many test-split photos to offer when the first has no floor.
const photoLimit = 3;

// One local file the photo worker needs, and the words used when it is absent.
type RequiredFile = {
  // Path relative to the repository root.
  relative: string;
  // Short reason. The test prints this and continues without the photo.
  label: string;
};

// Files that must exist before a photo estimate is attempted. Hugging Face caches are checked separately.
const requiredFiles: RequiredFile[] = [
  // Child process that holds CUDA torch. The API process does not load these models.
  { relative: ".venv-train/bin/python", label: "perception worker .venv-train/bin/python" },
  // Phase 7a detector. The photo step must not download or retrain a replacement.
  { relative: "models/detector/finetune/weights/best.pt", label: "detector weights models/detector/finetune/weights/best.pt" },
  // Phase 7a room classifier.
  { relative: "models/room_classifier.pt", label: "room classifier weights models/room_classifier.pt" },
  // YuNet face model. The pipeline stops when this file is missing.
  { relative: "models/pretrained/face_detection_yunet_2023mar.onnx", label: "YuNet face model models/pretrained/face_detection_yunet_2023mar.onnx" },
];

// Hugging Face hub folder, honouring the same environment overrides as the diffusion cache lookup.
function hubDir(): string {
  // Explicit hub cache.
  const explicit = process.env.HF_HUB_CACHE || process.env.HUGGINGFACE_HUB_CACHE;
  // Use it when set.
  if (explicit) {
    // Caller-selected cache.
    return explicit;
  }
  // HF_HOME/hub is the other common layout.
  if (process.env.HF_HOME) {
    // Standard subfolder.
    return path.join(process.env.HF_HOME, "hub");
  }
  // Default cache on this machine.
  const home = process.env.HOME ?? "";
  // The usual Linux location.
  return path.join(home, ".cache", "huggingface", "hub");
}

// True when a hub repo has a local snapshot pointer. This does not download the repo.
function hubRefPresent(repoFolder: string): boolean {
  // refs/main is written when a snapshot has been fetched.
  return existsSync(path.join(hubDir(), repoFolder, "refs", "main"));
}

// Why the photo step cannot run, or null when the local weights are present.
export function photoSkipReason(): string | null {
  // Labels of anything that is not on disk.
  const missing: string[] = [];
  // Each required file.
  for (const item of requiredFiles) {
    // Absolute path under the repo.
    const absolute = path.join(repoRoot, item.relative);
    // A missing file is a skip, not a download.
    if (!existsSync(absolute)) {
      // Keep the label for the test report.
      missing.push(item.label);
    }
  }
  // SAM2.1 Hiera-Tiny. The worker loads it with local files only.
  if (!hubRefPresent("models--facebook--sam2.1-hiera-tiny")) {
    // Name the checkpoint. Nothing is fetched here.
    missing.push("SAM2 checkpoint facebook/sam2.1-hiera-tiny");
  }
  // Depth Anything V2 metric indoor small.
  if (!hubRefPresent("models--depth-anything--Depth-Anything-V2-Metric-Indoor-Small-hf")) {
    // Name the checkpoint. Nothing is fetched here.
    missing.push("depth checkpoint depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf");
  }
  // All present.
  if (missing.length === 0) {
    // The photo step may run.
    return null;
  }
  // One sentence the test can show. The rest of the flow still runs.
  return `photo skipped: ${missing.join("; ")}`;
}

// Absolute paths of SUN RGB-D test-split JPEGs already on disk, preferred image first.
export function sunTestPhotos(): string[] {
  // Processed export. Raw zip members are not read from here.
  const folder = path.join(repoRoot, "datasets", "processed", "sun_rgbd");
  // Collected paths. Duplicates are dropped.
  const found: string[] = [];
  // The documented example, then the test list.
  const relatives = [preferredRelative.replace("datasets/processed/sun_rgbd/", "")];
  // YOLO list of labelled test images. Paths are relative to the export folder.
  const listPath = path.join(folder, "test.txt");
  // The list is optional. A missing export skips the photo later.
  if (existsSync(listPath)) {
    // One relative path per line.
    const lines = readFileSync(listPath, "utf8").split("\n");
    // Keep non-empty lines.
    for (const line of lines) {
      // Trim a trailing CR.
      const relative = line.trim();
      // Skip blanks.
      if (relative !== "") {
        // Remember it.
        relatives.push(relative);
      }
    }
  }
  // Resolve until the cap.
  for (const relative of relatives) {
    // Absolute JPEG path.
    const absolute = path.join(folder, relative);
    // Only files that are actually on disk.
    if (existsSync(absolute) && !found.includes(absolute)) {
      // Keep it.
      found.push(absolute);
    }
    // Three candidates are enough. The test does not walk the whole split.
    if (found.length >= photoLimit) {
      // Stop.
      break;
    }
  }
  // Possibly empty.
  return found;
}

// Path relative to the repository root, for the report.
export function relativeToRepo(absolute: string): string {
  // POSIX separators so the report matches the docs.
  return path.relative(repoRoot, absolute).split(path.sep).join("/");
}
