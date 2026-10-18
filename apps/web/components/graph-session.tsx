"use client";

import Link from "next/link";
import { useState } from "react";

import StateBadge from "@/components/state-badge";
import { apiPost, type Receipt } from "@/lib/api";

const PRESETS: [string, string][] = [
  ["Starter price", "What is the current starter plan price for Acme Corp?"],
  ["Launch date", "What is the current launch date for Initech?"],
  ["Pro price (absent)", "What is the current pro plan price for Stark Industries?"],
];

/** Retired documents are shown struck through and labelled RETIRED. */
function labelWord(label: string): string {
  return label === "superseded" ? "RETIRED" : label;
}

function PathChain({ path }: { path: [string, string][] }) {
  return (
    <span className="font-mono text-[11px] leading-relaxed text-lp-mute">
      {path.map(([nodeLabel, nodeId], index) => (
        <span key={`${nodeLabel}:${nodeId}`} className="whitespace-nowrap">
          {index > 0 && <span className="px-1">→</span>}
          <span className="rounded-sm border border-lp-line px-1.5 py-0.5 text-lp-ink">
            {nodeLabel}
          </span>
          <span> {nodeId.slice(0, 8)}…</span>
        </span>
      ))}
    </span>
  );
}

/**
 * GraphSession: a live grounding session embedded in the landing page. Every
 * question hits the same POST /ground endpoint the console uses (demo tenant),
 * so the graph decides in front of the visitor — answers, cut documents and
 * the walked justification paths all come from the API response.
 */
export default function GraphSession() {
  const [question, setQuestion] = useState(PRESETS[0][1]);
  const [mode, setMode] = useState<"current" | "historical">("current");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run(q: string) {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setReceipt(await apiPost("/ground", { question: q, mode }));
    } catch (err) {
      setReceipt(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const decisions = receipt ? Object.entries(receipt.decisions) : [];
  const supersededCuts =
    receipt?.cut_set.filter((entry) => entry.reason === "superseded") ?? [];
  const budgetCuts = receipt ? receipt.cut_set.length - supersededCuts.length : 0;

  return (
    <div className="grid gap-8 md:grid-cols-[170px_minmax(0,1fr)] md:gap-14">
      <div>
        <p className="label text-lp-mute">03 &mdash; Ask the graph</p>
      </div>
      <div className="space-y-8">
        <div className="max-w-[64ch] space-y-4">
          <h2 className="display text-[clamp(1.5rem,3.2vw,2.4rem)] leading-[1.1] tracking-[-0.005em] text-lp-ink">
            Run a live session.
          </h2>
          <p className="text-[15px] leading-[1.85] text-lp-mute">
            Every question below hits the same{" "}
            <span className="font-mono text-lp-ink">POST /ground</span> endpoint
            the console uses, against the seeded demo tenant. Nothing here is
            cached: the graph decides in front of you, and each cut document
            carries the walked path that justifies the cut.
          </p>
        </div>

        <div className="flex flex-col gap-4 border border-lp-line bg-lp-panel p-5">
          <div
            className="flex flex-wrap items-center gap-2"
            role="group"
            aria-label="Example questions"
          >
            {PRESETS.map(([name, preset]) => (
              <button
                key={name}
                type="button"
                onClick={() => {
                  setQuestion(preset);
                  run(preset);
                }}
                disabled={loading}
                className="label rounded-full border border-lp-line px-3 py-1.5 text-lp-mute hover:border-lp-ink hover:text-lp-ink disabled:opacity-40"
              >
                {name}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <label htmlFor="session-question" className="sr-only">
              Question
            </label>
            <input
              id="session-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") run(question);
              }}
              placeholder="Ask about any claim in the demo corpus…"
              className="flex-1 border border-lp-line bg-lp-bg px-4 py-3 font-mono text-sm text-lp-ink placeholder:text-lp-mute"
            />
            <div className="flex items-center gap-2">
              {(["current", "historical"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={mode === m}
                  onClick={() => setMode(m)}
                  className={`label rounded-sm border px-2 py-2 ${
                    mode === m
                      ? "border-lp-ink text-lp-ink"
                      : "border-lp-line text-lp-mute hover:text-lp-ink"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
            <button
              onClick={() => run(question)}
              disabled={loading || question.trim().length === 0}
              className="label rounded-full bg-lp-ink px-4 py-2 text-lp-bg disabled:opacity-40"
            >
              {loading ? "Grounding…" : "Ask"}
            </button>
          </div>
        </div>

        {error && (
          <div className="border border-lp-retired bg-lp-panel px-4 py-3 font-mono text-sm text-lp-retired">
            Fail closed: {error} — the graph never falls back to plain
            retrieval.
          </div>
        )}

        {!receipt && !error && (
          <p className="font-mono text-[13px] text-lp-mute">
            Pick a question or type your own — the answer comes from the graph,
            not from this page.
          </p>
        )}

        {receipt && (
          <div className="space-y-6">
            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <div className="label text-lp-mute">Answer</div>
              <div className="mt-3 space-y-2">
                {decisions.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex flex-wrap items-baseline gap-3"
                  >
                    <StateBadge state={value.decision} />
                    <span className="font-mono text-lg text-lp-ink">
                      {value.selected_value ?? "—"}
                    </span>
                    <span className="font-mono text-[11px] text-lp-mute">
                      {value.reason}
                      {value.priority != null
                        ? ` · priority ${value.priority}`
                        : ""}
                    </span>
                  </div>
                ))}
                {decisions.length === 0 && (
                  <span className="font-mono text-lg text-lp-mute">
                    No claim key matched this question.
                  </span>
                )}
              </div>
              <div className="mt-4 font-mono text-[11px] text-lp-mute">
                {receipt.final_size} docs in context · sha256{" "}
                {receipt.sha256.slice(0, 16)}… · receipt {receipt.receipt_id} ·{" "}
                <Link href="/gate" className="underline hover:text-lp-ink">
                  open the gate
                </Link>
              </div>
            </div>

            <div className="border border-lp-line bg-lp-panel px-5 py-6">
              <div className="label text-lp-mute">Cut from the ranking</div>
              {supersededCuts.length === 0 ? (
                <p className="mt-3 font-mono text-[13px] text-lp-mute">
                  Nothing retired in the pool for this question.
                </p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {supersededCuts.map((entry) => (
                    <li key={entry.doc_id} className="space-y-1">
                      <div className="flex flex-wrap items-baseline gap-2 font-mono text-xs">
                        <span className="text-lp-mute">{entry.rank}</span>
                        <span className="value-retired">{entry.doc_id}</span>
                        <span className="text-lp-mute">
                          {labelWord(entry.label)} · {entry.reason}
                        </span>
                      </div>
                      {entry.graph_path && entry.graph_path.length > 0 && (
                        <div className="pl-6">
                          <PathChain path={entry.graph_path} />
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {budgetCuts > 0 && (
                <p className="mt-3 font-mono text-[11px] text-lp-mute">
                  + {budgetCuts} more cut to hold the {receipt.final_size}-document
                  budget
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
