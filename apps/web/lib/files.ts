import { promises as fs } from "node:fs";
import path from "node:path";

const ROOT =
  process.env.CANISTER_ROOT ?? path.resolve(process.cwd(), "..", "..");

/** Read a JSON result file from the repo root. Returns null when absent (not_run). */
export async function readJson(rel: string): Promise<any | null> {
  try {
    const text = await fs.readFile(path.join(ROOT, rel), "utf8");
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function repoRoot(): string {
  return ROOT;
}
