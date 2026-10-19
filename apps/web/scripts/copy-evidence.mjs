#!/usr/bin/env node
/**
 * Prebuild: copy ../../evidence into apps/web/.evidence so that the
 * landing page and /results work when only apps/web is deployed (e.g.
 * Render, Vercel) without the rest of the monorepo mounted.
 *
 * If the source does not exist (clean CI before evidence is generated)
 * the script exits 0 so it never breaks the build.
 */
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const src = path.resolve(webRoot, "..", "..", "evidence");
const dst = path.resolve(webRoot, ".evidence");

if (!existsSync(src)) {
  console.log(`[copy-evidence] source ${src} not found — skipping.`);
  process.exit(0);
}

mkdirSync(dst, { recursive: true });
cpSync(src, dst, { recursive: true });
console.log(`[copy-evidence] copied ${src} → ${dst}`);