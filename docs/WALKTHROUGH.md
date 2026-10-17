# Canister: Technical Walkthrough & Judge Briefing

This document is a comprehensive technical walkthrough for presenting Canister to hackathon judges. It explains the system architecture, truth topology, core algorithms, edge cases, and verbatim code references, concluding with 15 verified judge Q&As.

---

## 1. Executive Summary

Search engines find what is **relevant**. They cannot tell what is still **true**. In corporate wikis, tickets, and release notes, older documents frequently out-rank newer ones because they share the exact same vocabulary and have accumulated more citations or corroboration.

Canister places a **temporal claim graph on FalkorDB** directly between the retriever (SQLite FTS5 BM25) and the LLM:
- BM25 proposes candidate documents based on lexical relevance.
- FalkorDB decides which documents are currently true, historical, or superseded.
- Superseded documents are excised, missing current documents are pinned, and the context is backfilled to maintain an exact 10-document budget.
- Every decision produces an immutable, replayable **grounding record** (`receipt`) with SHA-256 fingerprints and Cypher query identifiers.
- **Fail-closed contract:** If FalkorDB is unavailable, the API returns `503 TEMPORAL_GRAPH_UNAVAILABLE`. It never silently degrades to raw retrieval.

---

## 2. End-to-End Data Flow

```
[ Raw Documents ]
       |
       v
[ Deterministic Extractor ] --------> [ SQLite FTS5 Index ]
(canister_extraction)                 (canister_retrieval.FtsStore)
       |
       v
[ Ingest & Graph Writer ] -----------> [ FalkorDB Graph ]
(canister_graph.writer)                 - Entity, ClaimKey, Proposition,
       |                                - Assertion, Artifact
       v
[ Canonization Resolver ] -----------> [ FalkorDB Truth Topology ]
(canister_graph.canonize)               - CanonEvent nodes
                                        - [:SUPERSEDES] revision chains
                                        - [:SELECTS] proposition links
       |
       +---------------------------------------------+
                                                     |
[ User / Agent Question ]                            |
       |                                             |
       v                                             |
[ POST /ground ]                                     |
(canister_api.main)                                  |
       |                                             |
       v                                             v
[ Grounding Engine ] <------------------ [ GraphClaimProvider ]
(canister_graph.grounding)               - relevant_claim_keys()
       |                                 - claim_state()
       |                                 - doc_claim_values()
       +---> BM25 Retrieval (top candidates)
       +---> classify() (current, superseded, contested, historical)
       +---> _select_temporal() (Filter -> Pin -> Backfill)
       |
       v
[ Grounding Record / Receipt ]
(JSON with final context, cut set, sha256, and cypher query IDs)
```

### Stage 1: Ingestion & Lexical Indexing
1. Input documents (Markdown with YAML frontmatter) are processed by `canister_extraction`.
2. Extracted claims yield `ArtifactInput` (document metadata and SHA-256) and `AssertionInput` (entity, attribute, raw value, normalized value, stance, explicit supersession flag, prior value, and exact character offsets).
3. Document bodies are stored in SQLite FTS5 via `FtsStore.add_documents()` to power BM25 ranking.

### Stage 2: Graph Ingestion (`writer.py`)
1. `GraphWriter.ingest(documents)` takes an iterable of `IngestDocument`.
2. For each artifact, `GraphWriter.write_artifact()` executes a parameterized Cypher `MERGE (a:Artifact {id: $id})`.
3. For each assertion, `GraphWriter.write_assertion()` executes a Cypher `MERGE` that links:
   - `(e:Entity)-[:HAS_CLAIM]->(ck:ClaimKey)-[:HAS_VALUE]->(p:Proposition)`
   - `(as:Assertion)-[:ASSERTS]->(p)`
   - `(as:Assertion)-[:IN_ARTIFACT]->(art:Artifact)`
4. Node and relationship IDs are generated deterministically using SHA-256 (`canister_graph.ids`), guaranteeing that re-ingesting the exact same corpus creates 0 new nodes and 0 new relationships.

### Stage 3: Canonization (`writer.py` + `canonize.py`)
1. `GraphWriter.canonize_all()` queries all unique claim keys via `GraphWriter.claim_keys()`.
2. For each key, `GraphWriter.assertions_for(claim_key)` retrieves all assertions from the graph.
3. The pure function `canister_graph.canonize.resolve(claim_key, assertions)` evaluates the assertions in a strict 4-level priority order (see Section 3).
4. The result (`ClaimDecision`) is recorded by `GraphWriter.write_canon_event(decision)`:
   - Creates a `(ce:CanonEvent)` node with `current=true`.
   - Clears `current=false` on any prior `CanonEvent` nodes for this claim key via `CLEAR_OTHER_CURRENT`.
   - Links the new event to the previous event via `LINK_SUPERSEDES`: `(ce)-[:SUPERSEDES]->(prev)`.
   - Links the event to the chosen proposition via `LINK_SELECTS`: `(ce)-[:SELECTS]->(p)`.

