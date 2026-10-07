# Source provenance and dependency licenses

## Contribution policy

The owner requires Ghost's implementation to be independently written. Do not
copy, adapt, port or translate code, tests, rules, documentation or assets from
Apache-licensed projects into this repository. This also applies to material
produced by a model from such a project's implementation. Use Ghost's feature
requirements to design its own implementation. Changing names, formatting or
language is not a substitute for independent authorship.

Do not vendor third-party implementations. For any otherwise permitted external
material, record the upstream URL, version or commit, license, destination files
and required notices before inclusion. Preserve attribution and license files;
Ghost's MIT license cannot replace someone else's license. Unclear provenance
must be resolved or reported before the material is included.

Architecture inspiration is documented openly. The OpenSRE-style folder layout
does not authorize copying its implementation. Keep that distinction explicit
in future changes.

## Dependencies are separate

This policy forbids importing Apache project material into Ghost's own source.
It does not ban separately installed dependencies. Ghost currently installs
Apache-licensed packages, including Bandit and watchdog, through Python package
management. Scanner adapters invoke installed tools; Ghost does not bundle the
scanner implementations in its wheel. Dependencies retain their own licenses.

Apache 2.0 permits reuse subject to its conditions, including license and notice
requirements when redistributing covered material. See the [official license,
sections 1, 2 and 4](https://www.apache.org/licenses/LICENSE-2.0). The owner's
no-copy policy is stricter than that permission. MIT applies to Ghost's own
material and does not erase dependency obligations. Bundled executables,
containers or offline installers would require a fresh redistribution review.

Direct runtime packages inspected in the development environment on 2026-10-05:

- Typer 0.27.2: MIT.
- Rich 15.0.0: MIT.
- prompt-toolkit 3.0.53: BSD license; installed license text checked.
- Pydantic 2.13.5: MIT.
- watchdog 6.0.0: Apache 2.0.
- httpx 0.28.1: BSD 3-Clause.
- Bandit 1.9.4: Apache 2.0.
- Semgrep 1.179.0: LGPL 2.1 or later, according to installed distribution metadata.

These describe the inspected versions, not a lockfile or a complete bill of
materials. Semgrep's binaries, transitive packages, development/build tools,
external model CLIs and future versions need their own review. A dependency
declaring multiple licenses may contain components with different terms.

## Release tooling reviewed — 2026-10-07

The release workflow, checks, tests and maintainer instructions are independently
written from Ghost's requirements. No external workflow implementation was
copied. Separately executed tools/actions are not vendored into Ghost:

- GitHub's [checkout](https://github.com/actions/checkout),
  [setup-python](https://github.com/actions/setup-python),
  [upload-artifact](https://github.com/actions/upload-artifact) and
  [download-artifact](https://github.com/actions/download-artifact): repository
  license metadata reports MIT. Workflow references pin full v6 commit IDs;
  update those pins deliberately and review their changes/licenses.
- [PyPA build](https://github.com/pypa/build) **1.3.0**: MIT, confirmed from
  installed distribution metadata. The isolated local build environment also
  installed packaging **26.3** (Apache 2.0 OR BSD 2-Clause) and pyproject-hooks
  **1.3.3** (MIT). These are build tools, not Ghost runtime additions or bundled
  project implementations. Future resolved build dependencies require review.
- [actionlint](https://github.com/rhysd/actionlint) **1.7.12**: MIT according to
  repository license metadata. Used an external local validation binary with
  its release checksum verified and included license preserved under ignored
  `.ghost/release-workflow/tooling/`; it is not shipped with Ghost.

The workflow installs package dependencies on hosted runners. Package
installation does not transfer their license to Ghost, and checks for unexpected
wheel package paths do not establish universal originality or license compliance.

## Audit performed — 2026-10-05

Audited Ghost at commit `11198e8`, before adding this policy:

- Reviewed tracked paths, license/attribution references, package configuration,
  initial commit history, scanner adapters and local scanner rules. No vendored
  Apache implementation or Apache source header was identified in this scope.
- Inspected the OpenSRE-layout commit `012ca70`: Git records moves of Ghost's
  existing implementation from `ghost/` into the layered packages, alongside
  import/composition changes. This is evidence for a layout migration, not a
  general certification of every file's authorship.
- Compared 131 tracked source/config/vector files against installed packages
  whose metadata mentions Apache. Checked exact whole-file SHA-256 matches
  (Ghost files larger than 300 bytes) and Python AST matches for functions/classes
  spanning at least 12 source lines and exceeding 400 AST characters. AST matching
  ignores comments, locations and formatting, but retains identifiers/literals.
  Compared 328 distinct Ghost AST blocks with 1,925 reference blocks from 604
  Python files across 20 distributions: **zero matches** in either comparison.
- Inspected the previously built `ghost_debugger-0.1.0-py3-none-any.whl`: all 104
  archive entries belong to Ghost's five packages or its distribution metadata.
  No external package paths were bundled. This path check does not itself prove
  the origin of code within a Ghost package.

The reference set included Bandit, watchdog, requests, packaging, cryptography,
stevedore, importlib_metadata, pytest-asyncio, python-multipart,
googleapis-common-protos and ten OpenTelemetry distributions. It includes
development/transitive packages and packages offering Apache among other terms.
Only their installed Python files were compared; binary components were not.
The local machine-readable result is ignored runtime evidence at
`.ghost/evidence-integrity/source-provenance-audit.json`.

No evidence of copied Apache source was found by these checks. They cannot
establish universal originality: renamed/rewritten code, short snippets,
unavailable upstream versions, other repositories and non-Python similarity
were not covered. The OpenSRE reference checkout was not available in the checked
`/Users/deveshrathod/Dev` directories for a direct comparison. Raster assets were
not compared against external image collections. Keep provenance review as a
release gate; do not advertise Ghost as Apache-free or legally certified.
