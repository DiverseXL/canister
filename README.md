# Canister

A temporal claim graph on FalkorDB that keeps superseded company facts out of an
AI agent's context.

**Track 3 — Company Brain.** Built for *Graph Hacks: Context for AI Agents* (FalkorDB).

## Thesis

BM25 decides what is *relevant*. FalkorDB decides what is still *allowed to ground
the answer*. Superseded claims stay answerable as history, but never reach the model
as present-tense context. Same model, same prompt, same corpus, same 10-document
budget — only the context topology changes. On our synthetic corpus that moves
superseded-in-context from **42 to 0** while every other metric holds.

## Architecture

```
 documents ──► extractor ──► Assertions ──► FalkorDB temporal claim graph
 (deterministic)                              Entity ──HAS_CLAIM──► ClaimKey
                                              ClaimKey ──HAS_VALUE──► Proposition
                                              Assertion ──ASSERTS──► Proposition
                                              Assertion ──IN_ARTIFACT──► Artifact
                                              CanonEvent ──SELECTS──► Proposition
                                              CanonEvent ──SUPERSEDES──► CanonEvent
                                                     │
 question ──► BM25 (SQLite FTS5) ──► candidates ─────┤
                                    graph labels,    │
                                    filter + backfill┤──► ground(): 10-doc context + receipt
                                    + pin            │
                                                     ▼
                     FastAPI /ground · MCP canister_ground · Next.js console
```

## How it works

1. **Extract** — a deterministic extractor turns company documents into assertions
   with exact evidence spans, a stance marker (`assert` / `supersede` / `corroborate`)
   and a structured-vs-prose flag.
2. **Store** — assertions, propositions, claim keys and artifacts are written to a
   FalkorDB graph with deterministic ids and idempotent `MERGE`s. Re-ingesting the
   same corpus adds zero nodes.
3. **Canonize** — a fixed-priority resolver decides, per claim key, exactly one of
   `CANON`, `CONTESTED` or `UNKNOWN`, and records a `CanonEvent` that `SUPERSEDES`
   the previous one. History is never overwritten.
4. **Ground** — BM25 proposes candidates; the graph labels each one `current`,
   `superseded`, `historical`, `contested` or `not_in_claim_graph`, filters
   superseded, backfills from the same ranking, pins any missed current evidence by
   **evicting** the lowest-ranked candidate (never an 11th slot), and returns a
   receipt with a `sha256` of the final context and the Cypher query identifiers used.

### Canonization priority (enforced by tests)

1. Explicit supersession language beats everything.
2. Reliable temporal ordering, only when metadata and semantics agree.
3. Corroboration is a tie-break only. Majority never overrides supersession.
4. No signal → `CONTESTED`. Never invent an ordering.

Every current-state answer is exactly `CANON`, `CONTESTED` or `UNKNOWN`.

### Fail closed

If FalkorDB is unreachable the API returns **503 `TEMPORAL_GRAPH_UNAVAILABLE`** and
the MCP tools error. Neither ever silently falls back to plain retrieval.

## How to run (4 commands)

```sh
uv sync
docker compose up -d
make corpus index seed
make verify
```

Then, optionally: `make controls`, `make benchmark`, `make stress`, `make envelope`,
`make manifest`, `make api` (FastAPI), `make mcp` (MCP server), `make web` (console).

`make test` runs ruff plus unit tests (no network, no API key) and integration tests
(marker `falkordb`, needs `docker compose up -d`).

## Measured results

The corpus is **synthetic and seeded** (`corpus/generator.py`, seed 1337): 200
documents, 40 claim keys, 18 conflicts (one 8-vs-1 majority-adversarial), 2 contested
and 10 unanswerable questions. Every metric below is **deterministic** — no model is
called, and nothing is compared to any other project's numbers. Regenerate with
`make benchmark controls stress`; the raw JSON is written to `var/` and
`corpus/out/stress.json`.

### Flat vs temporal (50 questions)

