"use client";

import { useEffect, useState } from "react";

import PageHeader from "@/components/page-header";
import StateBadge from "@/components/state-badge";
import { apiGet, type ClaimsResponse } from "@/lib/api";

/** Claim keys are shortened for the table; the full value lives in title. */
function shortenKey(key: string): string {
  return key.length > 12 ? `${key.slice(0, 12)}…` : key;
}

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
    <div className="space-y-10">
      <PageHeader
        eyebrow="Truth"
        title="Truth"
        description={
          <>
            Every claim key with its current state, read from{" "}
            <span className="font-mono">GET /claims</span>.
          </>
        }
      />

      {error && (
        <div className="border border-lp-retired bg-lp-panel px-4 py-3 font-mono text-sm text-lp-retired">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left">
          <thead>
            <tr className="border-b border-lp-line">
              <th className="label py-2 pr-4 align-bottom text-lp-mute">
                Entity
              </th>
              <th className="label py-2 pr-4 align-bottom text-lp-mute">
                Attribute
              </th>
              <th className="label py-2 pr-4 align-bottom text-lp-mute">
                State
              </th>
              <th className="label py-2 pr-4 align-bottom text-lp-mute">
                Value
              </th>
              <th className="label py-2 pr-4 align-bottom text-lp-mute">
                Reason
              </th>
              <th className="label py-2 align-bottom text-lp-mute">
                Claim key
              </th>
            </tr>
          </thead>
          <tbody className="font-mono text-[13px]">
            {(claims?.claims ?? []).map((claim) => (
              <tr key={claim.claim_key} className="border-b border-lp-line">
                <td className="py-2 pr-4 text-lp-ink">{claim.entity}</td>
                <td className="py-2 pr-4 text-lp-ink">
                  {claim.attribute_label}
                </td>
                <td className="py-2 pr-4">
                  <StateBadge state={claim.decision} />
                </td>
                <td className="py-2 pr-4 text-lp-ink">
                  {claim.selected_value ?? "—"}
                </td>
                <td className="py-2 pr-4 text-lp-ink">{claim.reason}</td>
                <td className="py-2" title={claim.claim_key}>
                  {shortenKey(claim.claim_key)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
