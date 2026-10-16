.RECIPEPREFIX = >

PY = uv run python

.PHONY: help install fmt lint test test-unit test-integration up down api mcp web web-build corpus index seed verify benchmark envelope controls stress manifest clean

help:
> @echo "Canister targets:"
> @echo "  install           uv sync (dev deps included)"
> @echo "  fmt               ruff format"
> @echo "  lint              ruff check"
> @echo "  test              lint + unit + integration (integration needs FalkorDB)"
> @echo "  test-unit         pytest -m 'not falkordb' (no network, no API key)"
> @echo "  test-integration  pytest -m 'falkordb' (requires docker compose up)"
> @echo "  up / down         docker compose up -d / down"
> @echo "  api               run the FastAPI service"
> @echo "  mcp               run the MCP server (stdio)"
> @echo "  web               run the Next.js console (apps/web)"
> @echo "  web-build         install + build the console"
> @echo "  corpus            generate 200 docs + gold labels"
> @echo "  index             build the SQLite FTS5/BM25 index"
> @echo "  seed              extract + write graph + canonize"
> @echo "  verify            end-to-end verification suite"
> @echo "  benchmark         flat vs temporal arms over gold questions"
> @echo "  envelope          write the measured submission envelope"
> @echo "  controls          Task 8 controls -> evidence/controls.json"
> @echo "  stress            Task 9 paraphrased-supersession stress set"
> @echo "  manifest          git commit + FalkorDB digest + result hashes"
> @echo "  clean             remove generated artifacts"

install:
> uv sync

fmt:
> uv run ruff format .

lint:
> uv run ruff check .

test-unit:
> $(PY) -m pytest -m "not falkordb"

test-integration:
> $(PY) -m pytest -m "falkordb"

test: lint test-unit test-integration

up:
> docker compose up -d

down:
> docker compose down

api:
> uv run uvicorn canister_api.main:app --reload

mcp:
> uv run canister-mcp

web:
> npm --prefix apps/web run dev

web-build:
> npm --prefix apps/web install
> npm --prefix apps/web run build

corpus:
> $(PY) corpus/generator.py

index: corpus
> $(PY) scripts/index.py

seed: corpus
> $(PY) scripts/seed.py

verify: corpus index
> $(PY) scripts/verify.py

benchmark: index
> $(PY) scripts/benchmark.py

envelope: benchmark
> $(PY) scripts/envelope.py

controls: seed
> $(PY) scripts/controls.py

stress:
> $(PY) corpus/stress.py

manifest:
> $(PY) scripts/manifest.py

clean:
> -$(PY) -c "import shutil,os; [shutil.rmtree(p, ignore_errors=True) for p in ('corpus/out','var') if os.path.exists(p)]"
