# Canister — 3-minute demo script

Everything below actually runs. No slide-only claims. Have `docker compose up -d`
and (optionally) `make api` and `make web` already started before you begin.

---

### 0:00 — Hook (20s)

> "An AI agent reading a company wiki will happily cite a price that was retired
> last quarter. Canister puts a temporal claim graph in front of the model and
> makes the retired fact un-groundable — without deleting it."

### 0:20 — It runs end to end (15s)

```sh
make verify
```

Point at: **9 passed, 0 failed, 0 not_run** — including `restart_persistence`
(graph survives a real `docker restart`) and `idempotent_reingest` (0 new nodes).

### 0:35 — The failure, measured (25s)

```sh
make benchmark
```

Point at: **superseded_leak_total 42 → 0** and **questions 18 → 0**, while
`context_size_mean` stays `10.0` and `current_recall_mean` stays `1.0`. Same BM25,
same 10-doc budget; only the context topology changed.

### 1:00 — The Temporal Cut, visually (30s)

Open the console at `/cut`, type:

> `What is the current integration owner for Hooli?`

Point at: the same ranking shown twice; the retired `doc-####` struck through on the
left and gone on the right; **baseline answer `doc-####` [superseded]** next to
**temporal answer `omar haddad`**; and the `CanonEvent → CANON (explicit_supersession)`
path that justifies the cut.

### 1:30 — Controls (35s)

```sh
make controls
```

Point at, in order:

- **random-removal**: baseline 42, random 27, temporal 0 — removing *the superseded*
  docs is the mechanism, not removing any docs.
- **mechanism split**: cut-only already reaches 0; pin-only stays at 42 — so cutting
  removes the leak and pinning only holds the budget at 10.
- **safety envelope**: 32/32 non-conflict contexts byte-identical to flat, 0 removed
  outside conflicts, 0 pins outside conflicts — the graph touches only conflicts.

Then open `/results` to show the same tables rendered straight from `var/controls.json`.

### 2:05 — History is not deleted (25s)

Open `/ask`, ask the same question, and point at **Current** (`omar haddad`) beside
**Historical** (the retired evidence recovered in context). Mention the isolation
check: two tenants with different `Hooli` owners return only their own value.

### 2:30 — Honest about what fails (20s)

```sh
make stress
```

Point at: **value recall 0.70, supersession recall 0.00, current recall 0.00** on 20
paraphrased documents ("we have since retired the old figure"). The extractor was not
tuned to them; the misses are in the README **Limitations** section.

### 2:50 — Close (10s)

```sh
make manifest
```

> "One command records the git commit, the FalkorDB image digest and a SHA-256 of
> every result file. BM25 ranks what is relevant; FalkorDB decides what is still
> allowed to ground an answer."

---

## Fallbacks

- If the browser is unavailable, `curl -s localhost:8000/ground -H 'content-type: application/json' -d '{"question":"What is the current integration owner for Hooli?","mode":"current"}'` shows the receipt, `sha256` and Cypher ids.
- If FalkorDB is down, the same call returns `503 TEMPORAL_GRAPH_UNAVAILABLE` — that
  is the fail-closed behavior, and it is worth showing rather than hiding.
