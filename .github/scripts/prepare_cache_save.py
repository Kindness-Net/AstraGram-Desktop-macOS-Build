"""Prune one cache family before saving; any failure disables the new upload."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess


def github_api(endpoint, *, paginate=False, method="GET"):
    command = ["gh", "api", "--method", method, endpoint]
    if paginate:
        command += ["--paginate", "--slurp"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        # Concurrent eviction can remove a cache between listing and deletion.
        if method == "DELETE" and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(f"GitHub cache API {method} failed: {result.stderr.strip()}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def cache_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def select_stale(caches, *, prefix, key, ref, started_at):
    if not prefix.endswith("-") or prefix.count("-") < 2:
        raise ValueError("A cache family including the architecture is required")
    if key == prefix or not key.startswith(prefix) or not ref.startswith("refs/"):
        raise ValueError("Invalid cache key or ref")
    family = [c for c in caches if c["ref"] == ref and c["key"].startswith(prefix)]
    if any(cache_time(c["created_at"]) > cache_time(started_at) for c in family):
        raise RuntimeError("A newer build has already saved this cache family")
    family.sort(key=lambda cache: cache_time(cache["created_at"]))
    return [c["id"] for c in family if c["key"] != key], any(
        c["key"] == key for c in family
    )


def prepare_save(*, repository, run_id, attempt, prefix, key, ref, paths, api=github_api):
    # Never delete the only remote copy if there is no local replacement.
    for path in paths:
        if not path.is_dir() or not any(path.iterdir()):
            raise ValueError(f"Missing or empty cache directory: {path}")
    if not paths:
        raise ValueError("At least one cache directory is required")
    run = api(f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}")
    # Snapshot all pages before deleting; deletion otherwise shifts pagination.
    pages = api(f"repos/{repository}/actions/caches?per_page=100", paginate=True)
    caches = [cache for page in pages for cache in page["actions_caches"]]
    stale, exists = select_stale(
        caches, prefix=prefix, key=key, ref=ref, started_at=run["run_started_at"]
    )
    for cache_id in stale:
        print(f"Deleting old cache {cache_id} ({ref}, {prefix})")
        api(f"repos/{repository}/actions/caches/{cache_id}", method="DELETE")
    return not exists


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    ready = False
    try:
        ready = prepare_save(
            repository=os.environ["GITHUB_REPOSITORY"],
            run_id=os.environ["GITHUB_RUN_ID"],
            attempt=os.environ["GITHUB_RUN_ATTEMPT"],
            ref=os.environ["GITHUB_REF"],
            prefix=args.prefix,
            key=args.key,
            paths=args.paths,
        )
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::warning::Cache upload skipped: {message}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"save={str(ready).lower()}\n")


if __name__ == "__main__":
    main()
