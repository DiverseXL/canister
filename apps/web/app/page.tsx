"use client";

import { useEffect, useState } from "react";

import { API_BASE, apiGet, type ClaimsResponse } from "@/lib/api";

export default function Overview() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [claims, setClaims] = useState<ClaimsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setHealth(await apiGet("/health"));
        setClaims(await apiGet("/claims"));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  const counts: Record<string, number> = {};
  for (const claim of claims?.claims ?? []) {
    counts[claim.decision] = (counts[claim.decision] ?? 0) + 1;
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold text-white">Overview</h1>
        <p className="mt-1 text-sm text-slate-400">
          Live from <span className="font-mono">{API_BASE}</span>. Nothing on this
          page is hardcoded.
        </p>
      </section>

      {error && (
        <div className="card border-retired text-retired">
          Could not reach the API: {error}
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Graph reachable
          </div>
          <div className="mt-1 text-2xl font-semibold">
            {health ? String(health.graph_reachable) : "…"}
          </div>
        </div>
        <div className="card">
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Tenant
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold">
            {claims?.tenant_id ?? "…"}
          </div>
        </div>
        <div className="card">
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Claim keys
          </div>
          <div className="mt-1 text-2xl font-semibold">
            {claims?.count ?? "…"}
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {["CANON", "CONTESTED", "UNKNOWN"].map((decision) => (
          <div key={decision} className="card">
            <div className="text-xs uppercase tracking-wide text-slate-400">
              {decision}
            </div>
            <div className="mt-1 text-2xl font-semibold">
              {claims ? (counts[decision] ?? 0) : "…"}
            </div>
          </div>
        ))}
      </section>

      <section className="card">
        <div className="text-xs uppercase tracking-wide text-slate-400">
          Response sha256 (claims)
        </div>
        <div className="mt-1 break-all font-mono text-sm text-slate-300">
          {claims?.sha256 ?? "…"}
        </div>
      </section>
    </div>
  );
}