### Stage 4: Query Time & Temporal Gating (`grounding.py`)
1. The client sends a request to `POST /ground` with a natural language `question`, `mode` (`"temporal"`, `"flat"`, or `"history"`), and `tenant_id`.
2. `canister_graph.grounding.ground()` orchestrates the gate:
   - `GraphClaimProvider.relevant_claim_keys(question)` matches known claim keys against the question.
   - The BM25 retriever fetches an expanded candidate pool (e.g. 40 candidates).
   - `GraphClaimProvider.claim_state()` and `GraphClaimProvider.doc_claim_values()` fetch the active truth topology from FalkorDB.
   - `classify()` assigns a label to each candidate: `current`, `contested`, `historical`, `superseded`, or `not_in_claim_graph`.
   - `_select_temporal()` performs the three-step **filter**, **pin**, and **backfill** sequence.
   - Returns a structured grounding record containing the final 10-document context, the full cut set with cut reasons, and SHA-256 hashes of the context and Cypher queries.

---

## 3. Deep Dive: Core Modules and Exact Function Names

### `packages/graph/src/canister_graph/canonize.py`
This module contains pure Python business logic with zero database dependencies.

- **`resolve(claim_key: str, assertions: Iterable[AssertionView]) -> ClaimDecision`**
  Resolves the current state of a claim key using four priority rules:
  1. **Rule 1: Explicit supersession language beats everything.**
     Identified when `assertion.explicit_supersession` is `True` (e.g. "supersedes previous guidance", "changed from X to Y"). If multiple explicit assertions exist, `_sort_key` picks the latest by publication date and ID. This rule is the *only* mechanism permitted to beat majority corroboration.
  2. **Rule 2: Reliable temporal ordering (metadata and semantics agree).**
     Triggered when multiple distinct values exist, all assertions have valid ISO publication dates, the latest date is strictly greater than older dates (`metadata_agrees`), and semantic change is evident (`assertion.stance == "supersede"` or `prior_value` matches an existing proposition).
  3. **Rule 3: Corroboration is a tie-break only.**
     If all assertions agree on a single proposition (`len(values) == 1`), the value is selected as `CANON`. Corroboration is strictly a tie-break; 9 old assertions can never override 1 newer supersession.
  4. **Rule 4: No signal -> `CONTESTED`.**
     If conflicting values exist without valid supersession language or agreeing temporal metadata, the claim is assigned `CONTESTED` with `selected_value = None`. Canister never invents an ordering.
  5. **Empty assertions -> `UNKNOWN`.**
     If no assertions exist for a key, the decision is `UNKNOWN` with reason `"no_assertions"`.

- **`_canon(...)`**
  Helper that constructs the `ClaimDecision` object, automatically identifying all superseded assertions (`value_norm != selected.value_norm`) and evidence assertions.

- **`_sort_key(assertion: AssertionView) -> tuple[str, str]`**
  Returns `(assertion.published_at or "", assertion.assertion_id)` for stable, deterministic ordering.

---

### `packages/graph/src/canister_graph/writer.py`
Handles idempotent persistence and revision history in FalkorDB.

- **`GraphWriter.ensure_schema()`**
  Executes `CREATE INDEX FOR (n:Label) ON (n.prop)` for all schema indexes (`Entity.id`, `ClaimKey.id`, `Proposition.id`, `Assertion.id`, `Artifact.id`, `Artifact.doc_id`, `CanonEvent.id`, `CanonEvent.claim_key_id`). It catches and ignores exceptions containing `"already indexed"` to remain idempotent.

- **`GraphWriter.write_artifact(artifact: ArtifactInput)`**
  Executes `WRITE_ARTIFACT` using `MERGE (a:Artifact {id: $id})` with SHA-256 and document path.

- **`GraphWriter.write_assertion(assertion: AssertionInput) -> str`**
  Executes `WRITE_ASSERTION`, merging the entity, claim key, proposition, assertion, and artifact relationships in a single Cypher transaction.

- **`GraphWriter.ingest(documents: Iterable[IngestDocument]) -> IngestStats`**
  Iterates over documents, invoking `write_artifact` and `write_assertion`.

