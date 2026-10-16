"use client";

import { useState } from "react";

import { apiPost, type Receipt } from "@/lib/api";

function RankingRow({
  rank,
  docId,
  label,
  reason,
}: {
  rank: number;
  docId: string;
  label: string;
  reason?: string;
}) {
  return (
    <li className="flex items-center gap-2 font-mono text-xs">
      <span className="w-6 text-right text-slate-500">{rank}</span>
      <span className={`label-${label}`}>{docId}</span>
      <span className="text-slate-500">{label}</span>
      {reason && <span className="text-slate-600">· {reason}</span>}
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
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold text-white">Temporal Gate</h1>
        <p className="mt-1 text-sm text-slate-400">
          The same BM25 ranking, shown twice. The graph decides which ranked
          evidence may still ground a present-tense answer.
        </p>
      </section>

      <section className="card flex flex-col gap-3 sm:flex-row">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What is the current integration owner for Hooli?"
          className="flex-1 rounded border border-edge bg-ink px-3 py-2 font-mono text-sm outline-none focus:border-current"
        />
        <button
          onClick={run}
          disabled={loading || question.trim().length === 0}
          className="rounded bg-current px-4 py-2 text-sm font-semibold text-ink disabled:opacity-40"
        >
          {loading ? "Grounding…" : "Cut"}
        </button>
      </section>

      {error && <div className="card border-retired text-retired">{error}</div>}

      {receipt && (
        <>
          <section className="grid gap-4 md:grid-cols-2">
            <div className="card">
              <div className="text-xs uppercase tracking-wide text-slate-400">
                Baseline answer (BM25 only)
              </div>
              <div className="mt-1 font-mono text-lg text-retired">
                {baseline[0]?.doc_id ?? "—"}{" "}
                <span className="text-sm text-slate-500">
                  [{baseline[0]?.label ?? "—"}]
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                retired docs in context: {baselineLeak}
              </div>
            </div>
            <div className="card">
              <div className="text-xs uppercase tracking-wide text-slate-400">
                Temporal answer (graph-constrained)
              </div>
              <div className="mt-1 font-mono text-lg text-current">
                {decision?.selected_value ?? decision?.decision ?? "UNKNOWN"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                retired docs in context: {temporalLeak}
              </div>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="card">
              <h2 className="mb-2 font-semibold text-white">
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
            <div className="card">
              <h2 className="mb-2 font-semibold text-white">
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
            <div className="card">
              <h2 className="mb-2 font-semibold text-white">Cut from the ranking</h2>
              <ol className="space-y-1">
                {receipt.cut_set.map((entry) => (
                  <RankingRow
                    key={entry.doc_id}
                    rank={entry.rank}
                    docId={entry.doc_id}
                    label={entry.label}
                    reason={entry.reason}
                  />
                ))}
              </ol>
            </div>
            <div className="card">
              <h2 className="mb-2 font-semibold text-white">
                Graph path justifying the cut
              </h2>
              <ul className="space-y-2 font-mono text-xs">
                {Object.entries(receipt.decisions).map(([key, value]) => (
                  <li key={key}>
                    <div className="text-slate-400">{key}</div>
                    <div>
                      CanonEvent → {value.decision}
                      {value.selected_value ? ` = ${value.selected_value}` : ""} (
                      {value.reason}, priority {value.priority ?? "—"})
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-3 text-[11px] text-slate-500">
                queries: {Object.keys(receipt.cypher_queries).join(", ")}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
