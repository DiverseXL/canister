import PageHeader from "@/components/page-header";
import StateBadge from "@/components/state-badge";
import { readJson, repoRoot } from "@/lib/files";

export const dynamic = "force-dynamic";

const STATE_WORDS = new Set(["CANON", "CONTESTED", "UNKNOWN"]);
const STATE_COLUMNS = new Set(["state", "decision"]);

function Table({
  head,
  rows,
}: {
  head: string[];
  rows: (string | number | null)[][];
}) {
  const wide = head.length >= 4 ? " min-w-[640px]" : "";
  return (
    <div className="overflow-x-auto">
      <table className={`w-full${wide} border-collapse text-left`}>
        <thead>
          <tr className="border-b border-lp-line">
            {head.map((cell) => (
              <th
                key={cell}
                className="label py-2 pr-4 align-bottom text-lp-mute"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono text-[13px]">
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-lp-line align-top">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="py-2 pr-4 text-lp-ink">
                  {cell === null ? (
                    "—"
                  ) : STATE_COLUMNS.has(head[cellIndex]) &&
                    typeof cell === "string" &&
                    STATE_WORDS.has(cell) ? (
                    <StateBadge state={cell} />
                  ) : (
                    String(cell)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4 border border-lp-line bg-lp-panel px-5 py-6">
      <h2 className="font-mono text-[13px] font-medium uppercase tracking-[0.12em] text-lp-ink">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default async function Results() {
  const controls = await readJson("evidence/controls.json");
  const benchmark = await readJson("evidence/benchmark.json");
  const stress = await readJson("corpus/out/stress.json");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Results"
        title="Results"
        description={
          <>
            Rendered directly from <span className="font-mono">evidence/*.json</span> and{" "}
            <span className="font-mono">corpus/out/stress.json</span> under{" "}
            <span className="font-mono">{repoRoot()}</span>.
          </>
        }
      />

      {!controls && (
        <div className="border border-dashed border-lp-mute bg-lp-panel px-4 py-3 font-mono text-[13px] text-lp-mute">
          evidence/controls.json is <span className="font-mono">not_run</span>. Run{" "}
          <span className="font-mono">make controls</span>.
        </div>
      )}

      {controls && (
        <>
          <Section title="Controls metadata">
            <Table
              head={["field", "value"]}
              rows={[
                ["generated_by", controls.generated_by],
                ["metrics_class", controls.metrics_class],
                ["budget", controls.budget],
                ["documents", controls.corpus?.documents],
                ["seed", controls.corpus?.seed],
              ]}
            />
          </Section>

          <Section title="a) Random-removal control">
            <Table
              head={["metric", "value"]}
              rows={Object.entries(
                controls.random_removal_control.summary,
              ).map(([key, value]) => [key, value as number])}
            />
          </Section>

          <Section title="b) Mechanism split (over conflict questions)">
            <Table
              head={[
                "arm",
                "superseded in context",
                "current gold in context",
                "size mean",
                "all k",
              ]}
              rows={Object.entries(controls.mechanism_split.arms).map(
                ([arm, value]: [string, any]) => [
                  arm,
                  value.superseded_in_context,
                  value.current_gold_in_context,
                  value.context_size_mean,
                  String(value.context_size_all_ten),
                ],
              )}
            />
          </Section>

          <Section title="c) top-k sweep (baseline vs temporal leak)">
            <Table
              head={["k", "baseline leak", "temporal leak", "baseline all k", "temporal all k"]}
              rows={Object.entries(controls.top_k_sweep).map(
                ([k, value]: [string, any]) => [
                  k,
                  value.baseline.leak_total,
                  value.temporal.leak_total,
                  String(value.baseline.size_all_k),
                  String(value.temporal.size_all_k),
                ],
              )}
            />
          </Section>

          <Section title="d) Historical mode">
            <Table
              head={["metric", "value"]}
              rows={[
                ["conflicts", controls.historical_mode.summary.conflicts],
                [
                  "all recover retired evidence",
                  String(
                    controls.historical_mode.summary
                      .all_conflicts_recover_retired_evidence,
                  ),
                ],
                [
                  "any retired doc cut",
                  String(controls.historical_mode.summary.any_retired_doc_cut),
                ],
              ]}
            />
          </Section>

          <Section title="e) Safety envelope (all questions)">
            <Table
              head={["metric", "value"]}
              rows={[
                ["non-conflict questions", controls.safety_envelope.non_conflict_questions],
                [
                  "non-conflict byte-identical",
                  controls.safety_envelope.non_conflict_byte_identical,
                ],
                [
                  "expected removed outside conflicts",
                  controls.safety_envelope.expected_docs_removed_outside_conflicts,
                ],
                [
                  "removed outside conflicts",
                  controls.safety_envelope.docs_removed_outside_conflicts,
                ],
                ["pins outside conflicts", controls.safety_envelope.pins_outside_conflicts],
              ]}
            />
            <Table
              head={["qid", "kind", "conflict", "removed", "pinned", "decisions"]}
              rows={controls.safety_envelope.interventions.map((row: any) => [
                row.qid,
                row.claim_kind,
                String(row.conflict),
                row.removed_from_base_ranking.join(",") || "—",
                row.pinned_current.join(",") || "—",
                Object.entries(row.decisions)
                  .map(([key, value]: [string, any]) => `${key}:${value.reason}`)
                  .join(" "),
              ])}
            />
          </Section>

          <Section title="f) Tenant isolation">
            <Table
              head={["field", "value"]}
              rows={[
                ["isolated", String(controls.tenant_isolation.isolated)],
                ["claim entity", controls.tenant_isolation.claim_key_entity],
                ["claim attribute", controls.tenant_isolation.claim_key_attribute],
                ["tenant A value", controls.tenant_isolation.tenant_a_value],
                ["tenant B value", controls.tenant_isolation.tenant_b_value],
              ]}
            />
          </Section>
        </>
      )}

      {benchmark && (
        <Section title="Benchmark arms (flat vs temporal)">
          <Table
            head={["metric", "flat", "temporal"]}
            rows={Object.keys(benchmark.arms.flat.metrics).map((key) => [
              key,
              benchmark.arms.flat.metrics[key],
              benchmark.arms.temporal.metrics[key],
            ])}
          />
        </Section>
      )}

      {stress && (
        <Section title="Stress set (paraphrased supersession)">
          <Table
            head={["metric", "value"]}
            rows={[
              ["documents", stress.summary.documents],
              ["value recall", stress.summary.value_recall],
              ["supersession recall", stress.summary.supersession_recall],
              ["current recall", stress.summary.current_recall],
              [
                "outcomes",
                Object.entries(stress.summary.outcomes)
                  .map(([key, value]) => `${key}=${value}`)
                  .join(" "),
              ],
            ]}
          />
          <Table
            head={["doc", "entity", "attribute", "expected", "surface", "decision", "selected"]}
            rows={stress.results.map((row: any) => [
              row.doc_id,
              row.entity,
              row.attribute,
              row.expected_current,
              row.surface_new,
              row.decision,
              row.selected_value ?? "—",
            ])}
          />
        </Section>
      )}
    </div>
  );
}
