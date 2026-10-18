"""Export real gate example from POST /ground to evidence/gate_example.json."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_BODY_PATH = REPO_ROOT / "docs" / "demo-body.json"
OUTPUT_PATH = REPO_ROOT / "evidence" / "gate_example.json"
API_BASE = "http://localhost:8000"


def check_health() -> tuple[bool, bool]:
    """Return (api_up, graph_reachable)."""
    try:
        req = urllib.request.Request(
            f"{API_BASE}/health", headers={"User-Agent": "canister-exporter"}
        )
        with urllib.request.urlopen(req, timeout=3) as res:
            if res.status == 200:
                data = json.loads(res.read().decode("utf-8"))
                return True, bool(data.get("graph_reachable", False))
    except Exception:
        pass
    return False, False


def get_git_commit() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True)
        return out.strip()
    except Exception as e:
        return f"unknown ({e})"


def main() -> None:
    api_started = False
    proc = None

    api_up, graph_reachable = check_health()
    if not api_up:
        print("API not running on http://localhost:8000; starting temporary uvicorn process...")
        proc = subprocess.Popen(
            ["uv", "run", "uvicorn", "canister_api.main:app", "--port", "8000"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        api_started = True
        for _ in range(30):
            time.sleep(0.5)
            api_up, graph_reachable = check_health()
            if api_up:
                break
        if not api_up:
            if proc:
                proc.terminate()
            sys.exit("Failed to start API on http://localhost:8000.")

    try:
        if not graph_reachable:
            sys.exit("FalkorDB is unreachable from the API. Please ensure FalkorDB is running.")

        if not DEMO_BODY_PATH.is_file():
            sys.exit(f"Demo body payload not found at {DEMO_BODY_PATH}")

        payload_bytes = DEMO_BODY_PATH.read_bytes()
        req = urllib.request.Request(
            f"{API_BASE}/ground",
            data=payload_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "canister-exporter"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as res:
            if res.status != 200:
                sys.exit(f"POST /ground returned status {res.status}")
            raw_text = res.read().decode("utf-8")
            resp_data = json.loads(raw_text)

        # Add top-level provenance fields
        resp_data["generated_at"] = datetime.now(UTC).isoformat()
        resp_data["git_commit"] = get_git_commit()
        resp_data["note"] = "synthetic corpus, seeded, no model in the loop"

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(resp_data, f, indent=2)
            f.write("\n")

        print(f"Successfully wrote gate example to {OUTPUT_PATH}")
    finally:
        if api_started and proc:
            print("Stopping temporary API process...")
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
