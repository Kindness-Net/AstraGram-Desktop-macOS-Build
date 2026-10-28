#!/usr/bin/env python3
"""补包前核对构建来源、已发布归档和应用架构。"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct
import subprocess
import zipfile


SOURCE_REPOSITORY = "Kindness-Kismet/AstraGram-Desktop"
BUILDER_REPOSITORY = "Kindness-Net/AstraGram-Desktop-macOS-Build"


def gh_json(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint]))


def validate_archive(path, asset, version, update_version, official_version, arch):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if asset["state"] != "uploaded" or asset["size"] != path.stat().st_size:
        raise ValueError("Release archive is incomplete or has a different size")
    if asset["digest"] != "sha256:" + digest:
        raise ValueError("Build artifact differs from the published release archive")
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ValueError("Unsafe archive path")
        if archive.testzip() is not None:
            raise ValueError("Archive CRC failed")
        info = plistlib.loads(archive.read("AstraGram.app/Contents/Info.plist"))
        if info["CFBundleShortVersionString"] != official_version:
            raise ValueError("Application version mismatch")
        if info["CFBundleVersion"] != update_version:
            raise ValueError("Application update version mismatch")
        name = "AstraGram.app/Contents/MacOS/AstraGram"
        with archive.open(name) as binary:
            magic, cpu = struct.unpack("<II", binary.read(8))
        if (magic, cpu) != (0xFEEDFACF, {"x64": 0x1000007, "arm64": 0x100000C}[arch]):
            raise ValueError("Application architecture mismatch")
        if not (archive.getinfo(name).external_attr >> 16) & 0o111:
            raise ValueError("Application executable permission is missing")
    expected = f"AstraGram-v{version}-macos-{arch}.zip"
    if path.name != expected or asset["name"] != expected:
        raise ValueError("Archive filename mismatch")
    return digest


def main():
    sha, version = os.environ["SOURCE_SHA"], os.environ["VERSION"]
    update_version, run_id = os.environ["UPDATE_VERSION"], os.environ["BUILD_RUN_ID"]
    if os.environ["GITHUB_ACTOR"] != "KiritoXDone":
        raise ValueError("Only the release maintainer can dispatch repackaging")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"\d+(?:\.\d+){3}", version):
        raise ValueError("Invalid source SHA or version")
    if not run_id.isdecimal() or not update_version.isdecimal():
        raise ValueError("Invalid build run or update version")
    if not 1016 < int(update_version) <= 999999999:
        raise ValueError("Update version exceeds the Packer range")
    head = subprocess.check_output(["git", "-C", "source", "rev-parse", "HEAD"], text=True).strip()
    fields = dict(line.split(None, 1) for line in Path("source/Telegram/build/version").read_text().splitlines() if line.strip())
    if head != sha or fields["AppVersionStrSmall"] != version or fields["AppUpdateVersion"] != update_version:
        raise ValueError("Source checkout or version mismatch")
    compare = gh_json(f"repos/{SOURCE_REPOSITORY}/compare/{sha}...main")
    if compare["status"] not in ("identical", "ahead"):
        raise ValueError("Source commit must belong to main")
    run = gh_json(f"repos/{BUILDER_REPOSITORY}/actions/runs/{run_id}")
    if (run["conclusion"], run["event"], run["path"], run["actor"]["login"], run["head_branch"]) != (
        "success", "workflow_dispatch", ".github/workflows/build.yml", "KiritoXDone", "main"
    ):
        raise ValueError("Expected a successful main-branch macOS build")
    release = gh_json(f"repos/{SOURCE_REPOSITORY}/releases/tags/v{version}")
    if release["draft"] or release["prerelease"]:
        raise ValueError("Expected a published stable release")
    artifacts = gh_json(f"repos/{BUILDER_REPOSITORY}/actions/runs/{run_id}/artifacts")["artifacts"]
    evidence = {"source_sha": sha, "build_run_id": run_id, "version": version, "appupdateversion": update_version, "archives": {}}
    for arch in ("x64", "arm64"):
        artifact = f"Validation-{sha}-AstraGram-macOS-{arch}"
        matches = [a for a in artifacts if a["name"] == artifact and not a["expired"]]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous validation artifact")
        directory = Path("archives") / arch
        subprocess.run(["gh", "run", "download", run_id, "-R", BUILDER_REPOSITORY, "-n", artifact, "-D", str(directory)], check=True)
        path = directory / f"AstraGram-v{version}-macos-{arch}.zip"
        asset = next(a for a in release["assets"] if a["name"] == path.name)
        evidence["archives"][arch] = validate_archive(path, asset, version, update_version, fields["AppVersionStrOfficial"], arch)
    Path("output").mkdir()
    Path("output/repack-inputs.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("Both build artifacts match the published archives, versions and architectures.")


if __name__ == "__main__":
    main()
