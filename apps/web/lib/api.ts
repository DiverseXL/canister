export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type RankedEntry = {
  rank: number;
  doc_id: string;
  label: string;
  bm25_score?: number;
  reason?: string;
};

export type Decision = {
  decision: string;
  selected_value: string | null;
  priority: number | null;
  reason: string;
};

export type Receipt = {
  mode: string;
  mode_requested?: string;
  question?: string;
  query: string;
  query_id: string;
  receipt_id?: string;
  tenant_id?: string;
  grounding: string;
  claim_keys: string[];
  decisions: Record<string, Decision>;
  pool_size: number;
  input_ranking: RankedEntry[];
  cut_set: RankedEntry[];
  final_context: RankedEntry[];
  pinned: string[];
  final_size: number;
  sha256: string;
  cypher_queries: Record<string, string>;
};

export type ClaimsResponse = {
  tenant_id: string;
  count: number;
  claims: {
    claim_key: string;
    entity: string;
    attribute: string;
    attribute_label: string;
    decision: string;
    selected_value: string | null;
    priority: number | null;
    reason: string;
  }[];
  sha256: string;
  cypher_queries: Record<string, string>;
};

async function unwrap(res: Response): Promise<any> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? detail?.error ?? `${res.status}`;
    throw new Error(message);
  }
  return body;
}

export async function apiGet(path: string): Promise<any> {
  return unwrap(await fetch(`${API_BASE}${path}`, { cache: "no-store" }));
}

export async function apiPost(path: string, payload: unknown): Promise<any> {
  return unwrap(
    await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    }),
  );
}
