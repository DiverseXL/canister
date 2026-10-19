import { promises as fs } from "node:fs";
import path from "node:path";

const REPO_ROOT =
  process.env.CANISTER_ROOT ?? path.resolve(process.cwd(), "..", "..");

export function repoRoot(): string {
  return REPO_ROOT;
}

/**
 * Resolve the directory holding the evidence JSON files, in priority order:
 *   1. EVIDENCE_DIR environment variable (explicit override, e.g. on a host
 *      where only apps/web is deployed),
 *   2. apps/web/.evidence (copied there by scripts/copy-evidence.mjs at build
 *      time when the repo-root evidence/ folder is present),
 *   3. the repo-root evidence/ folder (normal in-repo development).
 * Returns null when none of the candidates exists.
 */
export async function evidenceDir(): Promise<string | null> {
  const fromEnv = process.env.EVIDENCE_DIR;
  if (fromEnv) return fromEnv;
  const local = path.join(process.cwd(), ".evidence");
  try {
    if ((await fs.stat(local)).isDirectory()) return local;
  } catch {
    /* not present */
  }
  const atRoot = path.join(REPO_ROOT, "evidence");
  try {
    if ((await fs.stat(atRoot)).isDirectory()) return atRoot;
  } catch {
    /* not present */
  }
  return null;
}

/** Read a JSON file from the evidence directory. Returns null when absent (not_run). */
export async function readEvidence(name: string): Promise<any | null> {
  const dir = await evidenceDir();
  if (!dir) return null;
  try {
    const text = await fs.readFile(path.join(dir, name), "utf8");
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Read a JSON file relative to the repo root. Returns null when absent (not_run). */
export async function readJson(rel: string): Promise<any | null> {
  try {
    const text = await fs.readFile(path.join(REPO_ROOT, rel), "utf8");
    return JSON.parse(text);
  } catch {
    return null;
  }
}