- **`GraphWriter.assertions_for(claim_key: str) -> list[AssertionView]`**
  Executes `READ_ASSERTIONS` traversing `(ClaimKey)-[:HAS_VALUE]->(Proposition)<-[:ASSERTS]-(Assertion)-[:IN_ARTIFACT]->(Artifact)` to reconstruct typed assertion objects.

- **`GraphWriter.write_canon_event(decision: ClaimDecision) -> str`**
  Commits a canonization decision:
  1. `WRITE_CANON_EVENT`: Merges `(ce:CanonEvent {id: $id})` with `current=true`.
  2. `CLEAR_OTHER_CURRENT`: Matches prior events for the same `claim_key_id` and sets `prev.current=false`.
  3. `LINK_SUPERSEDES`: Orders prior events by `as_of DESC, id DESC LIMIT 1` and creates `(ce)-[:SUPERSEDES]->(prev)`.
  4. `LINK_SELECTS`: Merges `(ce)-[:SELECTS]->(p)` pointing to the selected `Proposition`.

- **`GraphWriter.canonize_all() -> list[ClaimDecision]`**
  Discovers all claim keys via `claim_keys()`, resolves each using `resolve()`, and records each event via `write_canon_event()`.

---

### `packages/graph/src/canister_graph/grounding.py`
Controls context selection, filtering, and audit receipt generation.

- **`classify(values: Sequence[tuple[str, str]], states: dict[str, ClaimState]) -> str`**
  Labels a document relative to the query's active claim keys according to strict precedence:
  $$\text{current} > \text{contested} > \text{historical} > \text{superseded} > \text{not\_in\_claim\_graph}$$
  If a document asserts a proposition that matches a `CANON` state's selected value, it is labelled `current`. If it asserts a proposition for a `CANON` state with a different value, it is labelled `superseded`.

- **`_select_temporal(ranking: list[Any], labels: dict[str, str], k: int) -> tuple[list[Any], list[str], set[str]]`**
  Executes the three-phase context stabilization:
  1. **Filter (Suppression):**
     `kept = [c for c in ranking if labels[c.doc_id] != "superseded"]`
     Every document holding retired claims is stripped out immediately.
  2. **Pin (Recall Recovery):**
     Iterates through `kept`. If any candidate has `labels[doc_id] == "current"` but was ranked outside the top `k`, it is pinned into the context. To preserve exact budget parity, the lowest-ranked candidate currently in `final` is evicted (`final.pop()`).
  3. **Backfill (Budget Maintenance):**
     If filtering removed documents and `len(final) < k`, the algorithm backfills candidates from `kept` in BM25 rank order until `len(final) == k`. The model receives exactly 10 documents every time.

- **`ground(question: str, mode: str, *, provider: ClaimProvider, retrieve, k: int = 10) -> dict[str, Any]`**
  The top-level entrypoint for `/ground`:
  - Validates `mode` (`"flat"`, `"temporal"`, `"history"`).
  - Retrieves candidates and labels them.
  - Applies context selection (`_select_temporal` for `"temporal"`, raw top-k for `"flat"`, only superseded for `"history"`).
  - Constructs the cut set with explicit reasons (`"superseded"`, `"outside_budget"`, or `"not_superseded"`).
  - Calculates `_sha256_context(final_context)` and attaches `cypher_queries()`.

- **`GraphClaimProvider`**
  Implements `ClaimProvider` protocol using live FalkorDB queries:
  - `relevant_claim_keys(question)`: Requires both the entity string to appear in the question and all tokens of the attribute label to be present.
  - `claim_state(claim_key)`: Reads `CanonEvent` where `ce.current=true`.
  - `doc_claim_values(doc_id, claim_keys)`: Traverses `Artifact -> Assertion -> Proposition` for the document.

---

## 4. The 503 Fail-Closed Rule

### The Code
In `packages/graph/src/canister_graph/client.py`:
```python
def select_graph(tenant_id: str, *, db: FalkorDB | None = None):
    db = db or build_client()
    ping(db)
    try:
        return db.select_graph(tenant_id)
    except Exception as exc:
        raise GraphUnavailable(f"could not select graph {tenant_id!r}: {exc}") from exc
```

In `services/api/src/canister_api/main.py`:
```python
@app.exception_handler(GraphUnavailable)
async def graph_unavailable_handler(request: Request, exc: GraphUnavailable):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": {"error": "TEMPORAL_GRAPH_UNAVAILABLE", "message": str(exc)}},
    )
```

