import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = (Path(__file__).resolve().parents[1] / "workflows/build.yml").read_text()
SOURCE_SHA = "498022da709c485a1b00b996bde5203909c9fc89"


def step(name):
    return WORKFLOW.split(f"      - name: {name}\n", 1)[1].split(
        "\n      - name:", 1
    )[0]


class StandaloneSourceTests(unittest.TestCase):
    def run_validation(self, **overrides):
        script = textwrap.dedent(
            step("Validate standalone source.").split("        run: |\n", 1)[1]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "bin"
            binary.mkdir()
            commands = {
                "git": 'test "$*" = "rev-parse HEAD" || exit 2\nprintf "%s\\n" "$TEST_HEAD"\n',
                "gh": (
                    'test "$1" = "api" || exit 2\n'
                    'test "$2" = "repos/Kindness-Kismet/AstraGram-Desktop/compare/${SOURCE_SHA}...main" || exit 2\n'
                    'test "$3" = "--jq" && test "$4" = ".status" || exit 2\n'
                    'printf "%s\\n" "$TEST_COMPARE_STATUS"\n'
                    'exit "$TEST_API_EXIT"\n'
                ),
            }
            for name, command in commands.items():
                path = binary / name
                path.write_text("#!/bin/bash\n" + command)
                path.chmod(0o755)
            version = root / "Telegram/build/version"
            version.parent.mkdir(parents=True)
            version.write_text(
                "AppVersionStrSmall 7.3.1.10\nAppUpdateVersion   70300110\n"
            )
            env = dict(os.environ)
            env.update(
                PATH=str(binary) + os.pathsep + env["PATH"],
                GITHUB_ACTOR="KiritoXDone",
                SOURCE_SHA=SOURCE_SHA,
                SOURCE_REF="refs/heads/main",
                VERSION="7.3.1.10",
                APP_UPDATE_VERSION="70300110",
                TEST_HEAD=SOURCE_SHA,
                TEST_COMPARE_STATUS="identical",
                TEST_API_EXIT="0",
            )
            env.update(overrides)
            return subprocess.run(
                ["bash", "-c", script], cwd=root, env=env,
                capture_output=True, text=True,
            )

    def test_accepts_current_main_and_main_ancestors(self):
        for status in ("identical", "ahead"):
            with self.subTest(status=status):
                result = self.run_validation(TEST_COMPARE_STATUS=status)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_commits_outside_main(self):
        for status in ("behind", "diverged", "", "unexpected"):
            with self.subTest(status=status):
                self.assertNotEqual(
                    self.run_validation(TEST_COMPARE_STATUS=status).returncode, 0
                )

    def test_rejects_api_failure_even_with_valid_output(self):
        self.assertNotEqual(self.run_validation(TEST_API_EXIT="1").returncode, 0)

    def test_rejects_other_dispatchers(self):
        self.assertNotEqual(self.run_validation(GITHUB_ACTOR="someone").returncode, 0)

    def test_rejects_non_sha_inputs(self):
        for sha in ("main", "abc", "../main", SOURCE_SHA + "\n"):
            with self.subTest(sha=sha):
                self.assertNotEqual(self.run_validation(SOURCE_SHA=sha).returncode, 0)

    def test_rejects_checkout_mismatch(self):
        self.assertNotEqual(self.run_validation(TEST_HEAD="f" * 40).returncode, 0)

    def test_rejects_non_main_ref(self):
        self.assertNotEqual(
            self.run_validation(SOURCE_REF="refs/tags/v7.3.1.10").returncode, 0
        )

    def test_rejects_version_mismatch(self):
        for values in ({"VERSION": "7.3.1.11"}, {"APP_UPDATE_VERSION": "70300111"}):
            with self.subTest(values=values):
                self.assertNotEqual(self.run_validation(**values).returncode, 0)

    def test_release_validation_and_outputs_remain_release_only(self):
        for name in ("Validate source request.", "Pack update.", "Write artifact provenance."):
            with self.subTest(name=name):
                self.assertIn("if: ${{ !inputs.build_only }}", step(name))
        self.assertIn("scripts/build_provenance.py validate-source", step("Validate source request."))
        self.assertIn("if: ${{ inputs.build_only }}", step("Validate standalone source."))

    def test_manual_mode_is_opt_in_and_artifacts_are_distinct(self):
        inputs = WORKFLOW.split("    inputs:\n", 1)[1]
        build_only = inputs.split("      build_only:\n", 1)[1].split("      source_sha:", 1)[0]
        self.assertIn("default: false", build_only)
        self.assertIn("type: boolean", build_only)
        self.assertIn("inputs.build_only && format('Validation-{0}-AstraGram-", WORKFLOW)
        self.assertIn("inputs.build_only && 'build-only' || 'release'", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
