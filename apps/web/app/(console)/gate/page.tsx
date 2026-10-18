"use client";

import { useState } from "react";

import PageHeader from "@/components/page-header";
import { apiPost, type Receipt } from "@/lib/api";

/** Retired documents are shown struck through and labelled RETIRED. */
function labelWord(label: string): string {
  return label === "superseded" ? "RETIRED" : label;
}

function RankingRow({
  rank,
  docId,
  label,
  reason,
  graphPath,
}: {
  rank: number;
  docId: string;
  label: string;
  reason?: string;
  graphPath?: [string, string][];
}) {
  return (
    <li>
      <div className="flex items-center gap-2 font-mono text-xs">
        <span className="w-6 text-right text-lp-mute">{rank}</span>
        <span
          className={label === "superseded" ? "value-retired" : "text-lp-ink"}
        >
          {docId}
        </span>
        <span className="text-lp-mute">{labelWord(label)}</span>
        {reason && <span className="text-lp-mute">· {reason}</span>}
      </div>
      {graphPath && graphPath.length > 0 && (
        <div className="mt-1 pl-8 font-mono text-[11px] leading-relaxed text-lp-mute">
          {graphPath.map(([nodeLabel, nodeId], index) => (
            <span key={`${nodeLabel}:${nodeId}`} className="whitespace-nowrap">
              {index > 0 && <span className="px-1">→</span>}
              <span className="rounded-sm border border-lp-line px-1.5 py-0.5 text-lp-ink">
                {nodeLabel}
              </span>
              <span> {nodeId.slice(0, 8)}…</span>
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

export default function Cut() {
  const [question, setQuestion] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setReceipt(await apiPost("/ground", { question, mode: "temporal" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const k = receipt?.final_size ?? 0;
  const baseline = receipt ? receipt.input_ranking.slice(0, k) : [];
  const baselineLeak = baseline.filter((entry) => entry.label === "superseded").length;
  const temporalLeak =
    receipt?.final_context.filter((entry) => entry.label === "superseded").length ?? 0;
  const decision =
    receipt && receipt.claim_keys.length === 1
      ? receipt.decisions[receipt.claim_keys[0]]
      : null;

  return (
    <div className="space-y-10">
      <PageHeader
        eyebrow="Gate"
        title="Temporal Gate"
        description={
          <>
            The same BM25 ranking, shown twice. The graph decides which ranked
            evidence may still ground a present-tense answer.
          </>
        }
      />

      <section className="flex flex-col gap-3 border border-lp-line bg-lp-panel p-5 sm:flex-row">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What is the current starter plan price for Acme Corp?"
          className="flex-1 border border-lp-line bg-lp-bg px-4 py-3 font-mono text-sm text-lp-ink placeholder:text-lp-mute"
        />
        <button
          onClick={run}
          disabled={loading || question.trim().length === 0}
          className="label rounded-full bg-lp-ink px-4 py-2 text-lp-bg disabled:opacity-40"
        >
          {loading ? "Grounding…" : "Cut"}
        </button>
      </section>

      {error && (
        <div className="border border-lp-retired bg-lp-panel px-4 py-3 font-mono text-sm text-lp-retired">
          {error}
        </div>
      )}

      {receipt && (
        <>
          <section className="grid gap-4 md:grid-cols-2">
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <div className="label text-lp-mute">Baseline answer (BM25 only)</div>
              <div
                className={`mt-2 font-mono text-lg ${
                  baseline[0]?.label === "superseded"
                    ? "value-retired"
                    : "text-lp-ink"
                }`}
              >
                {baseline[0]?.doc_id ?? "—"}{" "}
                <span className="text-sm text-lp-mute">
                  [{labelWord(baseline[0]?.label ?? "—")}]
                </span>
              </div>
              <div className="mt-1 font-mono text-xs text-lp-mute">
                retired docs in context: {baselineLeak}
              </div>
            </div>
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <div className="label text-lp-mute">
                Temporal answer (graph-constrained)
              </div>
              <div className="mt-2 font-mono text-lg text-lp-ink">
                {decision?.selected_value ?? decision?.decision ?? "UNKNOWN"}
              </div>
              <div className="mt-1 font-mono text-xs text-lp-mute">
                retired docs in context: {temporalLeak}
              </div>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <h2 className="mb-3 font-mono text-[13px] font-medium uppercase tracking-[0.12em] text-lp-ink">
                Baseline context (flat top-{k})
              </h2>
              <ol className="space-y-1">
                {baseline.map((entry) => (
                  <RankingRow
                    key={entry.doc_id}
                    rank={entry.rank}
                    docId={entry.doc_id}
                    label={entry.label}
                  />
                ))}
              </ol>
            </div>
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <h2 className="mb-3 font-mono text-[13px] font-medium uppercase tracking-[0.12em] text-lp-ink">
                Temporal context ({k} docs)
              </h2>
              <ol className="space-y-1">
                {receipt.final_context.map((entry) => (
                  <RankingRow
                    key={entry.doc_id}
                    rank={entry.rank}
                    docId={entry.doc_id}
                    label={entry.label}
                  />
                ))}
              </ol>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <h2 className="mb-3 font-mono text-[13px] font-medium uppercase tracking-[0.12em] text-lp-ink">
                Cut from the ranking
              </h2>
              <ol className="space-y-2">
                {receipt.cut_set.map((entry) => (
                  <RankingRow
                    key={entry.doc_id}
                    rank={entry.rank}
                    docId={entry.doc_id}
                    label={entry.label}
                    reason={entry.reason}
                    graphPath={entry.graph_path}
                  />
                ))}
              </ol>
            </div>
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <h2 className="mb-3 font-mono text-[13px] font-medium uppercase tracking-[0.12em] text-lp-ink">
                Graph path justifying the cut
              </h2>
              <ul className="space-y-2 font-mono text-xs">
                {Object.entries(receipt.decisions).map(([key, value]) => (
                  <li key={key}>
                    <div className="text-lp-mute">{key}</div>
                    <div className="text-lp-ink">
                      CanonEvent → {value.decision}
                      {value.selected_value ? ` = ${value.selected_value}` : ""} (
                      {value.reason}, priority {value.priority ?? "—"})
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-3 font-mono text-[11px] text-lp-mute">
                queries: {Object.keys(receipt.cypher_queries).join(", ")}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
