# Deploying Canister

Canister runs as a single FastAPI web service. The API is stateless; the
temporal claim graph lives in a FalkorDB instance the service talks to over the
network. This guide deploys the service to [Render](https://render.com) and the
graph to [FalkorDB Cloud](https://www.falkordb.com/), both on their free tiers.

The repository ships a Render Blueprint (`render.yaml`) so the build and start
commands are checked in rather than clicked together in a dashboard.

```
Render (web service)  --FALKORDB_*-->  FalkorDB Cloud (one graph per tenant)
  uvicorn canister_api.main:app
```

## Prerequisites

- A GitHub account with this repository forked or pushed to it.
- A [Render](https://render.com) account (free).
- A [FalkorDB Cloud](https://www.falkordb.com/) account (free instance).
- Locally, for the one-off seed step: Docker is **not** needed, but `uv` is, and
  the FALKORDB_* variables must point at the cloud instance.

## Step 1 - Create the FalkorDB Cloud instance

1. Sign in to FalkorDB Cloud and create a **free** instance.
2. Copy its connection details: host, port, username and password.
3. Do not configure TLS. The client connects in plaintext; the free Cloud
   endpoint is reachable without it.

## Step 2 - Apply the Render Blueprint

1. In Render, choose **New > Blueprint**, connect this repository, and let it
   read `render.yaml`.
2. Render creates one free Python web service named `canister`.

The Blueprint fixes these commands:

| Setting | Value |
|---|---|
| Build command | `pip install uv` then `uv sync`, then `uv run python corpus/generator.py` and `uv run python scripts/index.py` |
| Start command | `uv run uvicorn canister_api.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Plan | free |

`corpus/generator.py` writes the seeded synthetic corpus to `corpus/out/` and
`scripts/index.py` builds the SQLite FTS5 index at `var/index.sqlite3`. Both are
regenerated on every deploy; they are cheap and deterministic.

## Step 3 - Set the environment variables

Render prompts for the variables marked `sync: false` in `render.yaml`. Fill
them in the dashboard:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `PYTHON_VERSION` | yes | `3.12` | pinned in the Blueprint |
| `FALKORDB_HOST` | yes | `127.0.0.1` | FalkorDB Cloud host; `sync: false` |
| `FALKORDB_PORT` | yes | `6379` | FalkorDB Cloud port |
| `FALKORDB_USERNAME` | no | *(none)* | Cloud username; `sync: false` |
| `FALKORDB_PASSWORD` | yes | *(none)* | **secret**; `sync: false`, never logged by the app |
| `CANISTER_CORS_ORIGINS` | no | `http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001` | comma-separated browser origins; `sync: false` |
| `CANISTER_DEFAULT_TENANT` | no | `demo` | tenant used when a request omits `tenant_id` |
| `CANISTER_INDEX_PATH` | no | `var/index.sqlite3` | built during deploy |

`FALKORDB_PASSWORD` is marked `sync: false` so it is never written to the
repository. It is scrubbed from every error message the client raises, so it
cannot leak through a `503` detail, the `/health` payload, or logs.

## Step 4 - Seed the graph once

The service reads the graph but never creates the demo data. Seed it once,
pointing the FALKORDB_* variables at the **cloud** instance:

```bash
export FALKORDB_HOST=<cloud-host>
export FALKORDB_PORT=<cloud-port>
export FALKORDB_USERNAME=<cloud-user>
export FALKORDB_PASSWORD=<cloud-password>

uv sync
uv run python corpus/generator.py
uv run python scripts/seed.py --allow-remote
```

`--allow-remote` is required: `scripts/seed.py` drops and rewrites the tenant
graph, so it refuses a non-local host unless you opt in explicitly. Re-running
it is idempotent (the graph's writes are deterministic `MERGE`s), so a second
`seed.py --allow-remote` creates zero new nodes.

## Step 5 - Verify the deployment

Open `https://<service>.onrender.com/health`. A healthy response is:

```json
{"status": "ok", "graph_reachable": true, "detail": "ok"}
```

If the graph is unreachable the service still returns `200` but reports
`"status": "degraded"` and `"graph_reachable": false`. `/ground` then fails
closed with `503 TEMPORAL_GRAPH_UNAVAILABLE`; it never falls back to plain
retrieval.

Smoke-test a grounded question:

```bash
curl.exe -X POST https://<service>.onrender.com/ground \
  -H "Content-Type: application/json" \
  --data-binary "@docs/demo-body.json"
```

## Free-tier limits

- **FalkorDB Cloud (free).** The free instance **stops after 1 day without use**.
  It resumes when a new connection arrives, which can take a moment. Until it
  answers, `/health` reports `degraded` and `/ground` returns `503`. Ping it (or
  ask a question) periodically if you need it warm.
- **Render (free web service).** The service **sleeps after 15 minutes without
  traffic**. The next request triggers a cold start and takes noticeably longer
  (tens of seconds). The `/health` health check keeps it awake only while it is
  running, not across a sleep.
- The Render free plan has an ephemeral filesystem: `var/index.sqlite3` and
  `corpus/out/` are rebuilt by the build command on every deploy or restart.

## Warning: never run verify or controls against the remote

**Do not run `scripts/verify.py` or `scripts/controls.py` against the hosted
instance or the cloud graph.**

- `scripts/verify.py` drops and rewrites its own tenant graphs and, in its
  restart check, drives **the local Docker container**. Against a remote graph
  the restart check is meaningless and the drop/write is destructive.
- `scripts/controls.py` drops and rewrites tenant graphs and measures
  behaviour. It is a local, deterministic experiment, not a production tool.

Both scripts now refuse to run when `FALKORDB_HOST` is anything other than
`localhost`, `127.0.0.1` or `::1`, unless `--allow-remote` is passed. Do not
pass `--allow-remote` for these two scripts. The same guard protects
`scripts/perf.py`, `scripts/seed.py`, `scripts/benchmark_seed.py` and
`scripts/benchmark_controls.py`.

These scripts write to `evidence/`, which is committed measurement output.
Running them against the remote would rewrite local evidence and could corrupt
hosted data.

## Local verification of this Blueprint

The build and start commands were verified locally:

1. The repository was copied to a temporary directory (no `.git`, no `.venv`).
2. `uv sync`, `uv run python corpus/generator.py` and
   `uv run python scripts/index.py` all completed (offline, from the uv cache).
3. `uv run uvicorn canister_api.main:app --host 0.0.0.0 --port 8002` started
   with the FALKORDB_* variables pointed at the local container and
   `GET /health` returned
   `{"status":"ok","graph_reachable":true,"detail":"ok"}`.

No graph was written during verification: `/health` only issues a read-only
`PING`.
