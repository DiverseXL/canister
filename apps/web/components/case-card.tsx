import { readJson } from "@/lib/files";
import StateBadge from "@/components/state-badge";

interface Claim {
  attribute?: string;
  attribute_label?: string;
  entity?: string;
  value_norm?: string;
  value_raw?: string;
  stance?: string;
}

interface DocumentItem {
  doc_id: string;
  gold_label?: string;
  claims?: Claim[];
}

interface ClaimKeyItem {
  id?: string;
  entity?: string;
  attribute?: string;
  attribute_label?: string;
  current_value?: string;
  old_value?: string;
}

interface CutSetItem {
  doc_id: string;
  label?: string;
  reason?: string;
}

export default async function CaseCard() {
  const gateExample = await readJson("evidence/gate_example.json");
  const gold = await readJson("evidence/gold.json");

  const ckId: string | undefined =
    gateExample?.claim_keys?.[0] ??
    (gateExample?.decisions ? Object.keys(gateExample.decisions)[0] : undefined);

  const decisionInfo = ckId && gateExample?.decisions ? gateExample.decisions[ckId] : null;

  const goldClaimKeys: ClaimKeyItem[] = gold?.claim_keys ?? [];
  const goldClaimKey = goldClaimKeys.find(
    (ck) =>
      ck.id === ckId ||
      (ck.entity === "Acme Corp" && ck.attribute_label === "starter plan price")
  );

  const entity = goldClaimKey?.entity ?? "Acme Corp";
  const attributeLabel = goldClaimKey?.attribute_label ?? "starter plan price";

  const state = decisionInfo?.decision ?? "not recorded";
  const priority =
    decisionInfo?.priority !== undefined ? String(decisionInfo.priority) : "not recorded";
  const reason = decisionInfo?.reason ?? "not recorded";

  // Cut set analysis
  const cutSet: CutSetItem[] = gateExample?.cut_set ?? [];
  const supersededCut = cutSet.filter(
    (item) => item.label === "superseded" || item.reason === "superseded"
  );
  const retiredDocCount = supersededCut.length;
  const cutDocIds = supersededCut.map((item) => item.doc_id);

  const documents: DocumentItem[] = gold?.documents ?? [];
  const docMap = new Map<string, DocumentItem>(documents.map((d) => [d.doc_id, d]));

  const assertingDocIds: string[] = [];
  const retiredValuesSet = new Set<string>();

  for (const docId of cutDocIds) {
    const doc = docMap.get(docId);
    if (doc?.claims) {
      for (const c of doc.claims) {
        if (c.entity === entity) {
          assertingDocIds.push(docId);
          if (c.value_raw) retiredValuesSet.add(c.value_raw);
          else if (c.value_norm) retiredValuesSet.add(`$${c.value_norm}`);
        }
      }
    }
  }

  const retiredDocIds =
    assertingDocIds.length > 0 ? Array.from(new Set(assertingDocIds)) : cutDocIds;

  const currentDoc = documents.find((d) =>
    (d.claims ?? []).some(
      (c) =>
        c.entity === entity &&
        (c.value_norm === decisionInfo?.selected_value || c.stance === "supersede")
    )
  );
  const currentClaim = currentDoc?.claims?.find((c) => c.entity === entity);
  const currentValue =
    currentClaim?.value_raw ??
    (decisionInfo?.selected_value ? `$${decisionInfo.selected_value}` : "not recorded");

  const retiredValue =
    retiredValuesSet.size > 0 ? Array.from(retiredValuesSet).join(", ") : "not recorded";

  return (
    <div className="rounded-xl border border-lp-line bg-lp-panel p-5 sm:p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-lp-line pb-3">
        <span className="label text-lp-mute">
          One real conflict &mdash; synthetic corpus
        </span>
        <span className="font-mono text-xs text-lp-ink font-medium">
          {entity} <span className="text-lp-mute">/</span> {attributeLabel}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* RETIRED Panel */}
        <div className="rounded-lg border border-lp-line bg-lp-bg/80 p-4 space-y-3 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="label rounded-sm border border-lp-retired/40 px-1.5 py-0.5 text-lp-retired font-bold">
                RETIRED
              </span>
              <span className="font-mono text-[11px] text-lp-mute">
                {retiredDocCount} cut
              </span>
            </div>
            <div>
              <span className="value-retired text-3xl font-mono font-bold">
                {retiredValue}
              </span>
            </div>
          </div>

          <div className="border-t border-lp-line/60 pt-3 space-y-1.5">
            <p className="label text-[10px] text-lp-mute">Asserted by documents</p>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {retiredDocIds.length > 0 ? (
                retiredDocIds.map((id) => (
                  <span
                    key={id}
                    className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-lp-panel border border-lp-line text-lp-mute"
                  >
                    {id}
                  </span>
                ))
              ) : (
                <span className="font-mono text-xs text-lp-mute">not recorded</span>
              )}
            </div>
          </div>
        </div>

        {/* CURRENT Panel */}
        <div className="rounded-lg border border-lp-line bg-lp-bg/80 p-4 space-y-3 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="label rounded-sm border border-lp-line px-1.5 py-0.5 text-lp-ink font-bold">
                CURRENT
              </span>
              <StateBadge state={state} />
            </div>
            <div>
              <span className="value-current text-3xl font-mono font-bold text-lp-ink">
                {currentValue}
              </span>
            </div>
          </div>

          <div className="border-t border-lp-line/60 pt-3 space-y-1.5 text-xs font-mono">
            <div className="flex justify-between items-center text-lp-mute">
              <span>Priority:</span>
              <span className="text-lp-ink font-medium">{priority}</span>
            </div>
            <div className="flex justify-between items-center text-lp-mute">
              <span>Reason:</span>
              <span className="text-lp-ink font-medium">{reason}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
