"use client";

import { useState } from "react";

import PageHeader from "@/components/page-header";
import { apiPost, type Receipt } from "@/lib/api";

/** Retired documents are shown struck through and labelled RETIRED. */
function labelWord(label: string): string {
  return label === "superseded" ? "RETIRED" : label;
}

function ReceiptPanel({ title, receipt }: { title: string; receipt: Receipt }) {
  const decision =
    receipt.claim_keys.length === 1
      ? receipt.decisions[receipt.claim_keys[0]]
      : null;
  return (
    <div className="space-y-4 border border-lp-line bg-lp-panel px-5 py-6">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-[13px] font-medium uppercase tracking-[0.12em] text-lp-ink">
          {title}
        </h2>
        <span className="label text-lp-mute">
          {receipt.mode_requested ?? receipt.mode}
        </span>
      </div>
      <div className="text-sm">
        <span className="text-lp-mute">answer: </span>
        <span className="font-mono text-lp-ink">
          {decision?.selected_value ?? decision?.decision ?? "UNKNOWN"}
        </span>
        {decision && (
          <span className="ml-2 font-mono text-xs text-lp-mute">
            ({decision.reason})
          </span>
        )}
      </div>
      <ol className="space-y-1 font-mono text-xs">
        {receipt.final_context.map((entry) => (
          <li key={entry.doc_id + entry.rank} className="flex gap-2">
            <span className="w-6 text-right text-lp-mute">{entry.rank}</span>
            <span
              className={
                entry.label === "superseded" ? "value-retired" : "text-lp-ink"
              }
            >
              {entry.doc_id}
            </span>
            <span className="text-lp-mute">{labelWord(entry.label)}</span>
          </li>
        ))}
      </ol>
      <div className="font-mono text-[11px] text-lp-mute">
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
  const [showCurrent, setShowCurrent] = useState(true);
  const [showHistorical, setShowHistorical] = useState(true);

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
    <div className="space-y-10">
      <PageHeader
        eyebrow="Ask"
        title="Ask"
        description={
          <>
            The same question in <span className="font-mono">current</span> and{" "}
            <span className="font-mono">historical</span> mode.
          </>
        }
      />

      <section className="flex flex-col gap-4 border border-lp-line bg-lp-panel p-5">
        <div
          className="flex flex-wrap items-center gap-2"
          role="group"
          aria-label="Mode panels"
        >
          <button
            type="button"
            aria-pressed={showCurrent}
            onClick={() => setShowCurrent((visible) => !visible)}
            className={`label rounded-sm border px-2 py-1 ${
              showCurrent
                ? "border-lp-ink text-lp-ink"
                : "border-lp-line text-lp-mute hover:text-lp-ink"
            }`}
          >
            Current
          </button>
          <button
            type="button"
            aria-pressed={showHistorical}
            onClick={() => setShowHistorical((visible) => !visible)}
            className={`label rounded-sm border px-2 py-1 ${
              showHistorical
                ? "border-lp-ink text-lp-ink"
                : "border-lp-line text-lp-mute hover:text-lp-ink"
            }`}
          >
            Historical
          </button>
          <span className="font-mono text-[11px] text-lp-mute">
            both answers are always fetched
          </span>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
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
            {loading ? "Grounding…" : "Ground"}
          </button>
        </div>
      </section>

      {error && (
        <div className="border border-lp-retired bg-lp-panel px-4 py-3 font-mono text-sm text-lp-retired">
          {error}
        </div>
      )}

      {current && historical && (
        <section className="grid gap-4 md:grid-cols-2">
          {showCurrent && <ReceiptPanel title="Current" receipt={current} />}
          {showHistorical && (
            <ReceiptPanel title="Historical" receipt={historical} />
          )}
        </section>
      )}
    </div>
  );
}
