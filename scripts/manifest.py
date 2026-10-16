"""Write evidence/run_manifest.json: git commit, FalkorDB image digest, result hashes.

Everything is best-effort and honest: if git, Docker or a result file is absent
the field is recorded as ``not_run`` instead of guessed.

Run: ``uv run python scripts/manifest.py``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

CONTAINER = "canister-falkordb"


def sha256_file(path: Path) -> str:
    # Hash raw bytes exactly as stored on disk, so a hash computed on one machine
    # matches the same file in a fresh clone (no newline normalisation).
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "not_run"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, result.stdout.strip()


def git_info() -> dict:
    ok, commit = _run(["git", "rev-parse", "HEAD"])
    if not ok:
        return {"commit": "not_run", "dirty": "not_run", "branch": "not_run"}
    _, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    _, status = _run(["git", "status", "--porcelain"])
    return {"commit": commit, "dirty": bool(status), "branch": branch}


def falkordb_info() -> dict:
    info: dict = {
        "container": CONTAINER,
        "image": "not_run",
        "image_id": "not_run",
        "repo_digests": "not_run",
    }
    ok, image = _run(["docker", "inspect", "--format", "{{.Config.Image}}", CONTAINER])
    if not ok:
        return info
    info["image"] = image
    _, image_id = _run(["docker", "inspect", "--format", "{{.Image}}", CONTAINER])
    info["image_id"] = image_id
    _, digests = _run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image])
    info["repo_digests"] = digests

    # Server-reported module version, if reachable.
    try:
        from canister_graph import build_client

        db = build_client()
        modules = db.connection.execute_command("MODULE", "LIST")
        for module in modules:
            fields = {str(k).lower(): v for k, v in zip(module[0::2], module[1::2], strict=False)}
            if fields.get("name") == "graph":
                info["server_graph_module"] = str(fields.get("ver"))
        info["server_redis_version"] = db.connection.info("server").get("redis_version")
    except Exception as exc:  # pragma: no cover - depends on environment
        info["server"] = f"not_run: {exc}"
    return info


def result_files(root: Path) -> dict[str, str]:
    targets: list[Path] = []
    for pattern in (
        # SQLite indexes are excluded: their bytes are not reproducible run to run.
        "evidence/*.json",
        "corpus/out/gold.json",
        "corpus/out/stress.json",
        "corpus/out/documents/*.md",
        "corpus/out/stress/*.md",
    ):
        targets.extend(sorted(root.glob(pattern)))
    hashes: dict[str, str] = {}
    for path in targets:
        if path.is_file():
            hashes[str(path.relative_to(root)).replace("\\", "/")] = sha256_file(path)
    return hashes


def check(out: Path) -> int:
    """Re-hash every file listed in ``out`` and report any mismatch."""
    if not out.is_file():
        print(f"{out} not found; run 'scripts/manifest.py' first")
        return 1
    data = json.loads(out.read_text(encoding="utf-8"))
    expected: dict[str, str] = data.get("results", {})
    recorded = data.get("git", {}).get("commit", "not_run")
    root = Path.cwd()
    matches = 0
    mismatches: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for rel, want in sorted(expected.items()):
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        got = sha256_file(path)
        if got == want:
            matches += 1
        else:
            mismatches.append((rel, want, got))
    print(f"manifest commit: {recorded}")
    print(
        f"checked {len(expected)} file(s): "
        f"{matches} match, {len(mismatches)} mismatch, {len(missing)} missing"
    )
    for rel, want, got in mismatches:
        print(f"  MISMATCH {rel}")
        print(f"    manifest {want}")
        print(f"    on disk  {got}")
    for rel in missing:
        print(f"  MISSING  {rel}")
    return 1 if (mismatches or missing) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the run manifest.")
    parser.add_argument("--out", type=Path, default=Path("evidence/run_manifest.json"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-hash every file listed in the manifest and report mismatches",
    )
    args = parser.parse_args()

    if args.check:
        return check(args.out)

    root = Path.cwd()
    results = result_files(root)
    # Never hash the manifest's own output; it changes on every run.
    try:
        self_key = str(args.out.resolve().relative_to(root.resolve())).replace("\\", "/")
        results.pop(self_key, None)
    except ValueError:
        pass
    missing = (
        [] if results else ["no result files found; run make corpus index seed benchmark controls"]
    )

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": git_info(),
        "docker": falkordb_info(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "results": results,
        "result_file_count": len(results),
        "missing": missing,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