### Why It Exists
In production enterprise architectures, systems often default to "graceful degradation": if a metadata cache or graph service goes down, the system silently falls back to basic keyword retrieval.

**In Canister, silent fallback is strictly prohibited because it reintroduces the exact security and factual failure the system was built to prevent.**

On our corpus, un-gated BM25 retrieval leaks **43 superseded documents across 18 conflict questions**. If FalkorDB goes down and Canister quietly fell back to BM25, the AI agent would cite retired pricing, outdated SLAs, or terminated employee permissions while believing it had valid context. 

By failing closed with `503 TEMPORAL_GRAPH_UNAVAILABLE`:
1. The calling agent or workflow immediately knows that temporal validity cannot be guaranteed.
2. The agent can refuse to answer, request user confirmation, or retry.
3. Factual corruption is blocked at the gateway.

---

## 5. 15 Judge Questions & Code-Verified Answers

### Q1: Why not just store timestamps in Postgres and sort by `updated_at DESC`?
**Answer:** Document timestamps in enterprise wikis and chat exports are notoriously misleading. An older document may be edited for typos without changing the fact; a newer document might mention an old policy for historical comparison; and multiple systems may lack synchronized clocks. Furthermore, simple timestamp sorting fails when a company fact is corroborated across 10 documents but superseded by 1 explicit update. Canister's `resolve()` requires semantic change or explicit supersession language (Rules 1 & 2) before allowing temporal ordering to override corroboration.

### Q2: Why use a graph database instead of a relational table with a `superseded_by` foreign key?
**Answer:** Three reasons:
1. **Revision Chains:** Claims undergo multiple revisions over time ($A \to B \to C$). FalkorDB resolves the chain by walking `(CanonEvent)-[:SUPERSEDES*1..10]->` to find the active head and trace complete lineage without knowing chain depth in advance.
2. **Residue Traversal:** To find every document in an organization that still asserts an invalidated proposition, the query traverses backwards from `Proposition <-[:ASSERTS]- Assertion -[:IN_ARTIFACT]-> Artifact`. The fan-in is unbounded, and each hop retains exact character span evidence.
3. **Tenant Isolation:** Graph separation via FalkorDB `select_graph(tenant_id)` ensures distinct truth topologies per tenant with zero cross-tenant query contamination.

### Q3: What happens in the 9-versus-1 majority adversarial case?
**Answer:** Nine documents assert an old price (`$0.15`) and one later document explicitly states that the price changed to `$0.07`. Under standard vector search or BM25, the nine older documents overwhelm retrieval. In Canister, `canister_graph.canonize.resolve()` evaluates Rule 1 (`explicit_supersession`). Rule 1 takes absolute precedence over Rule 3 (`corroborated`). The claim resolves to `$0.07` with priority 1. This is verified by `test_explicit_supersession_beats_majority()` in `test_canonize.py` and live in `verify.py`.

### Q4: What happens when two documents assert conflicting values without any supersession language or timestamps?
**Answer:** Rule 4 in `resolve()` triggers: `"no_signal"`. The claim state is marked `CONTESTED`, and `selected_value` is set to `None`. Canister refuses to guess or invent an arbitrary ordering. When an agent queries a contested claim, Canister exposes the conflict rather than presenting false certainty.

### Q5: How do you guarantee exact 10-document context parity between the baseline and temporal arms?
**Answer:** In `_select_temporal()` in `grounding.py`:
When superseded documents are excised from the top 10, the algorithm backfills candidates from the *same* BM25 ranking. When a missed current document is pinned into context, the lowest-ranked candidate is evicted (`final.pop()`). In all arms (baseline, random removal, cut-only, pin-only, and full gate), the context size is asserted to be exactly 10 (`context_size_all_ten: True` in `evidence/controls.json`).

### Q6: How does Canister prevent cross-tenant data leaks?
**Answer:** Canister enforces physical graph isolation using FalkorDB's native multi-graph capability. In `client.py`, `select_graph(tenant_id)` selects the dedicated graph for that tenant. In our test suite and demo, two tenants hold different values for the same claim key (`Acme Corp / starter_price`): `canister_controls_a` resolves to `0.07` and `canister_controls_b` resolves to `9.99` (source: `evidence/controls.json`, `tenant_isolation`). A traversal on one tenant cannot inspect or reach nodes in another.

### Q7: Why use SQLite FTS5 for BM25 instead of storing all document text in FalkorDB?
**Answer:** Separation of concerns:
- SQLite FTS5 is an ultra-fast, zero-overhead lexical search engine that handles full-text indexing and BM25 candidate proposal.
- FalkorDB manages the *truth topology*: entities, claims, propositions, assertions, and supersession event chains.
Storing full document prose in the graph would inflate graph memory without improving graph traversal speed. FalkorDB only stores the exact evidence quote and character span (`span_start`, `span_end`).

