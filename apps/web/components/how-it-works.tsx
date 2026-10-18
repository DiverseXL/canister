import Link from "next/link";
import { readJson } from "@/lib/files";
import GateToggle, { RankedItem } from "@/components/gate-toggle";

export default async function HowItWorks() {
  const data = await readJson("evidence/gate_example.json");

  // Step 01 data
  const question = data?.query ?? "not recorded";
  const poolSize = data?.pool_size != null ? data.pool_size : "not recorded";
  const inputRanking: RankedItem[] = data?.input_ranking ?? [];
  const before10 = inputRanking.slice(0, 10);

  // Step 02 data
  const claimKeys: string[] = data?.claim_keys ?? [];
  const primaryClaimKey = claimKeys[0] ?? "not recorded";
  const decisions = data?.decisions ?? {};
  const primaryDecision = decisions[primaryClaimKey] ?? null;
  const decisionVal = primaryDecision?.decision ?? "not recorded";
  const selectedValue = primaryDecision?.selected_value ?? "not recorded";
  const priorityVal =
    primaryDecision?.priority != null ? primaryDecision.priority : "not recorded";
  const reasonVal = primaryDecision?.reason ?? "not recorded";

  // Label counts from input_ranking
  const labelCounts = {
    superseded: inputRanking.filter((e) => e.label === "superseded").length,
    current: inputRanking.filter((e) => e.label === "current").length,
    historical: inputRanking.filter((e) => e.label === "historical").length,
    contested: inputRanking.filter((e) => e.label === "contested").length,
    not_in_claim_graph: inputRanking.filter(
      (e) => e.label === "not_in_claim_graph"
    ).length,
  };

  const cypherQueries: Record<string, string> = data?.cypher_queries ?? {};

  // Step 03 data
  const finalContext: RankedItem[] = data?.final_context ?? [];
  const after10 = finalContext.slice(0, 10);
  const cutCount =
    data?.cut_set != null
      ? data.cut_set.filter((e: any) => e.reason === "superseded").length
      : "not recorded";
  const beforeTopIds = new Set(before10.map((e) => e.doc_id));
  const backfillCount = after10.filter((e) => !beforeTopIds.has(e.doc_id)).length;
  const pinnedIds: string[] = data?.pinned ?? [];
  const pinnedCount = data?.pinned != null ? pinnedIds.length : "not recorded";
  const finalSize = data?.final_size != null ? data.final_size : "not recorded";

  // Step 04 data
  const recordKeys = data ? Object.keys(data) : [];
  const sha256: string = data?.sha256 ?? "";
  const shortSha256 = sha256 ? `${sha256.slice(0, 12)}…` : "not recorded";
  const receiptId = data?.receipt_id ?? "not recorded";

  return (
    <div>
      <div className="mb-12 space-y-4">
        <p className="label text-lp-mute">02 &mdash; How it works</p>
        <h2 className="display text-[clamp(1.75rem,4vw,3rem)] leading-[1.1] tracking-[-0.01em] text-lp-ink">
          How it works
        </h2>
        <p className="max-w-[64ch] text-[15px] leading-[1.8] text-lp-mute">
          Four steps between your retriever and your model. The graph never
          writes the answer; it decides what the model is allowed to read.
        </p>
      </div>

      <div className="space-y-8">
        {/* Step 01: Retrieve */}
        <div className="rounded-2xl border border-lp-line bg-lp-panel p-6 md:p-8">
          <div className="grid gap-6 md:grid-cols-[200px_minmax(0,1fr)] md:gap-12">
            <div>
              <p className="font-mono text-xs text-lp-mute uppercase tracking-[0.08em] mb-1">
                01
              </p>
              <h3 className="display text-2xl text-lp-ink">Retrieve</h3>
            </div>
            <div className="space-y-4 min-w-0">
              <p className="text-[15px] leading-[1.75] text-lp-ink">
                BM25 over a SQLite FTS5 index proposes candidates by relevance
                alone.
              </p>
              <p className="font-mono text-xs text-lp-mute">
                In the code:{" "}
                <code className="text-lp-ink">
                  the FTS store's bm25 method in packages/retrieval
                </code>
              </p>

              {/* Real data block */}
              <div className="mt-4 rounded-xl border border-lp-line bg-lp-bg p-4 space-y-3 font-mono text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-lp-line pb-2">
                  <span className="text-lp-mute">Question:</span>
                  <span className="text-lp-ink text-right">{question}</span>
                </div>
                <div className="flex items-center justify-between gap-2 border-b border-lp-line pb-2">
                  <span className="text-lp-mute">Candidate pool size:</span>
                  <span className="text-lp-ink">{poolSize}</span>
                </div>
                <div>
                  <span className="text-lp-mute block mb-2">
                    First 10 candidates (input_ranking):
                  </span>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="border-b border-lp-line text-lp-mute">
                          <th className="py-1 pr-3">Rank</th>
                          <th className="py-1 pr-3">Doc ID</th>
                          <th className="py-1 pr-3">BM25 Score</th>
                          <th className="py-1">Initial Label</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-lp-line/50">
                        {before10.length > 0 ? (
                          before10.map((entry) => (
                            <tr key={entry.doc_id}>
                              <td className="py-1 pr-3 text-lp-mute">
                                #{entry.rank}
                              </td>
                              <td className="py-1 pr-3 text-lp-ink font-medium">
                                {entry.doc_id}
                              </td>
                              <td className="py-1 pr-3 text-lp-mute">
                                {entry.bm25_score != null
                                  ? entry.bm25_score.toFixed(6)
                                  : "not recorded"}
                              </td>
                              <td className="py-1 text-lp-mute">
                                {entry.label ?? "not recorded"}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={4} className="py-2 text-lp-mute">
                              not recorded
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Step 02: Resolve */}
        <div className="rounded-2xl border border-lp-line bg-lp-panel p-6 md:p-8">
          <div className="grid gap-6 md:grid-cols-[200px_minmax(0,1fr)] md:gap-12">
            <div>
              <p className="font-mono text-xs text-lp-mute uppercase tracking-[0.08em] mb-1">
                02
              </p>
              <h3 className="display text-2xl text-lp-ink">Resolve</h3>
            </div>
            <div className="space-y-4 min-w-0">
              <p className="text-[15px] leading-[1.75] text-lp-ink">
                Each candidate is mapped to its claim and labelled from the graph.
                Priority order: explicit supersession, reliable temporal ordering,
                corroboration, no signal (CONTESTED).
              </p>
              <p className="font-mono text-xs text-lp-mute">
                In the code:{" "}
                <code className="text-lp-ink">
                  canonize.resolve and the grounding provider that reads the claim state
                </code>
              </p>

              {/* Real data block */}
              <div className="mt-4 rounded-xl border border-lp-line bg-lp-bg p-4 space-y-3 font-mono text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 border-b border-lp-line pb-3">
                  <div>
                    <span className="text-lp-mute block">Claim Key:</span>
                    <span className="text-lp-ink break-all">{primaryClaimKey}</span>
                  </div>
                  <div>
                    <span className="text-lp-mute block">Decision:</span>
                    <span className="text-lp-current font-bold">{decisionVal}</span>
                  </div>
                  <div>
                    <span className="text-lp-mute block">Selected Value:</span>
                    <span className="text-lp-ink">{selectedValue}</span>
                  </div>
                  <div>
                    <span className="text-lp-mute block">Priority & Reason:</span>
                    <span className="text-lp-ink">
                      Priority {priorityVal} ({reasonVal})
                    </span>
                  </div>
                </div>

                <div className="border-b border-lp-line pb-3">
                  <span className="text-lp-mute block mb-2">
                    Document counts per label (computed from response):
                  </span>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="rounded bg-lp-panel border border-lp-line px-2 py-1 text-lp-retired">
                      superseded: {labelCounts.superseded}
                    </span>
                    <span className="rounded bg-lp-panel border border-lp-line px-2 py-1 text-lp-current">
                      current: {labelCounts.current}
                    </span>
                    <span className="rounded bg-lp-panel border border-lp-line px-2 py-1 text-lp-mute">
                      historical: {labelCounts.historical}
                    </span>
                    <span className="rounded bg-lp-panel border border-lp-line px-2 py-1 text-lp-mute">
                      contested: {labelCounts.contested}
                    </span>
                    <span className="rounded bg-lp-panel border border-lp-line px-2 py-1 text-lp-mute">
                      not_in_claim_graph: {labelCounts.not_in_claim_graph}
                    </span>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-lp-mute">Cypher queries executed:</span>
                    <a
                      href="https://github.com/DiverseXL/canister#cypher-the-product-depends-on"
                      target="_blank"
                      rel="noreferrer"
                      className="text-lp-ink underline decoration-lp-mute hover:decoration-lp-ink"
                    >
                      Cypher the product depends on &rarr;
                    </a>
                  </div>
                  <div className="space-y-1">
                    {Object.keys(cypherQueries).length > 0 ? (
                      Object.entries(cypherQueries).map(([name, id]) => (
                        <div
                          key={name}
                          className="flex items-center justify-between text-xs"
                        >
                          <span className="text-lp-ink">{name}</span>
                          <span className="text-lp-mute">{id}</span>
                        </div>
                      ))
                    ) : (
                      <span className="text-lp-mute">not recorded</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Step 03: Rebuild */}
        <div className="rounded-2xl border border-lp-line bg-lp-panel p-6 md:p-8">
          <div className="grid gap-6 md:grid-cols-[200px_minmax(0,1fr)] md:gap-12">
            <div>
              <p className="font-mono text-xs text-lp-mute uppercase tracking-[0.08em] mb-1">
                03
              </p>
              <h3 className="display text-2xl text-lp-ink">Rebuild</h3>
            </div>
            <div className="space-y-4 min-w-0">
              <p className="text-[15px] leading-[1.75] text-lp-ink">
                Retired documents are cut, the next candidates from the same
                ranking take their places, and current evidence the retriever
                missed can be pinned; the context is always exactly ten documents.
              </p>
              <p className="font-mono text-xs text-lp-mute">
                In the code:{" "}
                <code className="text-lp-ink">ground and _select_temporal</code>
              </p>

              {/* Counters */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-center">
                <div className="rounded-lg border border-lp-line bg-lp-bg p-3">
                  <span className="block text-xl font-bold text-lp-retired">
                    {cutCount}
                  </span>
                  <span className="text-[11px] text-lp-mute uppercase">Cut</span>
                </div>
                <div className="rounded-lg border border-lp-line bg-lp-bg p-3">
                  <span className="block text-xl font-bold text-lp-current">
                    {backfillCount}
                  </span>
                  <span className="text-[11px] text-lp-mute uppercase">
                    Backfilled
                  </span>
                </div>
                <div className="rounded-lg border border-lp-line bg-lp-bg p-3">
                  <span className="block text-xl font-bold text-lp-ink">
                    {pinnedCount}
                  </span>
                  <span className="text-[11px] text-lp-mute uppercase">
                    Pinned
                  </span>
                </div>
                <div className="rounded-lg border border-lp-line bg-lp-bg p-3">
                  <span className="block text-xl font-bold text-lp-ink">
                    {finalSize}
                  </span>
                  <span className="text-[11px] text-lp-mute uppercase">
                    Final size
                  </span>
                </div>
              </div>

              <p className="text-xs text-lp-mute italic">
                Pins can only come from the candidate pool (the top 40), so the
                gate cannot recover a document retrieval never returned.
              </p>

              {/* Section C: Interactive Gate Toggle */}
              <GateToggle
                beforeItems={before10}
                afterItems={after10}
                pinnedIds={pinnedIds}
              />
            </div>
          </div>
        </div>

        {/* Step 04: Record */}
        <div className="rounded-2xl border border-lp-line bg-lp-panel p-6 md:p-8">
          <div className="grid gap-6 md:grid-cols-[200px_minmax(0,1fr)] md:gap-12">
            <div>
              <p className="font-mono text-xs text-lp-mute uppercase tracking-[0.08em] mb-1">
                04
              </p>
              <h3 className="display text-2xl text-lp-ink">Record</h3>
            </div>
            <div className="space-y-4 min-w-0">
              <p className="text-[15px] leading-[1.75] text-lp-ink">
                Every decision returns a record anyone can replay.
              </p>
              <p className="font-mono text-xs text-lp-mute">
                In the code:{" "}
                <code className="text-lp-ink">
                  the grounding record and GET /grounding/&#123;id&#125;
                </code>
              </p>

              {/* Real data block */}
              <div className="mt-4 rounded-xl border border-lp-line bg-lp-bg p-4 space-y-3 font-mono text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-lp-line pb-2">
                  <span className="text-lp-mute">Receipt ID:</span>
                  <span className="text-lp-ink">{receiptId}</span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-lp-line pb-2">
                  <span className="text-lp-mute">Context SHA-256:</span>
                  <span
                    title={sha256 || undefined}
                    className="text-lp-ink underline decoration-dotted decoration-lp-mute cursor-help"
                  >
                    {shortSha256}
                  </span>
                </div>
                <div>
                  <span className="text-lp-mute block mb-2">
                    Grounding record keys:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {recordKeys.length > 0 ? (
                      recordKeys.map((key) => (
                        <span
                          key={key}
                          className="rounded bg-lp-panel border border-lp-line px-2 py-0.5 text-lp-mute"
                        >
                          {key}
                        </span>
                      ))
                    ) : (
                      <span className="text-lp-mute">not recorded</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
