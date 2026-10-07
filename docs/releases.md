# Releasing Ghost

Ghost's [Release checks workflow](../.github/workflows/release.yml) runs on pull
requests, pushes to `main`, version tags and manual dispatch. Branch/PR/manual
runs validate a preview and retain artifacts. A matching version tag creates a
**draft GitHub release** only after every required job passes.

## What the workflow checks

1. All tests on Ubuntu 22.04 and macOS 14 with Python 3.12 and OS confinement.
   Linux installs bubblewrap; no isolation opt-out is used. Node must be available
   for local JavaScript authorization cases.
2. A canonical version in `pyproject.toml`, with tag equality and tag commit
   ancestry on `main`. Stable `v0.1.0` and prerelease `v0.2.0rc1`, `v0.2.0a1`,
   `v0.2.0b1` forms are supported; prereleases are marked on the draft.
3. An isolated source-distribution build, then a wheel built from that archive.
   Archive metadata, MIT license files, CLI entrypoint, bundled Ghost rules,
   unsafe/private archive paths and accidental external wheel packages are checked.
4. Installation of the wheel into a new environment; CLI help and the real mixed
   Python/TypeScript security repair demo run outside the source checkout.
5. SHA-256 checksums of the wheel/source archive, verified after downloading the
   workflow artifact into the draft job. Checksums detect content changes; they
   are not signatures or a substitute for verifying the workflow/source origin.

Actions are pinned to full commits. Test/build jobs have read-only repository
permissions; only the gated draft job receives `contents: write`, and its token
is supplied only to the GitHub CLI step. Checkout does not persist credentials.
No provider keys or PyPI token are needed. Runtime dependencies are downloaded
from their package indexes during installation; scanner/proof execution remains
local. Current dependency ranges are not a reproducible lockfile.

## Preview without creating a release

Open **Actions → Release checks → Run workflow** on `main`, or:

```bash
gh workflow run release.yml --ref main
gh run list --workflow release.yml
```

Inspect every job and download the `release-dist` artifact. Artifacts and test
reports are retained for 14 days. The baseline matrix exercises Python 3.12;
newer Python versions and other OS/architecture combinations need separate
qualification.
Newer branch previews cancel obsolete previews. Version-tag runs are serialized
without cancelling an in-progress release check.

## Create a draft when a version is ready

Update `[project].version` in `pyproject.toml`, document changes and remaining
limits, review source/dependency licenses, merge the tested work into `main`,
and confirm the branch is clean and synchronized with GitHub. Then, for the
matching version (replace `0.1.0` when appropriate):

```bash
python scripts/release.py validate --tag v0.1.0
git tag -a v0.1.0 -m "Ghost 0.1.0"
git push origin v0.1.0
```

Review the draft under **GitHub → Releases**. It contains the wheel, source
archive, `SHA256SUMS`, and generated installation/license notes. Add the actual
version's changelog and known limitations before manually publishing the draft.
This workflow does not publish to PyPI. PyPI publishing requires a separately
reviewed package-index workflow and authorization.

Failed tests/builds block the draft. Fix the failure and rerun checks before
considering release. Never move a published tag or overwrite published assets.
If draft creation partially failed, inspect the existing draft first; duplicate
release creation fails rather than replacing it. A maintainer may remove an
unpublished failed draft and rerun the draft job after review.

For a local packaging check:

```bash
python -m pip install 'build==1.3.0'
python -m build
python scripts/release.py prepare --dist dist
```

Use a fresh `dist/` directory: the checker requires exactly the current version's
wheel and source archive before it writes notes/checksums. A green workflow is
executable evidence for these gates, not proof that all launch blockers are
closed. Keep [launch readiness](launch-readiness.md) and
[source provenance](source-provenance.md) as review gates.