### Q8: What guarantees that re-ingesting the corpus will not duplicate graph nodes?
**Answer:** Every node and relationship identifier is deterministic. In `canister_graph.ids`:
- Artifact ID is `sha256("artifact:" + doc_id)`.
- ClaimKey ID is `sha256("claim_key:" + entity + ":" + attribute)`.
- Proposition ID is `sha256("proposition:" + claim_key_id + ":" + value_norm)`.
- Assertion ID is `sha256("assertion:" + artifact_id + ":" + claim_key_id + ":" + value_norm + ":" + start + ":" + end)`.
Every Cypher write in `writer.py` uses `MERGE (node {id: $id})`. Re-ingesting 200 documents creates exactly 0 new nodes (`idempotent_reingest` check in `verify.py`).

### Q9: What is a grounding record / receipt?
**Answer:** A structured JSON object generated by `ground()` that documents why a context was chosen. It contains:
1. `query_id`: SHA-256 of the mode and question.
2. `claim_keys`: Associated claim keys.
3. `decisions`: Active canonization states (`CANON`, `CONTESTED`, `UNKNOWN`).
4. `input_ranking`: The raw BM25 candidates.
5. `cut_set`: Documents removed, each with an explicit reason (`superseded`, `outside_budget`).
6. `final_context`: The filtered, pinned, and backfilled documents with their ranks and labels.
7. `sha256`: SHA-256 fingerprint over the final context.
8. `cypher_queries`: Truncated SHA-256 hashes of the exact Cypher queries executed.
The receipt is saved to disk and can be replayed at any time via `GET /grounding/{id}`.

### Q10: How does Canister answer historical questions (e.g. "What was the previous price?")?
**Answer:** By specifying `mode="history"` in `ground()`. In history mode, `classify()` still identifies document statuses, but `ground()` filters for documents labelled `superseded`. Across all 18 conflict questions in our benchmark, `mode="history"` achieves an 18/18 recovery rate for retired evidence, with 0 current documents included.

### Q11: Where does Canister break? What are its limitations?
**Answer:** Documented openly in our **Honesty: limitations** section and measured via `corpus/stress.py`:
On a stress set of 20 documents where supersession was expressed through conversational paraphrases without explicit cues ("we have since retired the old figure", "sometime in Q3"):
- 14 cases failed safely as `CONTESTED` (the extractor missed the change cue and treated both values as plain assertions).
- 6 cases failed unsafely as stale `CANON` (the new value was phrased so loosely that the extractor found nothing, leaving only the old value in the graph).
Canister makes no false claim of perfection: template/regex extractors require model assistance to catch conversational paraphrases.

### Q12: How are questions matched to claim keys without vector embeddings?
**Answer:** Through strict lexical matching in `GraphClaimProvider.relevant_claim_keys()`:
The entity name must appear as a substring in the question, and *all* whitespace-delimited tokens of the attribute label must be present as tokens in the question. Early prototypes used loose token overlap, which caused false-positive claim attachments. The strict rule eliminated all false matches across the test corpus.

### Q13: Does FalkorDB persist data across container restarts?
**Answer:** Yes. FalkorDB runs as a container with a mounted volume (`falkordb-data:/data`) and writes to Redis RDB/AOF persistence files. In `scripts/verify.py`, the `restart_persistence` check actively executes `docker restart canister-falkordb`, reconnects, and asserts that node counts before and after the restart are identical (552 before, 552 after).

### Q14: Why is the fail-closed 503 behavior superior to returning raw BM25 results?
**Answer:** Raw BM25 results leak outdated information 100% of the time on conflict queries in our corpus (43 leaks across 18 questions). Returning raw results under graph failure causes the agent to generate hallucinations with high confidence. A `503` informs the client application that contextual truth cannot be validated, allowing it to alert the user or pause execution safely.

### Q15: What was the exact role of AI in building Canister?
**Answer:** In accordance with Hackathon Rule 11 (AI use disclosure):
AI coding assistants (Google Antigravity / Gemini) were used as pair-programming tools for drafting repetitive boilerplate, creating initial unit test stubs, and formatting documentation. All architectural decisions (truth topology, precedence ranking, fail-closed contracts, filter/pin/backfill stabilization, and Cypher traversals) were conceived, implemented, benchmarked, and verified by the author. No LLM is used in the runtime decision loop.
