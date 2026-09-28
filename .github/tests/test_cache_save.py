import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_cache_save.py"
spec = importlib.util.spec_from_file_location("cache_save", SCRIPT)
cache_save = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache_save)
PREFIX = "win-libs-arm64-"
REF = "refs/heads/main"
STARTED = "2026-09-28T04:00:00Z"


def cache(identifier, key="old", ref=REF, created="2026-09-27T04:00:00.123Z", prefix=PREFIX):
    return {"id": identifier, "key": prefix + key, "ref": ref, "created_at": created}


class CacheSaveTests(unittest.TestCase):
    def select(self, items):
        return cache_save.select_stale(
            items, prefix=PREFIX, key=PREFIX + "current", ref=REF, started_at=STARTED
        )

    def test_preserves_other_branches_architectures_types_and_current_key(self):
        items = [cache(1), cache(2, ref="refs/heads/test"), cache(3, prefix="win-libs-x64-"),
                 cache(4, prefix="win-ccache-arm64-"), cache(5, key="current")]
        self.assertEqual(self.select(items), ([1], True))

    def test_empty_inventory_can_save(self):
        self.assertEqual(self.select([]), ([], False))

    def test_newer_run_blocks_pruning(self):
        with self.assertRaisesRegex(RuntimeError, "newer build"):
            self.select([cache(1), cache(2, created="2026-09-28T05:00:00Z")])

    def test_rejects_broad_prefix(self):
        with self.assertRaises(ValueError):
            cache_save.select_stale([], prefix="win-", key="win-current", ref=REF, started_at=STARTED)

    def test_rejects_key_outside_family(self):
        with self.assertRaises(ValueError):
            cache_save.select_stale([], prefix=PREFIX, key="wrong", ref=REF, started_at=STARTED)

    def prepare(self, api, path):
        return cache_save.prepare_save(
            repository="owner/repo", run_id="1", attempt="2", prefix=PREFIX,
            key=PREFIX + "current", ref=REF, paths=[path], api=api
        )

    def test_lists_all_pages_before_deleting(self):
        calls = []
        def api(endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            if "/attempts/" in endpoint:
                return {"run_started_at": STARTED}
            if kwargs.get("paginate"):
                return [{"actions_caches": [cache(1)]}, {"actions_caches": [cache(101)]}]
            return None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "object").write_text("data")
            self.assertTrue(self.prepare(api, path))
        self.assertEqual(calls[1][1], {"paginate": True})
        self.assertEqual([c[0].rsplit("/", 1)[-1] for c in calls[2:]], ["1", "101"])

    def test_exact_hit_cleans_old_generations_without_upload(self):
        deleted = []
        def api(endpoint, **kwargs):
            if "/attempts/" in endpoint:
                return {"run_started_at": STARTED}
            if kwargs.get("paginate"):
                return [{"actions_caches": [cache(1), cache(2, key="current")]}]
            deleted.append(endpoint.rsplit("/", 1)[-1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "object").write_text("data")
            self.assertFalse(self.prepare(api, path))
        self.assertEqual(deleted, ["1"])

    def test_listing_failure_never_deletes(self):
        deleted = []
        def api(endpoint, **kwargs):
            if "/attempts/" in endpoint:
                return {"run_started_at": STARTED}
            if kwargs.get("paginate"):
                raise RuntimeError("listing denied")
            deleted.append(endpoint)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "object").write_text("data")
            with self.assertRaisesRegex(RuntimeError, "listing denied"):
                self.prepare(api, path)
        self.assertEqual(deleted, [])

    def test_empty_local_payload_cannot_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(cache_save, "github_api") as api:
                with self.assertRaises(ValueError):
                    self.prepare(api, Path(directory))
                api.assert_not_called()

    def test_delete_failure_stops_update(self):
        def api(endpoint, **kwargs):
            if "/attempts/" in endpoint:
                return {"run_started_at": STARTED}
            if kwargs.get("paginate"):
                return [{"actions_caches": [cache(1)]}]
            raise RuntimeError("delete failed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "object").write_text("data")
            with self.assertRaisesRegex(RuntimeError, "delete failed"):
                self.prepare(api, path)

    def test_failure_writes_save_false(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            env = {"GITHUB_OUTPUT": str(output), "GITHUB_REPOSITORY": "owner/repo",
                   "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": REF}
            with patch.dict(os.environ, env), patch.object(sys, "argv", [
                str(SCRIPT), "--prefix", PREFIX, "--key", PREFIX + "current", directory
            ]), patch.object(cache_save, "prepare_save", side_effect=RuntimeError("API failed")):
                cache_save.main()
            self.assertEqual(output.read_text(), "save=false\n")

    def test_only_delete_404_is_ignored(self):
        with patch.object(cache_save.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "gh: Not Found (HTTP 404)"
            self.assertIsNone(cache_save.github_api("endpoint", method="DELETE"))
            with self.assertRaises(RuntimeError):
                cache_save.github_api("endpoint")


if __name__ == "__main__":
    unittest.main()
