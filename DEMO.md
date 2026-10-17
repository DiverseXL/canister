# Canister – 3-Minute Demo Recording Checklist

> **All commands run from the repository root.**

A minute-by-minute execution checklist for recording the hackathon demo video. Every command runs locally against live services; no mock data or slide-only claims.

---

## Pre-Flight Setup (T minus 5 minutes)

1. **Start FalkorDB:**
   ```bash
   docker compose up -d
   ```
2. **Start Backend API:**
   ```bash
   uv run uvicorn canister_api.main:app --port 8000
   ```
3. **Start Web Console:**
   ```bash
   npm --prefix apps/web run dev
   # Served on http://localhost:3000 (or http://localhost:3001 if port 3000 is occupied by FalkorDB browser)
   ```
4. **Arrange Screen Layout:**
   - Left half: Web Browser open to `http://localhost:3000` (or `3001`).
   - Right half: Terminal window with shell prompt ready in repo root.

---

## Recording Checklist (0:00 – 3:00)

| Timestamp | Phase | What to Do (Exact Commands / Clicks) | What Should Be on Screen | Narration & Key Takeaways |
|---|---|---|---|---|
| **0:00 – 0:20**<br>(20s) | **The Hook & Problem** | - Open browser to `/`<br>- Keep terminal visible | - Console home dashboard showing live metrics (552 nodes, 43 leaks under baseline, 0 under gate) | *"Search engines find what is relevant, not what is still true. In company wikis, outdated documents often rank higher than new ones because they share the same keywords. Canister places a temporal claim graph on FalkorDB between the retriever and the model to stop retired facts from grounding present-tense answers."* |
| **0:20 – 0:45**<br>(25s) | **End-to-End Verification** | In Terminal, run:<br>`uv run python scripts/verify.py --skip-restart` | Terminal output showing 9 checks passing:<br>`[PASS] write_read`<br>`[PASS] idempotent_reingest`<br>`[PASS] majority_adversarial`<br>`[PASS] supersession`<br>`[PASS] contested`<br>`[PASS] unknown`<br>`[PASS] residue_traversal`<br>`[PASS] ground_receipt` | *"The entire pipeline is verified live against FalkorDB. Point at `majority_adversarial`: nine documents assert the old price `$0.15`; one later document states the price changed to `$0.07`. Because explicit supersession beats corroboration in our canonizer, the single update wins every time. Re-ingest creates exactly 0 new nodes."* |
| **0:45 – 1:15**<br>(30s) | **The Temporal Gate (Live)** | - Switch to browser tab `/gate`<br>- Type in search box:<br>`What is the current starter plan price for Acme Corp?`<br>- Press Enter | - Split view comparing Baseline BM25 vs Temporal Gate.<br>- Left: Nine superseded documents highlighted.<br>- Right: Clean context with nine retired documents removed and replaced by backfill; decision shows `CANON $0.07`.<br>- Below: Grounding path showing `CanonEvent -> CANON (explicit_supersession)`. | *"Here is the Temporal Gate in action. Nine retired documents assert the old price; one later document explicitly says it changed. Majority vote would pick the old price. The graph picks the right one: nine retired documents are removed and the correct price is served with full graph provenance."* |
| **1:15 – 1:45**<br>(30s) | **Fail-Closed 503 Demonstration** | 1. In Terminal, stop FalkorDB:<br>`docker stop canister-falkordb`<br><br>2. Run query via curl:<br>`curl.exe -i -X POST http://localhost:8000/ground -H "Content-Type: application/json" --data-binary "@docs/demo-body.json"`<br><br>3. Restart FalkorDB:<br>`docker start canister-falkordb`<br><br>4. Verify health:<br>`curl.exe -s http://localhost:8000/health \| python -m json.tool` | 1. Docker stops the container.<br><br>2. HTTP response header and JSON:<br>`HTTP/1.1 503 Service Unavailable`<br>`{"detail":{"error":"TEMPORAL_GRAPH_UNAVAILABLE",...}}`<br><br>3. Container starts up.<br><br>4. JSON output:<br>`{"status":"ok","graph_reachable":true}` | *"Watch what happens when FalkorDB is stopped. The API immediately returns HTTP 503 TEMPORAL_GRAPH_UNAVAILABLE. It never falls back to un-gated retrieval, because silent degradation would leak the very hallucinations we exist to prevent. Once restarted, the service resumes instantly with full persistence."* |
| **1:45 – 2:10**<br>(25s) | **Historical Queries & Truth State** | - In browser, click `/ask`<br>- Select `Mode: Historical`<br>- Search: `What is the current starter plan price for Acme Corp?`<br>- Click `/truth` tab | - `/ask` displays the retired document restored in context.<br>- `/truth` displays table of all 40 claim keys (38 CANON, 2 CONTESTED). | *"History is never deleted. In historical mode, Canister selectively recovers the retired evidence for audit or retrospective analysis. On `/truth`, every claim key in the organization is tracked as CANON, CONTESTED, or UNKNOWN. When two documents conflict without a resolution cue, Canister marks it CONTESTED rather than guessing."* |
| **2:10 – 2:35**<br>(25s) | **Measured Results & Controls** | - In browser, navigate to `/results`<br>(or in Terminal: `uv run python scripts/controls.py`) | Tables rendered from `evidence/controls.json`:<br>- Baseline leak: 43 → 0<br>- Random removal: 26 (cuts help only when targeted)<br>- Safety envelope: 32/32 non-conflict contexts byte-identical to raw BM25 | *"Our measured controls prove the mechanism: random removal only cuts leaks to 26, whereas the graph reaches 0. Furthermore, across all 32 non-conflict questions in the corpus, 32 out of 32 contexts are byte-identical to plain retrieval. The gate touches context only where graph supersession is proven."* |
| **2:35 – 3:00**<br>(25s) | **Honesty, Stress & Manifest Close** | In Terminal, run:<br>`uv run python scripts/manifest.py --check` | Terminal output:<br>`checked 226 file(s): 226 match, 0 mismatch, 0 missing`<br>`commit: [commit_hash]` | *"We are honest about limits: on a 20-doc stress set with informal conversational slang, the deterministic extractor misses 6 unformatted values. Finally, `manifest.py` verifies all 226 artifacts against byte-exact SHA-256 hashes and the Docker image digest. FalkorDB provides the truth topology that makes corporate RAG safe."* |

---

## Emergency Fallbacks & Tips

- **If port 3000 is taken:** FalkorDB maps port 3000 inside Docker Compose; Next.js automatically switches to `http://localhost:3001`. The backend CORS policy accepts both.
- **To test curl without browser:**
  ```bash
  curl.exe -s http://localhost:8000/ground --data-binary "@docs/demo-body.json" -H "Content-Type: application/json" | python -m json.tool
  ```
- **Inspect grounding receipt:** Use `receipt_id` from any response to inspect the replayable decision at `http://localhost:8000/grounding/{receipt_id}`.
