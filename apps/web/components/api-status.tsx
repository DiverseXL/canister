"use client";

import { isLocalApi } from "@/lib/api";

/**
 * Short mono banner for pages that call the API. Rendered only when the API
 * base is not localhost, i.e. when the console talks to the hosted demo.
 */
export function ApiBanner() {
  if (isLocalApi()) return null;
  return (
    <div className="mb-6 rounded border border-edge bg-panel px-4 py-3 font-mono text-xs leading-relaxed text-slate-400">
      Live demo: synthetic corpus on free-tier hosting. The first request can
      take about a minute while the API wakes up.
    </div>
  );
}

/**
 * API error card: a friendly line first, the real error text beneath it in
 * mono, so a cold start never breaks the page.
 */
export function ApiError({ error }: { error: string }) {
  return (
    <div className="card space-y-2 border-retired">
      <p className="text-sm text-slate-300">
        The demo backend is waking up or the free database has stopped; retry in
        a minute.
      </p>
      <pre className="whitespace-pre-wrap break-all font-mono text-xs text-retired">
        {error}
      </pre>
    </div>
  );
}