| metric | flat | temporal |
| --- | ---: | ---: |
| superseded-in-context (total) | 42 | 0 |
| questions with a leak | 18 | 0 |
| context size (mean) | 10.0 | 10.0 |
| every arm exactly 10 docs | true | true |
| current recall (mean) | 1.0 | 1.0 |
| answer correct rate | 1.0 | 1.0 |

### a) Random-removal control (18 conflicts)

Removes the same number of documents the temporal arm removes, chosen uniformly at
random from the baseline, backfilled from the same ranking.

| arm | superseded-in-context |
| --- | ---: |
| baseline | 42 |
| random removal (seeded per question) | 27 |
| temporal (graph) | 0 |

Random removal helps on 10/18 conflicts; the temporal arm helps on 18/18. Removing
*the superseded* documents, not merely removing documents, is the mechanism.

### b) Mechanism split (over conflict questions)

| arm | superseded in context | current gold in context | size mean | all 10 |
| --- | ---: | ---: | ---: | --- |
| baseline | 42 | 18 | 10.0 | true |
| cut-only | 0 | 18 | 10.0 | true |
| pin-only | 42 | 18 | 10.0 | true |
| full | 0 | 18 | 10.0 | true |

Cutting does the leak work; pinning keeps the budget fixed at 10 in every arm.

### c) top-k sweep (baseline vs temporal leak)

| k | baseline leak | temporal leak |
| ---: | ---: | ---: |
| 5 | 39 | 0 |
| 10 | 42 | 0 |
| 20 | 42 | 0 |

### d) Historical mode

| metric | value |
| --- | ---: |
| conflicts | 18 |
| all recover retired evidence | true |
| any retired doc cut | false |

### e) Safety envelope (all 50 questions)

| metric | value |
| --- | ---: |
| non-conflict questions | 32 |
| non-conflict byte-identical to flat | 32 |
| docs removed outside conflicts | 0 |
| pins outside conflicts | 0 |

Every intervention is one of the 18 conflicts, and each is justified by an
explicit-supersession `CanonEvent`. The full per-question list is in
`var/controls.json` (`safety_envelope.interventions`).

### f) Tenant isolation

Two tenants share a claim key with different values (`Hooli` integration owner):

| tenant | value |
| --- | --- |
| A | `omar haddad` |
| B | `zara sentinel` |

`ground()` returns each tenant only its own canonical value.

### Stress set (paraphrased supersession)

20 documents that express supersession with paraphrases the extractor is not
designed to parse ("we have since retired the old figure"):

| metric | value |
| --- | ---: |
| documents | 20 |
| current value recovered by the extractor | 14/20 (0.70) |
| supersession flagged | 0/20 (0.00) |
| pipeline returns the current value | 0/20 (0.00) |

Outcomes: 14 `CONTESTED`, 6 stale. Reported as-is; the extractor was **not** tuned
to the stress set.

## Interfaces

- **HTTP** (`make api`): `POST /ground` (`mode` = `current` | `historical` |
  `temporal`), `GET /claims?tenant_id=`, `GET /receipt/{id}`, `GET /health`. Every
  response carries a `sha256` and the Cypher query identifiers used.
- **MCP** (`make mcp`): tools `canister_ground` and `canister_claim` over stdio, same
  fail-closed behavior. Client config:

  ```json
  {
    "mcpServers": {
      "canister": {
        "command": "uv",
        "args": ["run", "--project", "/abs/path/to/canister", "canister-mcp"],
        "env": {
          "CANISTER_DEFAULT_TENANT": "demo",
          "CANISTER_INDEX_PATH": "var/index.sqlite3",
          "FALKORDB_HOST": "127.0.0.1",
          "FALKORDB_PORT": "6379"
        }
      }
    }
  }
  ```

- **Console** (`make web`, `apps/web`): `/` overview, `/cut` the Temporal Cut,
  `/truth` claim states, `/ask` current vs historical, `/results` the control tables.
  Every number is read live from the API or from `var/*.json`; no hardcoded figures.

## Layout

