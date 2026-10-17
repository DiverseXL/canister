"use client";

import { useState } from "react";

import { apiPost, type Receipt } from "@/lib/api";

function ReceiptPanel({ title, receipt }: { title: string; receipt: Receipt }) {
  const decision =
    receipt.claim_keys.length === 1
      ? receipt.decisions[receipt.claim_keys[0]]
      : null;
  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold text-white">{title}</h2>
        <span className="font-mono text-xs text-slate-500">
          {receipt.mode_requested ?? receipt.mode}
        </span>
      </div>
      <div className="text-sm">
        <span className="text-slate-400">answer: </span>
        <span className="font-mono text-current">
          {decision?.selected_value ?? decision?.decision ?? "UNKNOWN"}
        </span>
        {decision && (
          <span className="ml-2 text-xs text-slate-500">({decision.reason})</span>
        )}
      </div>
      <ol className="space-y-1 font-mono text-xs">
        {receipt.final_context.map((entry) => (
          <li key={entry.doc_id + entry.rank}>
            <span className="text-slate-500">{entry.rank}</span>{" "}
            <span className={`label-${entry.label}`}>{entry.doc_id}</span>{" "}
            <span className="text-slate-500">{entry.label}</span>
          </li>
        ))}
      </ol>
      <div className="text-[11px] text-slate-500">
        sha256 {receipt.sha256.slice(0, 16)} · {receipt.final_size} docs
      </div>
    </div>
  );
}

export default function Ask() {
  const [question, setQuestion] = useState("");
  const [current, setCurrent] = useState<Receipt | null>(null);
  const [historical, setHistorical] = useState<Receipt | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const [now, then] = await Promise.all([
        apiPost("/ground", { question, mode: "current" }),
        apiPost("/ground", { question, mode: "historical" }),
      ]);
      setCurrent(now);
      setHistorical(then);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold text-white">Ask</h1>
        <p className="mt-1 text-sm text-slate-400">
          The same question in <span className="font-mono">current</span> and{" "}
          <span className="font-mono">historical</span> mode.
        </p>
      </section>

      <section className="card flex flex-col gap-3 sm:flex-row">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What is the current starter plan price for Acme Corp?"
          className="flex-1 rounded border border-edge bg-ink px-3 py-2 font-mono text-sm outline-none focus:border-current"
        />
        <button
          onClick={run}
          disabled={loading || question.trim().length === 0}
          className="rounded bg-current px-4 py-2 text-sm font-semibold text-ink disabled:opacity-40"
        >
          {loading ? "Grounding…" : "Ground"}
        </button>
      </section>

      {error && <div className="card border-retired text-retired">{error}</div>}

      {current && historical && (
        <section className="grid gap-4 md:grid-cols-2">
          <ReceiptPanel title="Current" receipt={current} />
          <ReceiptPanel title="Historical" receipt={historical} />
        </section>
      )}
    </div>
  );
}
