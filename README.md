# AstraGram macOS builds

This repository hosts the macOS build workflow and dependency cache for [AstraGram](https://github.com/Kindness-Kismet/AstraGram-Desktop). Releases are coordinated and published by the source repository.

The source repository dispatches an exact commit and Release workflow run. This repository builds separate x64 and ARM64 packages for Intel and Apple silicon, keeps GitHub Actions caches for each architecture, and returns short-lived artifacts with provenance manifests. It does not publish releases.

Pull requests only validate workflow syntax. The signing key is scoped to the dispatched build workflow and is removed from the runner workspace after each build.

For a standalone rebuild, dispatch `build.yml` on `main` with `build_only=true`, an exact source SHA from the source repository's `main` history, `source_ref=refs/heads/main`, and the matching `version` and `appupdateversion` values. Leave the source Release run fields empty. Manual builds validate the checkout and main-branch ancestry, then upload `Validation-<SHA>-...` archives without update packages or release provenance; they do not update an existing release.

To recover missing automatic-update packages after publishing standalone ZIPs, the maintainer can dispatch `repack.yml` with their successful `build_run_id`, `source_sha`, `version` and `appupdateversion`. It checks both build artifacts against the existing stable Release assets, compiles only the original signing tool, and returns signed x64/ARM64 updates. Signing uses the source Packer's fixed Qt 5.1 stream format. No application rebuild or release publication occurs; upload and verify both update files before extending `current6`.
