// Prebuild step: bundle the repo-root evidence/ folder into apps/web/.evidence
// so the console (especially /results) renders real numbers even when only
// apps/web is deployed (e.g. a Vercel root set to apps/web, where the repo
// root two levels up does not exist). Silently skips when the source is absent
// so a standalone apps/web checkout still builds.
import { cp, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.resolve(webDir, "..", "..", "evidence");
const target = path.join(webDir, ".evidence");

async function isDir(p) {
  try {
    return (await stat(p)).isDirectory();
  } catch {
    return false;
  }
}

if (!(await isDir(source))) {
  console.log(`copy-evidence: ${source} not found; skipping`);
  process.exit(0);
}

await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log(`copy-evidence: copied ${source} -> ${target}`);
