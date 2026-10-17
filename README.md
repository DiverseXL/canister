# Canister

**A temporal claim graph on FalkorDB that stops retired company facts from reaching an AI agent as present-tense context.**
Built for the FalkorDB "Graph Hacks: Context for AI Agents" hackathon, Track 3 (Company Brain).

Search finds what is *relevant*. It cannot tell what is still *true*. Canister puts a graph between the retriever and the model: BM25 proposes documents, FalkorDB decides which of them may still ground a current answer, and every decision ships with a record anyone can replay.

Between every arm of the experiment the model, the prompt, the corpus and the 10-document budget are identical. The only thing that changes is what the model is allowed to read.

## Results at a glance

Every number below is produced by a script in this repository on a **synthetic, seeded corpus** that we generate. See [Honesty: limitations](#honesty-limitations) before reading anything into them.

`evidence/run_manifest.json` records the commit the evidence came from, the FalkorDB image digest and a SHA-256 of every result file. It was generated at commit `a72b452`; every later commit touches documentation only. Recheck any checkout with `uv run python scripts/manifest.py --check`.

| Measurement | Baseline (BM25 only) | Canister |
|---|---|---|
| Superseded documents reaching present-tense context (18 conflict questions, deterministic) | **42** | **0** |
| Same count with the same number of documents removed *at random* | 27 | n/a |
| Historical questions that recover the retired evidence | n/a | **18 / 18** |
| Non-conflict contexts left byte-identical (safety envelope) | n/a | **32 / 32** |
| Documents removed or pinned outside the conflict set | n/a | **0** |
| Tenant isolation (two tenants, same claim key, different values) | n/a | **isolated** |
| Checks passing in `verify`, including a live FalkorDB restart | n/a | **9 / 9** |

No model is in the loop for any row above. They are all deterministic.

```
uv sync
docker compose up -d
uv run python corpus/generator.py      # seeded synthetic corpus + gold labels
uv run python scripts/index.py         # SQLite FTS5 index
uv run python scripts/seed.py          # extract, write the graph, canonize
uv run python scripts/verify.py        # 9 live checks incl. a database restart
uv run python scripts/controls.py      # every control below, written to evidence/controls.json
uv run python corpus/stress.py         # the stress set above, written to corpus/out/stress.json
uv run uvicorn canister_api.main:app   # API on :8000
npm --prefix apps/web install && npm --prefix apps/web run dev   # console on :3000 (or :3001)
```

## Table of contents

1. [The problem](#the-problem)
2. [What I built](#what-i-built)
3. [Architecture](#architecture)
4. [How a claim gets resolved](#how-a-claim-gets-resolved)
5. [How FalkorDB is used](#how-falkordb-is-used)
6. [Engineering decisions](#engineering-decisions)
7. [Measured results](#measured-results)
8. [Stress test: where it breaks](#stress-test-where-it-breaks)
9. [Use it as a component](#use-it-as-a-component)
10. [The console](#the-console)
11. [Honesty: limitations](#honesty-limitations)
12. [Tech stack](#tech-stack)
13. [Project layout](#project-layout)
14. [Run it locally](#run-it-locally)
15. [Tests](#tests)
16. [Attribution](#attribution)

## The problem

A company's knowledge is not a pile of facts. It is a pile of *claims with lifetimes*. A price is right on Monday, replaced on Wednesday, historically true on Friday, and harmful if an agent quotes it as current a month later.

Retrieval is built to maximise relevance, and that creates a specific failure. The retired document and the current document were written by the same people, about the same system, in the same vocabulary, so the retired one ranks just as well, and often better because it has had more time to be repeated. On our corpus, plain BM25 leaks **42 superseded documents into the top 10 across 18 conflict questions.** The agent then reads old truth as if it were new.

Canister treats "this used to be true" as a first-class state that sits next to relevance, so that retired truth stays visible as history and unreachable as present.

## What I built

A pipeline in which the graph decides what the model may read:

1. **Index.** Documents go into SQLite FTS5 for cheap global BM25 retrieval.
2. **Extract.** A deterministic extractor pulls claims from every document: entity, attribute, value, exact evidence span, stance (asserts, corroborates, supersedes) and whether the value came from a structured field or from prose.
3. **Canonize.** Each claim key is resolved in a fixed priority order (below), and the outcome is written to FalkorDB as an event. History is never overwritten.
4. **Gate.** At question time the top-10 BM25 candidates are mapped back to their claims. Each document is labelled, superseded ones are removed and replaced with the next candidates from the *same* ranking, and any current document the retriever missed is pinned in by evicting the lowest-ranked candidate. The context is always exactly 10 documents.
5. **Record.** Every decision returns a *grounding record*: the ranking that came in, the cut set with the reason for each cut, the context that went out, its SHA-256, and the Cypher query identifiers that decided it.

Every current-state answer is exactly one of `CANON`, `CONTESTED` or `UNKNOWN`. When evidence does not establish a winner, Canister shows the fork rather than inventing an order.

On the seeded demo corpus: 200 documents, 200 assertions, 40 claim keys, **38 CANON, 2 CONTESTED, 0 UNKNOWN**, 552 nodes and 538 relationships in the graph.

## Architecture

```
Entity --HAS_CLAIM--> ClaimKey --HAS_VALUE--> Proposition <--ASSERTS-- Assertion --IN_ARTIFACT--> Artifact
                                                   ^
                                                   | SELECTS
                                              CanonEvent --SUPERSEDES--> CanonEvent
```

| Node | Role |
|---|---|
| `Entity` | A real-world thing (a product, a team, a vendor). |
| `ClaimKey` | One mutable property of an entity, such as *Hooli / integration owner*. |
| `Proposition` | One possible value. Ten documents repeating the same value still make one node. |
| `Assertion` | One document asserting that value, with exact span, stance and source kind. |
| `Artifact` | The source document. Text itself lives in SQLite; the graph holds identity and relationships. |
| `CanonEvent` | The event that selects a value as current and may `SUPERSEDES` an earlier event. |

Document text lives in SQLite FTS5. The *truth topology* (what supersedes what, and which evidence may ground a present-tense answer) lives entirely in FalkorDB. Each tenant gets its own graph via `select_graph(tenant_id)`.

## How a claim gets resolved

Canonization runs in a fixed order, and the order is the whole point. It is enforced by unit tests.

1. **Explicit supersession.** Language such as "changed from X to Y" or "the old figure is retired". It is the only signal allowed to beat corroboration.
2. **Reliable temporal ordering.** Used only when metadata and semantics agree.
3. **Corroboration.** A tie-break and nothing more. Majority never overrides supersession. Test: eight documents asserting `$0.08` against one later document stating the price changed to `$0.06` must resolve to `$0.06`. This is re-proven live by every `verify` run.
4. **No signal.** The claim is `CONTESTED`. Canister never manufactures an ordering.

At question time, `ground()` maps the question to claim keys (entity must appear in the question and every token of the attribute label must be present), looks up the claim neighbourhood, labels each retrieved document, then filters, backfills and pins.

Document labels, in precedence order: `current`, `contested`, `historical`, `superseded`, `not_in_claim_graph`.

## How FalkorDB is used

Remove FalkorDB and the system loses the ability to decide current context. It is not a visualisation layer. Three traversals decide every answer:

```cypher
// Claim neighbourhood
MATCH (ck:ClaimKey {id: $ckid})-[:HAS_VALUE]->(p:Proposition)
RETURN p.value, p.status

// Supersession lineage
MATCH (ev:CanonEvent {id: $evid})-[:SUPERSEDES*1..10]->(old)-[:SELECTS]->(p)
RETURN p.value

// Residue: which documents still assert a retired value
MATCH (ck:ClaimKey {id: $ckid})-[:HAS_VALUE]->(p:Proposition)<-[:ASSERTS]-(a:Assertion)-[:IN_ARTIFACT]->(art:Artifact)
RETURN a.evidence_span, art.doc_id
```

Writes use parameterised `MERGE` with deterministic SHA-256 identifiers, so re-ingesting the corpus creates exactly zero new nodes.

Things learned the hard way, now built into the code:

- **Reversed arrows fail silently.** An early version of the assertion read had the `ASSERTS` arrow backwards and returned nothing. The integration test that round-trips a write now catches this.
- **Query timeouts.** Removing the `TIMEOUT_MAX` and `MAX_QUEUED_QUERIES` overrides from `docker-compose.yml` fixed spurious "Query timed out" errors.
- **Client edges.** `graph.delete()` errors on an empty key, so it is guarded with `list_graphs()`. Re-creating an index raises "already indexed", which `ensure_schema` tolerates.
- **Restart persistence** is verified, not assumed: `verify` restarts the container and compares node counts before and after (552 and 552).

## Engineering decisions

- **Structured state or nothing.** The graph returns states and typed records, never prose. That is what makes an honest `UNKNOWN` possible.
- **Fail closed.** If FalkorDB is unreachable, the API returns `503 TEMPORAL_GRAPH_UNAVAILABLE`. It never degrades to plain retrieval, because a silent fallback would reintroduce exactly the failure the system exists to prevent.
- **Exact document-count parity.** Every arm sees exactly 10 documents. Removing a superseded document backfills from the same ranking, and pinning a missed current document evicts the lowest-ranked candidate. This is asserted in code, not assumed.
- **Controls against our own result.** A random-removal arm, a cut-only arm and a pin-only arm exist specifically to attack the headline claim.
- **Claim-key matching is deliberately strict.** The first version matched on any token overlap and wrongly attached one unanswerable question to a claim. Requiring the entity plus the full attribute label removed that false match.
- **Sentence splitting must not break on decimals.** A naive splitter cut `$0.08` in half and corrupted values. The extractor now splits only on terminal punctuation followed by whitespace.
- **Never score an infrastructure failure as a wrong answer.** Any failed model or judge call is recorded as `error`, never as incorrect. Anything not run is recorded as `not_run`.
- **Original work, reproducible.** The corpus is generated from a fixed seed (1337), and `scripts/manifest.py` fingerprints the git commit, the FalkorDB image digest and the SHA-256 of every result file.

## Measured results

Corpus: 200 documents, 40 claim keys, 18 planted conflicts (index 0 is the 8-versus-1 majority case), 2 contested claims, 10 unanswerable questions, 50 questions in total. Seed 1337. All rows are deterministic.

### Does the graph remove the right documents?

| Arm | Superseded docs in context | Context size |
|---|---|---|
| Baseline (BM25 top 10) | 42 across 18 questions | 10 |
| Random removal (same count removed, seeded per question) | 27 | 10 |
| Temporal gate | 0 | 10 |

Random removal helps on 10 of the 18 conflict questions, and the gate helps on all 18. A random cut sometimes lands on a retired document by chance; the gate cuts the right one every time, because the graph tells it which one that is.

### Which half of the gate does the work?

| Arm | Superseded in context | Current gold in context | Context size |
|---|---|---|---|
| Baseline | 42 | 18 | 10 |
| Cut only | 0 | 18 | 10 |
| Pin only | 42 | 18 | 10 |
| Full gate | 0 | 18 | 10 |

Over the 18 conflict questions, every arm keeps all 18 current-gold documents and exactly 10 documents. Suppression is what stops retired evidence from reaching the model; pinning recovers current evidence the retriever ranked out. Source: `evidence/controls.json` (`mechanism_split.arms.*.superseded_in_context`, `mechanism_split.arms.*.current_gold_in_context`, `mechanism_split.arms.*.context_size_mean`).

### Stability across retrieval depth

Superseded documents reaching context, by retrieval depth. Both arms saw exactly `top-k` documents for every question at every depth.

| top-k | Baseline superseded in context | Temporal gate superseded in context |
|---|---|---|
| 5 | 39 | 0 |
| 10 | 42 | 0 |
| 20 | 42 | 0 |

The baseline leak rises from 39 at top-k 5 to 42 at top-k 10 and stays at 42 at top-k 20; the gate holds at 0 at every depth. Source: `evidence/controls.json` (`top_k_sweep."5"/"10"/"20".baseline.leak_total`, `top_k_sweep."5"/"10"/"20".temporal.leak_total`, `top_k_sweep."5"/"10"/"20".*.size_all_k`).

### Historical mode

For all 18 conflicts, asking in historical mode recovers the retired evidence (18 / 18) and the retired document is not cut (0 removed).

### Safety envelope

The deterministic gate runs over all 50 questions. Of the 32 non-conflict questions, **32 contexts are byte-identical** to plain retrieval. No expected document is removed outside the conflict set, and nothing is pinned outside it. The gate changes retrieval only where the graph can prove supersession.

### Tenant isolation

Two tenants hold different values for the same claim key (`omar haddad` and `zara sentinel`). `ground()` returns each tenant's own value and never the other's.

## Stress test: where it breaks

A separate set of 20 documents contains supersession phrased in ways the deterministic extractor was not designed to parse ("we have since retired the old figure", "as of last quarter this changed"). The extractor was not tuned to this set.

| Metric | Result |
|---|---|
| Value recall | 0.70 (14 / 20 recovered the new value) |
| Supersession recall | 0.00 (0 / 20 flagged a supersession) |
| Current-state recall | 0.00 (0 / 20 served the correct current value) |
| Resulting claim states | 14 CONTESTED, 6 CANON_stale |

What "6 stale" actually means, stated plainly:

- **6 of the 20 documents were served as `CANON` with a retired value** — false confidence. They are exactly the six whose new value was written loosely ("a fortnight", "sometime in Q3", "about three weeks") and from which the extractor recovered *nothing*: only the old value is in the graph, so canonization has nothing to contest and returns that retired value as current. Documents `stress-0015` through `stress-0020` (`selected_value` = `60d`, `2025-07-01`, `marcus webb`, `4h`, `14d`, `30d`, all equal to the retired `old_value`).
- **14 of the 20 were labelled `CONTESTED` and served no current value at all** (`stress-0001`–`stress-0014`). Here the new value *was* recovered, but the paraphrase carried no supersession marker, so the extractor labelled both values `assert` and canonization correctly refused to invent an order.

So the honest reading is not "it always fails safe". It is: **14 cases fail safe, 6 cases fail unsafe**. The unsafe six lose the new value entirely and then present the retired value as current — the exact failure this project exists to prevent. The extractor was not tuned to this set and these numbers are reported as they are. A model-assisted extractor is the obvious next step and is **not implemented** (`not_run`).

Source: `corpus/out/stress.json` (`results[].decision`, `results[].selected_value`, `results[].value_recovered`, `results[].outcome`, `summary.outcomes`).

**Next step (`not_run`).** Two changes would close this gap and neither is implemented: a fail-safe rule that marks a claim `CONTESTED` whenever a supersession cue is present but no new value was extracted, and a model-assisted extractor for loosely-phrased new values. Both are `not_run`; the deterministic extractor reported here is unchanged.

## Use it as a component

Put Canister between your retriever and your LLM.

```bash
curl -X POST localhost:8000/ground -H 'Content-Type: application/json' -d '{
  "question": "What is the current integration owner for Hooli?",
  "mode": "temporal",
  "tenant_id": "demo"
}'
```

Example response (abridged):

```json
{
  "grounding": "TEMPORAL_GRAPH",
  "decision": { "state": "CANON", "value": "omar haddad",
                "priority": 1, "reason": "explicit_supersession" },
  "final_size": 10,
  "cut": [ { "doc_id": "...", "reason": "superseded" } ],
  "sha256": "...",
  "query_ids": ["..."]
}
```

| Endpoint | Purpose |
|---|---|
| `POST /ground` | Ground a question. Modes: `current`, `historical`, `temporal`. |
| `GET /claims?tenant_id=` | List claim keys and their state. |
| `GET /grounding/{id}` | Replay a stored grounding record (`/receipt/{id}` is kept as an alias). |
| `GET /health` | Liveness. |

`receipt_id` identifies a stored grounding record; pass it to `GET /grounding/{id}` to replay the decision.

It fails closed: with FalkorDB down, `/ground` returns `503 TEMPORAL_GRAPH_UNAVAILABLE`.

### MCP

The same contract is exposed as MCP tools, `canister_ground` and `canister_claim`, with the same fail-closed behaviour. Client configuration:

```json
{
  "mcpServers": {
    "canister": {
      "command": "uv",
      "args": ["run", "canister-mcp"]
    }
  }
}
```

## The console

A Next.js app that reads the live API and `evidence/*.json`. No hardcoded figures and no mock data.

The console defaults to port 3000. Docker Compose also maps FalkorDB's browser to 3000, so when that port is busy Next.js serves the console on 3001 instead; the API's default `CANISTER_CORS_ORIGINS` allows both `localhost` and `127.0.0.1` on either port.

| Page | What it shows |
|---|---|
| `/` | Live headline numbers from the API |
| `/gate` | The same BM25 ranking shown twice: the retired sentence highlighted, the graph path that justifies removing it, and the baseline answer beside the gated one |
| `/truth` | Every claim key with its CANON / CONTESTED / UNKNOWN state |
| `/ask` | Ask in current or historical mode and see the evidence |
| `/results` | `controls.json` rendered as tables |

## Honesty: limitations

- **The corpus is synthetic.** We generated it with a fixed seed and planted the conflicts ourselves. Results of 0 leakage and 32/32 identical contexts are therefore close to guaranteed by construction. They demonstrate that the mechanism works as specified, not that it will perform at that level on real company data.
- **The extractor is deterministic and template-aware.** It matches the planted claims exactly on all 200 documents because it was validated against our own gold labels. The stress set above shows what happens on phrasing it was not built for.
- **When the extractor loses the new value, the system can be confidently wrong.** On the stress set, 6 of 20 documents had their new value expressed loosely and recovered as *nothing*; with only the retired value in the graph, canonization returned it as `CANON` current. That is false confidence, not a safe refusal, and it is a real limitation of a graph that only knows what the extractor gave it.
- **No model is in the loop.** Answer correctness here is derived from the decision state, not from a model-written answer. No model-judged results are reported, and none are claimed.
- **Question-to-claim matching is lexical.** It requires the entity and the whole attribute label. Embedding-based matching would scale better and is not implemented.
- **Retrieval is lexical BM25.** Semantic retrieval would change recall, not the temporal argument.
- **No resurrection handling.** There are no reliable timestamps, so a retired value reasserted later cannot be ordered against its supersession, and Canister does not claim to detect it.
- **Single-node FalkorDB.** Scale and concurrency were not tested.
- **`not_run`:** the fail-safe rule that marks a claim `CONTESTED` when a supersession cue is present but no new value was extracted, model-assisted extraction, model-judged answer scoring, and any deployment-scale benchmark.

## Tech stack

Python 3.12, uv workspace, FastAPI, pydantic v2, falkordb-py 1.8.0, SQLite FTS5, pytest, ruff, FalkorDB 4.22.1 (Redis 8.10.2) via Docker Compose, Next.js and Tailwind for the console.

## Project layout

```
packages/
  graph/        client, schema, ids, models, canonize, writer, grounding
  retrieval/    SQLite FTS5 store and BM25 candidates
  extraction/   vocab, normalisation, deterministic claim extractor
  evaluation/   corpus loader, context builder, metrics, arms
services/
  api/          FastAPI service (fail-closed)
  mcp/          MCP server exposing ground and claim lookup
apps/web/       Next.js console
corpus/         seeded generator and stress set; gold labels
scripts/        index, seed, benchmark, controls, envelope, verify, manifest
tests/          unit (no database) and integration (marked falkordb)
```

## Run it locally

Prerequisites: Docker, uv, Node 20+ with npm.

```bash
docker compose up -d                      # FalkorDB on :6379, browser on :3000
uv sync
uv run python corpus/generator.py         # seeded synthetic corpus + gold labels
uv run python scripts/index.py            # SQLite FTS5 index
uv run python scripts/seed.py             # extract claims, write the graph, canonize
uv run python scripts/verify.py           # 9 live checks, including a restart
uv run python scripts/controls.py         # all controls -> evidence/controls.json
uv run python corpus/stress.py            # stress set -> corpus/out/stress.json
uv run python scripts/envelope.py         # counts and environment
uv run python scripts/manifest.py         # fingerprint every artifact
uv run uvicorn canister_api.main:app      # API on :8000
npm --prefix apps/web install             # console deps (once)
npm --prefix apps/web run dev             # console on :3000 (or :3001)
```

`verify` checks: write and read, idempotent re-ingest, the 8-versus-1 majority adversarial case, supersession, contested, unknown, residue traversal, the grounding record, and persistence across a real container restart.

`.env.example` contains no required secrets. Nothing in this repository needs a paid service or an API key.

## Tests

```bash
uv run ruff check .
uv run python -m pytest -q                 # 51 tests
uv run python -m pytest -m "not falkordb"  # unit tests only, no database, no network
```

Coverage includes canonization priority order (including the majority case), identifier determinism, extraction against the full gold set, grounding label precedence, metric arithmetic, the API including the 503 path with FalkorDB stopped and the `/grounding/{id}` replay (plus its `/receipt/{id}` alias), MCP tool schemas, and write-restart-read round trips against a live graph.

## Attribution

Everything here is used under its own licence.

| Component | Licence |
|---|---|
| FalkorDB server | SSPLv1 |
| falkordb-py 1.8.0 | MIT |
| FastAPI, pydantic, pytest, ruff | MIT |
| uvicorn, httpx | BSD-3-Clause |
| SQLite (FTS5) | Public domain |
| uv | Apache-2.0 OR MIT |
| Python | PSF-2.0 |
| Next.js, React, Tailwind CSS | MIT |

All documents in the corpus are synthetic and generated by `corpus/generator.py`. All code in this repository was written during the hackathon window.

## License

MIT