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

These describe versions inspected on 2026-10-05. `uv.lock` now records exact
development/test package resolutions and archive hashes, but it is not a
complete license bill of materials. Semgrep's binaries, external model CLIs,
future versions, and licenses of transitive packages still need review. A
dependency declaring multiple licenses may contain components with different
terms.

## Release and CI tooling reviewed — 2026-10-08

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
- [uv](https://github.com/astral-sh/uv) **0.12.23**: the upstream project offers
  MIT or Apache 2.0 licensing. CI installs the pinned package as a dependency
  manager and uses it to enforce `uv.lock`; no uv source, tests, rules,
  documentation, or assets are copied into Ghost, and uv is not bundled in the
  Ghost wheel. The owner’s no-copy policy remains in force regardless of the
  upstream license option. The pinned upstream license files are available at
  [MIT](https://github.com/astral-sh/uv/blob/0.12.23/LICENSE-MIT) and
  [Apache 2.0](https://github.com/astral-sh/uv/blob/0.12.23/LICENSE-APACHE).

The workflow installs package dependencies on hosted runners. Package
installation does not transfer their license to Ghost, and checks for unexpected
wheel package paths do not establish universal originality or license compliance.

## Security brief preview — 2026-10-08

`assets/brief-preview.svg` records Ghost's actual output from an independently
created disposable Python/TypeScript sample. It was generated by the already
installed Rich **15.0.0** (MIT) SVG exporter; the generated Rich attribution
comment is preserved. The preview's external font declarations were removed:
it uses local font fallbacks and bundles no third-party font files. No project
source, scanner rules, external screenshot or new dependency was incorporated
for this feature. Its renderer, tests and user guides were written independently
from Ghost's requirements.

## Landing page — 2026-10-09

The static landing page, styles, interactions, illustrative workflow panels
and Pages workflow were independently authored from Ghost's requirements.
`site/assets/ghost-icon.svg` reuses the existing Ghost-owned mascot unchanged.
No external templates, fonts, icons or frontend packages were incorporated.
Browser checks used the environment's separately installed Playwright 1.57.0
(Apache 2.0) and Chromium; none of their source, fixtures or assets were copied
or shipped with the site. Browser automation was independently written.

Separately executed GitHub Pages actions were reviewed at these references:

- [configure-pages](https://github.com/actions/configure-pages) v5,
  `983d7736d9b0ae728b81ab479565c72886d7745b`: MIT.
- [upload-pages-artifact](https://github.com/actions/upload-pages-artifact) v3,
  `56afc609e74202658d3ffba0e8f6dda462b719fa`: MIT.
- [deploy-pages](https://github.com/actions/deploy-pages) v4,
  `d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e`: MIT.

Their upstream LICENSE files were read at those commits. No action implementation
is vendored in Ghost. These tools retain their own licenses; the site adds no
Ghost runtime dependency. Checkout is the existing pinned action recorded above.

## Next.js frontend conversion — 2026-10-09

The Next.js App Router page and typed React interactions were independently
written from Ghost's existing landing page and feature requirements. They reuse
Ghost's own content, CSS and icons. No external application template, scanner
source, tests or assets were copied. The mascot now lives in
`site/public/assets/ghost-icon.svg`. The previous Pages workflow is replaced
with frontend type/build checks; Vercel deployment uses the Next.js preset.

New separately installed frontend dependencies, with exact versions pinned in
`site/package.json` and resolved archives recorded in `site/package-lock.json`:

- [Next.js](https://github.com/vercel/next.js) 16.4.0: MIT.
- [React and React DOM](https://github.com/facebook/react) 19.3.0: MIT.
- [TypeScript](https://github.com/microsoft/TypeScript) 5.9.3: Apache 2.0;
  development type-checker only. Its source is not incorporated into Ghost.
- [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped)
  `@types/node` 24.10.1, `@types/react` 19.3.0 and `@types/react-dom` 19.3.0: MIT.

Registry license metadata and the installed Next/React/TypeScript license files
were checked. Their notices remain in separately installed dependency packages;
`node_modules/`, build artifacts and generated Next type directives are ignored
by Git. This list is not a complete transitive dependency license inventory.
No dependencies were added to Ghost's Python CLI.

Formatting used separately executed [Prettier](https://github.com/prettier/prettier)
3.6.2 (MIT), with no Prettier implementation included. Frontend CI executes
[setup-node](https://github.com/actions/setup-node) v6 at
`249970729cb0ef3589644e2896645e5dc5ba9c38` (MIT; upstream LICENSE read at that
commit), alongside the existing pinned checkout action. No external action
implementation is vendored.

## Review triage and scanner transport — 2026-10-09

`install.sh` and `Formula/ghost.rb` were independently authored for Ghost's
installation requirements; no external installer or formula implementation
was copied. They invoke separately installed Homebrew or uv. Homebrew's
[project license](https://github.com/Homebrew/brew/blob/master/LICENSE.txt)
is BSD 2-Clause; no Homebrew code is bundled. The formula uses the project's
existing Python runtime and locked dependencies, whose licenses remain their
own. Homebrew resolves its own tool versions at installation time; these are
not newly pinned Ghost runtime dependencies.

The finding filters, grouped views, investigation guidance, regression fixtures
and bounded report worker were independently written from Ghost's requirements.
The worker invokes the separately installed Bandit CLI, then selects the
metadata Ghost already uses from its JSON report. No Bandit implementation,
tests, documentation or rules were copied, and no new dependency was added.
Bandit retains the dependency license recorded above.

## Repair runner verification — 2026-10-09

The typed runner adapter, TAP evidence validation, CLI guidance and JavaScript
repair fixtures were independently written from Ghost's verification requirements.
No external implementations, tests, rules or documentation were copied or added
as dependencies. The fixtures invoke the separately installed Node built-in
test runner; Ghost does not bundle Node. Deterministic model replies use Ghost's
existing fake provider and are labeled as such, not live provider validation.

Linux/macOS test CI selects Node 20 using the same pinned `actions/setup-node`
v6 reference already reviewed for the frontend above. It configures a hosted CI
runtime; the repair adapter never installs runtimes or project dependencies.

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

## In-site documentation and terminal gallery — 2026-10-10

The `/docs` Next.js page, shared navigation, command-copy component and responsive
styles were independently written from Ghost's current CLI and guides. No new
runtime dependency or external template was added. Browser automation uses the
already installed Playwright/Chromium tooling described above, without vendoring
its implementation; formatting uses the same separately executed Prettier 3.6.2.

`site/public/assets/screenshots/01` through `04` copy Ghost's existing framed and
plain PNG captures from `assets/screenshots/` unchanged. Those captures are from
executed disposable samples, show an earlier interface snapshot, and retain
explicit evidence limits. Full-resolution originals remain available.

`05-fix-illustration.png` and `06-chat-illustration.png` reuse the user-requested
AI-generated announcement images from this session unchanged. They are labeled
illustrative demos, not live terminal screenshots or evidence of model quality.
No external screenshot, template, icon source, font file or implementation was
copied into this increment.

The website also serves the existing `assets/brief-preview.svg` unchanged as a
separate real saved-review capture. Its Rich exporter attribution is preserved;
no font or script dependency is added.

## Documentation organization, phase history and fresh captures — 2026-10-10

The grouped contents, quick-start cards, accessible gallery tabs, dated phase
timeline, and Git-history generator were independently written from the owner's
requested workflow. Historical entries use Ghost's own commits; development
notes summarize available conversations without copying private transcripts.
No external templates, implementations, rules, or assets were incorporated,
and no application dependency was added.

The six replacement website captures render Ghost's current home/help, scan,
brief, repair, and local chat-action output from an independently authored,
disposable Python/TypeScript sample. Bandit 1.9.4 and Semgrep 1.180.0 executed
under existing OS confinement. The Python sample passed three baseline and
patched unittest cases, the supported helper probe and static rescan; reviewed
sample source stayed unchanged. No model was called. Captures preserve the
suspected-finding and helper-proof limits.

Rendering uses separately installed Rich 15.0.0 (MIT) and Playwright 1.62.1
(Apache 2.0) with the environment's Chromium. Their implementations are not
copied or shipped with Ghost; no external font file is bundled. The frame and
generation scripts are independently authored. Formatting uses the previously
documented, separately executed Prettier 3.6.2 (MIT). Earlier illustration assets
are retained, but are not displayed in the new gallery.
