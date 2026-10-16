# Canister

A temporal claim graph on FalkorDB that keeps superseded company facts out of an
AI agent's context.

**Track 3 — Company Brain.** Built for *Graph Hacks: Context for AI Agents* (FalkorDB).

## Thesis

BM25 decides what is *relevant*. FalkorDB decides what is still *allowed to ground
the answer*. Superseded claims stay answerable as history, but never reach the model
as present-tense context. Same model, same prompt, same corpus, same 10-document
budget — only the context topology changes.

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
   superseded, backfills from the same ranking, pins any missed current evidence,
   and returns a receipt with a `sha256` of the final context.

### Canonization priority (enforced by tests)

1. Explicit supersession language beats everything.
2. Reliable temporal ordering, only when metadata and semantics agree.
3. Corroboration is a tie-break only. Majority never overrides supersession.
4. No signal → `CONTESTED`. Never invent an ordering.

Every current-state answer is exactly `CANON`, `CONTESTED` or `UNKNOWN`.

### Fail closed

If FalkorDB is unreachable, the API returns **503 `TEMPORAL_GRAPH_UNAVAILABLE`**.
It never silently falls back to plain retrieval.

## Quickstart

```sh
uv sync
docker compose up -d
make corpus index seed
make verify
```

`make test` runs ruff plus unit tests (no network, no API key) and integration
tests (marker `falkordb`, needs `docker compose up -d`).

Run the API with `make api`, then:

```sh
curl -s localhost:8000/ground \
  -H 'content-type: application/json' \
  -d '{"question":"What is the current integration owner for Hooli?","mode":"temporal"}' \
  | jq .sha256
```

If FalkorDB is down the same request returns `503 TEMPORAL_GRAPH_UNAVAILABLE`.

## Layout

```
packages/graph/        client, schema, ids, writer, canonize, grounding
packages/retrieval/    SQLite FTS5 store and BM25 candidates
packages/extraction/   deterministic claim extraction
packages/evaluation/   arms, context builder, metrics
services/api/          FastAPI
scripts/               index, seed, verify, benchmark, envelope
corpus/                generator for synthetic company docs
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
| [pytest](https://github.com/pytest-dev/pytest) | Test runner | MIT |
| [ruff](https://github.com/astral-sh/ruff) | Linter and formatter | MIT |
| [SQLite / FTS5](https://sqlite.org/) | BM25 candidate retrieval | Public domain |
| [uv](https://github.com/astral-sh/uv) | Workspace and dependency manager | Apache-2.0 OR MIT |
| [Python](https://www.python.org/) | Runtime | PSF-2.0 |

All code, copy and assets in this repository are original.