```
packages/graph/        client, schema, ids, writer, canonize, grounding
packages/retrieval/    SQLite FTS5 store and BM25 candidates
packages/extraction/   deterministic claim extraction
packages/evaluation/   arms, context builder, metrics
services/api/          FastAPI
services/mcp/          MCP server (canister_ground, canister_claim)
apps/web/              Next.js + Tailwind console
scripts/               index, seed, verify, benchmark, envelope, controls, manifest
corpus/                generator (gold corpus) and stress set
tests/                 unit (no db) and integration (marked falkordb)
```

## Graph schema

```
(Entity)-[:HAS_CLAIM]->(ClaimKey)-[:HAS_VALUE]->(Proposition)
(Assertion)-[:ASSERTS]->(Proposition)
(Assertion)-[:IN_ARTIFACT]->(Artifact)
(CanonEvent)-[:SELECTS]->(Proposition)
(CanonEvent)-[:SUPERSEDES]->(CanonEvent)
```

Ids are deterministic. History is never overwritten. Re-ingest creates 0 new nodes.

## Reproducibility

- The corpus is generated with a fixed seed and the gold labels are written to
  `corpus/out/gold.json`.
- Every published number is measured by a script under `scripts/`. Anything not run
  is recorded as `not_run`, never simulated.
- `make manifest` writes `var/run_manifest.json` with the git commit, the FalkorDB
  image digest and the SHA-256 of every result file.

## Limitations

- **Synthetic corpus.** The 200-document corpus is generated with a fixed seed
  (`corpus/generator.py`); it is not real company data.
- **Deterministic extractor.** Extraction is regex/ontology based, with no model and
  no network. It recognizes a fixed set of entities, attributes and value shapes.
- **Paraphrased supersession is missed.** On the 20-document stress set, the
  extractor recovers the current value in 14/20 documents, flags supersession in
  0/20, and the pipeline returns the current value in 0/20 (14 `CONTESTED`, 6 stale).
- **Single-value answers.** A document that states two values with no supersession
  marker canonizes to `CONTESTED` by design rather than guessing.
- **Model-judged metrics: none.** Every reported metric is deterministic. No model is
  called, so nothing is labelled model-judged.
- **not_run.** Results only exist after the corresponding script runs; missing files
  are surfaced as `not_run` rather than fabricated (see `var/run_manifest.json`).

## Attribution

Canister builds on the following dependencies. Licenses are listed as published by
each project; see the linked projects for the authoritative text.

| Dependency | Role | License |
| --- | --- | --- |
| [FalkorDB](https://github.com/FalkorDB/FalkorDB) | Graph engine; stores the temporal claim graph | SSPLv1 |
| [falkordb-py](https://github.com/FalkorDB/falkordb-py) | Official Python client | MIT |
| [FastAPI](https://github.com/fastapi/fastapi) | HTTP API | MIT |
| [pydantic](https://github.com/pydantic/pydantic) | Request/response models | MIT |
| [uvicorn](https://github.com/encode/uvicorn) | ASGI server | BSD-3-Clause |
| [httpx](https://github.com/encode/httpx) | Test HTTP client | BSD-3-Clause |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Model Context Protocol server | MIT |
| [Next.js](https://github.com/vercel/next.js) | Console framework | MIT |
| [React](https://github.com/facebook/react) | Console UI | MIT |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | Console styling | MIT |
| [TypeScript](https://github.com/microsoft/TypeScript) | Console types | Apache-2.0 |
| [Node.js](https://github.com/nodejs/node) | Console runtime | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | Test runner | MIT |
| [ruff](https://github.com/astral-sh/ruff) | Linter and formatter | MIT |
| [SQLite / FTS5](https://sqlite.org/) | BM25 candidate retrieval | Public domain |
| [uv](https://github.com/astral-sh/uv) | Workspace and dependency manager | Apache-2.0 OR MIT |
| [Python](https://www.python.org/) | Runtime | PSF-2.0 |

All code, copy and assets in this repository are original.
