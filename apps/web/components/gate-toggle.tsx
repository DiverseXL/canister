"use client";

import { useState } from "react";

export type RankedItem = {
  rank: number;
  doc_id: string;
  label?: string;
  bm25_score?: number;
  reason?: string;
};

export type GateToggleProps = {
  beforeItems: RankedItem[];
  afterItems: RankedItem[];
  pinnedIds?: string[];
};

export default function GateToggle({
  beforeItems,
  afterItems,
  pinnedIds = [],
}: GateToggleProps) {
  const [isGated, setIsGated] = useState(false);

  // Identify documents that were backfilled (in afterItems but not in top 10 of beforeItems)
  const beforeTopDocIds = new Set(beforeItems.map((item) => item.doc_id));

  return (
    <div className="mt-6 rounded-xl border border-lp-line bg-lp-bg p-5 md:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="label text-xs text-lp-mute">Interactive view</span>
          <p className="text-sm text-lp-ink">
            Compare raw BM25 candidates with the post-gate context
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-lp-mute" aria-live="polite">
            State: {isGated ? "after (gate applied)" : "before (raw retrieval)"}
          </span>
          <button
            type="button"
            aria-pressed={isGated}
            onClick={() => setIsGated((prev) => !prev)}
            className="label cursor-pointer rounded-full border border-lp-ink px-4 py-2 text-lp-ink transition-colors duration-200 hover:bg-lp-ink hover:text-lp-bg focus-visible:outline-2 focus-visible:outline-lp-ink"
          >
            Run the gate
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* Left Column: Before (BM25 ranking) */}
        <div
          className={`rounded-lg border p-4 transition-all duration-300 ${
            !isGated
              ? "border-lp-ink/40 bg-lp-panel/60"
              : "border-lp-line bg-lp-panel/30 opacity-75"
          }`}
        >
          <div className="mb-3 flex items-center justify-between border-b border-lp-line pb-2">
            <span className="label text-xs text-lp-mute">
              Before &mdash; BM25 returned
            </span>
            <span className="font-mono text-xs text-lp-mute">10 items</span>
          </div>

          <ol className="space-y-2.5 p-0 m-0 list-none">
            {beforeItems.map((item) => {
              const isRetired =
                item.label === "superseded" || item.reason === "superseded";
              return (
                <li
                  key={`before-${item.doc_id}`}
                  className="flex items-center justify-between gap-3 text-sm font-mono"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-lp-mute text-xs w-6 shrink-0">
                      #{item.rank + 1}
                    </span>
                    <span
                      className={`truncate transition-all duration-300 ${
                        isRetired
                          ? "value-retired text-lp-retired line-through"
                          : "text-lp-ink"
                      }`}
                    >
                      {item.doc_id}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {item.bm25_score != null && (
                      <span className="text-xs text-lp-mute">
                        {item.bm25_score.toFixed(3)}
                      </span>
                    )}
                    {isRetired && (
                      <span className="label text-[10px] text-lp-retired border border-lp-retired/40 bg-lp-retired/10 px-1.5 py-0.5 rounded">
                        RETIRED
                      </span>
                    )}
                    {item.label === "current" && (
                      <span className="label text-[10px] text-lp-current border border-lp-current/40 bg-lp-current/10 px-1.5 py-0.5 rounded">
                        CURRENT
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>

        {/* Right Column: After (Post-gate context) */}
        <div
          className={`rounded-lg border p-4 transition-all duration-300 ${
            isGated
              ? "border-lp-current/60 bg-lp-panel/60 shadow-[0_0_20px_rgba(56,211,159,0.06)]"
              : "border-lp-line bg-lp-panel/30 opacity-70"
          }`}
        >
          <div className="mb-3 flex items-center justify-between border-b border-lp-line pb-2">
            <span className="label text-xs text-lp-mute">
              After &mdash; Post-gate context
            </span>
            <span className="font-mono text-xs text-lp-mute">10 items</span>
          </div>

          <ol className="space-y-2.5 p-0 m-0 list-none">
            {afterItems.map((item, idx) => {
              const isPinned = pinnedIds.includes(item.doc_id);
              const isBackfilled = !beforeTopDocIds.has(item.doc_id);
              return (
                <li
                  key={`after-${item.doc_id}`}
                  className="flex items-center justify-between gap-3 text-sm font-mono"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-lp-mute text-xs w-6 shrink-0">
                      #{idx + 1}
                    </span>
                    <span className="truncate text-lp-ink">{item.doc_id}</span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {item.bm25_score != null && (
                      <span className="text-xs text-lp-mute">
                        {item.bm25_score.toFixed(3)}
                      </span>
                    )}
                    {isPinned && (
                      <span className="label text-[10px] text-lp-ink border border-lp-ink/40 bg-lp-ink/10 px-1.5 py-0.5 rounded">
                        PIN
                      </span>
                    )}
                    {isBackfilled && (
                      <span className="label text-[10px] text-lp-current border border-lp-current/40 bg-lp-current/10 px-1.5 py-0.5 rounded">
                        BACKFILL
                      </span>
                    )}
                    {!isBackfilled && !isPinned && (
                      <span className="label text-[10px] text-lp-current/70 border border-lp-current/20 px-1.5 py-0.5 rounded">
                        KEPT
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      <p className="mt-4 border-t border-lp-line pt-3 text-xs text-lp-mute">
        Synthetic corpus, seeded. No model in the loop.
      </p>
    </div>
  );
}
