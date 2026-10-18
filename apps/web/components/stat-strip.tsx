import { readJson } from "@/lib/files";

export default async function StatStrip() {
  const controls = await readJson("evidence/controls.json");
  const benchControls = await readJson("evidence/benchmark/controls.json");

  // Cell 1: synthetic corpus
  const synBaseline =
    controls?.mechanism_split?.arms?.baseline?.superseded_in_context ?? "not recorded";
  const synGate =
    controls?.mechanism_split?.arms?.full?.superseded_in_context ?? "not recorded";

  // Cell 2: real benchmark (19 conflict questions)
  const benchBaseline =
    benchControls?.all_19?.baseline?.superseded_in_context_total ?? "not recorded";
  const benchGate =
    benchControls?.all_19?.gate?.superseded_in_context_total ?? "not recorded";

  // Cell 3: recall on real benchmark
  const expRecall = benchControls?.all_19?.expected_recall;
  const recBaseline =
    expRecall?.baseline_recall !== undefined
      ? `${Math.round(expRecall.baseline_recall * 100)}%`
      : "not recorded";
  const recGate =
    expRecall?.gate_recall !== undefined
      ? `${Math.round(expRecall.gate_recall * 100)}%`
      : "not recorded";
  const recTitle =
    expRecall?.baseline_found !== undefined &&
    expRecall?.expected_docs_total !== undefined &&
    expRecall?.gate_found !== undefined
      ? `${expRecall.baseline_found}/${expRecall.expected_docs_total} → ${expRecall.gate_found}/${expRecall.expected_docs_total}`
      : undefined;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 lg:divide-x divide-lp-line rounded-xl border border-lp-line bg-lp-panel">
        {/* Cell 1: Synthetic documents in context */}
        <div className="flex flex-col justify-between p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="label text-[10px] text-lp-mute uppercase">synthetic</span>
          </div>
          <div>
            <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight">
              <span className="value-retired line-through text-lp-retired">
                {synBaseline}
              </span>{" "}
              <span className="text-lp-mute font-normal text-xl mx-1">&rarr;</span>{" "}
              <span className="value-current text-lp-ink">
                {synGate}
              </span>
            </div>
            <p className="mt-2 text-xs text-lp-mute font-mono">
              Retired docs in context
            </p>
          </div>
        </div>

        {/* Cell 2: Benchmark documents in context */}
        <div className="flex flex-col justify-between p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="label text-[10px] text-lp-mute uppercase">real benchmark</span>
            <span className="font-mono text-[10px] text-lp-mute">19 conflicts</span>
          </div>
          <div>
            <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight">
              <span className="value-retired line-through text-lp-retired">
                {benchBaseline}
              </span>{" "}
              <span className="text-lp-mute font-normal text-xl mx-1">&rarr;</span>{" "}
              <span className="value-current text-lp-ink">
                {benchGate}
              </span>
            </div>
            <p className="mt-2 text-xs text-lp-mute font-mono">
              Retired docs in context
            </p>
          </div>
        </div>

        {/* Cell 3: Expected recall (the cost) */}
        <div className="flex flex-col justify-between p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="label text-[10px] text-lp-mute uppercase">real benchmark</span>
            <span className="label text-[10px] text-lp-retired">the cost</span>
          </div>
          <div>
            <div
              className="font-mono text-2xl sm:text-3xl font-bold tracking-tight cursor-help"
              title={recTitle}
            >
              <span className="text-lp-mute font-normal">
                {recBaseline}
              </span>{" "}
              <span className="text-lp-mute font-normal text-xl mx-1">&rarr;</span>{" "}
              <span className="text-lp-ink">
                {recGate}
              </span>
            </div>
            <p className="mt-2 text-xs text-lp-mute font-mono" title={recTitle}>
              Recall: baseline to gate
            </p>
          </div>
        </div>

        {/* Cell 4: Graph unreachable: HTTP 503 */}
        <div className="flex flex-col justify-between p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="label text-[10px] text-lp-mute uppercase">real benchmark</span>
          </div>
          <div>
            <div className="font-mono text-xl sm:text-2xl font-bold tracking-tight text-lp-ink">
              HTTP 503
            </div>
            <p className="mt-2 text-xs text-lp-mute font-mono">
              Graph unreachable
            </p>
          </div>
          <div className="pt-1">
            <a
              href="https://github.com/DiverseXL/canister#engineering-decisions"
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-mono text-lp-mute hover:text-lp-ink underline underline-offset-2 inline-flex items-center gap-1"
            >
              Fail-closed test &rarr;
            </a>
          </div>
        </div>
      </div>

      <p className="text-[12px] font-mono text-lp-mute leading-relaxed">
        Deterministic; no model in the loop. The gate cannot recover documents that retrieval never returned.
      </p>
    </div>
  );
}
