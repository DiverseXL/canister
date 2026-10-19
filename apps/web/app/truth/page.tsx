"use client";

import { useEffect, useState } from "react";

import { apiGet, type ClaimsResponse } from "@/lib/api";
import { ApiBanner, ApiError } from "@/components/api-status";

export default function Truth() {
  const [claims, setClaims] = useState<ClaimsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setClaims(await apiGet("/claims"));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <ApiBanner />
      <section>
        <h1 className="text-2xl font-semibold text-white">Truth</h1>
        <p className="mt-1 text-sm text-slate-400">
          Every claim key with its current state, read from{" "}
          <span className="font-mono">GET /claims</span>.
        </p>
      </section>      {error && <ApiError error={error} />}

      <section className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="py-2 pr-4">Entity</th>
              <th className="py-2 pr-4">Attribute</th>
              <th className="py-2 pr-4">State</th>
              <th className="py-2 pr-4">Value</th>
              <th className="py-2 pr-4">Reason</th>
              <th className="py-2">Claim key</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {(claims?.claims ?? []).map((claim) => (
              <tr key={claim.claim_key} className="border-t border-edge">
                <td className="py-2 pr-4">{claim.entity}</td>
                <td className="py-2 pr-4">{claim.attribute_label}</td>
                <td className="py-2 pr-4">
                  <span className={`label-${claim.decision.toLowerCase()}`}>
                    {claim.decision}
                  </span>
                </td>
                <td className="py-2 pr-4">{claim.selected_value ?? "—"}</td>
                <td className="py-2 pr-4 text-slate-400">{claim.reason}</td>
                <td className="py-2 text-slate-500">{claim.claim_key}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
