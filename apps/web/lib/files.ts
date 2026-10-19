import { existsSync } from "node:fs";
import { promises as fs } from "node:fs";
import path from "node:path";

/**
 * Resolve the evidence directory.
 *
 * Priority:
 *   1. EVIDENCE_DIR env var (absolute or relative to cwd)
 *   2. apps/web/.evidence  (co-deployed copy populated by the prebuild script)
 *   3. Repo-root evidence/ (monorepo dev, two levels above apps/web)
 */
function resolveEvidenceDir(): string {
  if (process.env.EVIDENCE_DIR) {
    return path.resolve(process.cwd(), process.env.EVIDENCE_DIR);
  }
  const local = path.resolve(process.cwd(), ".evidence");
  if (existsSync(local)) {
    return local;
  }
  return path.resolve(process.cwd(), "..", "..", "evidence");
}

const EVIDENCE_DIR = resolveEvidenceDir();

/**
 * Legacy repo-root resolver kept for corpus/out paths that live outside
 * the evidence folder.  Can also be overridden via CANISTER_ROOT.
 */
const ROOT =
  process.env.CANISTER_ROOT ?? path.resolve(process.cwd(), "..", "..");

/**
 * Read a JSON result file.
 *
 * Paths starting with "evidence/" are resolved relative to EVIDENCE_DIR
 * (the local copy or the env-specified directory).  All other paths are
 * resolved relative to ROOT.  Returns null when the file is absent.
 */
export async function readJson(rel: string): Promise<any | null> {
  let target: string;
  if (rel.startsWith("evidence/")) {
    target = path.join(EVIDENCE_DIR, rel.slice("evidence/".length));
  } else {
    target = path.join(ROOT, rel);
  }
  try {
    const text = await fs.readFile(target, "utf8");
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function repoRoot(): string {
  return ROOT;
}