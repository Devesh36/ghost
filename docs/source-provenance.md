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

## Interactive workspace improvements — 2026-10-10

The workspace header, contextual footer, CLI-declaration completion, and input
event tests were independently written for Ghost. They use the already installed
Typer, prompt-toolkit, and Rich APIs without copying their implementations.
No application dependency or external asset was added. The refreshed workspace
capture renders Ghost's own home screen from a disposable project using the
same separately installed Rich/Playwright tooling and original frame described
above. No scan or model request is represented by that workspace capture.

## Terminal identity and product landing page — 2026-10-10

The product layout, responsive styles, theme generator and real-output preview
were independently written for this request. Website colors are extracted from
Ghost's own terminal palette. Product previews are escaped Rich HTML exports
from the same disposable sample and existing renderers, at desktop and mobile
terminal widths. The six gallery PNGs were regenerated in matching frames.
The confined scanners and supported Python repair checks ran successfully;
three baseline and patched project tests passed and sample source stayed
unchanged. No model, external template, font or new dependency was used.
Rendering and formatting use the separately installed tools already recorded
above, without copying their implementations.

## Source freshness and shell review accuracy — 2026-10-12

The opt-in source inspection, terminal/JSON report, Node import/require patterns
and positive/negative regression fixtures were independently written from
Ghost's existing APIs and the requested behavior. No external rule registry,
template, third-party implementation or new dependency was incorporated.
No Ghost model provider was called during qualification.
Qualification uses the already installed Semgrep/Bandit scanners under OS
confinement. The 179-file corpus is synthetic Ghost-authored source, never
executed or imported; scanner evidence remains suspected. Rich rendering and
website formatting use the existing separately installed tools described above.

## Review navigation and comparison context — 2026-10-14

The duplicate pairing, saved-source comparison context, filtered comparison
pages, transactional history pagination, regression cases and guides were
independently designed from Ghost's existing models and this milestone's
requirements. No external implementation, rule, test corpus, template or new
dependency was incorporated. The two additional terminal captures use the
existing independently authored sample, Rich renderer and Playwright frame.
Real confined scans precede and follow the sample TypeScript edit; the original
sample source is restored after capture. Static disappearances are not presented
as verified fixes. No Ghost model provider is called by this workflow.

## FalkorDB Graph Hacks triage — 2026-10-16

The synthetic dataset, graph schema, parameterized Cypher loader/ranking/witness
queries, deterministic triage agent, CLI renderer, tests, Compose configuration
and guide are new, independently authored work in this increment. Ghost's own
finding model, terminal palette, CLI/REPL framework and CI conventions are reused.
No third-party implementation, graph tutorial, sample dataset, test, scanner
rule or template was copied, adapted or vendored into Ghost.

New separately installed optional graph dependencies, resolved in `uv.lock`:

- [FalkorDB Python client](https://pypi.org/project/falkordb/1.8.0/) **1.8.0**:
  MIT; wheel license inspected. Public `FalkorDB`, `select_graph`, `query` and
  `ro_query` APIs are called without copying their implementations.
- [redis-py](https://pypi.org/project/redis/8.1.0/) **8.1.0**: MIT; wheel license
  inspected. Used by the SDK and its bounded retry configuration.
- [python-dateutil](https://pypi.org/project/python-dateutil/2.9.0.post0/)
  **2.9.0.post0**: dual Apache 2.0/BSD licensing, recorded in installed metadata.
  A separately installed transitive dependency, not incorporated source.
- [six](https://pypi.org/project/six/1.17.0/) **1.17.0**: MIT, recorded in
  installed metadata; separately installed transitive dependency.

The local server is the separately pulled `falkordb/falkordb` image, pinned to
manifest `sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a`.
Its running graph module reports **4.22.1**. FalkorDB's server
[LICENSE.txt](https://github.com/FalkorDB/FalkorDB/blob/6b6fbe82f3836be00221bbc1310ebceaefc6db10/LICENSE.txt)
at the v4.22.1 tag is **SSPL v1**, inspected separately from the SDK's MIT license.
The image and its other components retain their upstream terms; this is not a
complete container bill of materials. No server binaries/source are shipped in
Ghost's wheel. Compose runs a local service, not a hosted database offering;
redistribution or a hosted offering would require its own dependency review.

The graph-specific CI job uses the same pinned checkout/setup-python actions and
uv version already reviewed above. It copies no external workflow implementation.
The real demo uses only the new synthetic scenario and makes no LLM request.
Its terminal PNG reuses Ghost's independently authored gallery frame and actual
Rich output, rendered with the existing separately installed Playwright/Chromium
tools recorded above. It contains no external screenshot or font asset.

## Graph Hacks submission preparation — 2026-10-16

The disposable walkthrough, failure-cleanup tests, submission brief and captioned
demo replay are independently authored from Ghost's own feature and output. The
video renders fresh FalkorDB answers in Ghost's palette. It is an edited replay,
not a continuous recording or a fabricated scan, and contains no external music,
font files, graphics or source. Existing Rich/Playwright/Chromium tools are reused.
The separately executed system **FFmpeg 7.1.5-0+deb13u1** reports **GPL v2 or later**
for this build (`ffmpeg -L`); its tools and libraries are not bundled with Ghost.
Chromium reports **151.0.7922.173**. No application dependency was added.

The organizer's MIT-licensed website repository was inspected outside Ghost at
`WeMakeDevs/wemakedevs@62a6fc788845850666037d46eb3c1f3fb9f6cbaa` solely to look
for published event requirements. It had no FalkorDB event page; none of its
source, copy, rules or assets is incorporated. The inaccessible live event rules
are not reconstructed from other events or presented as verified.

## Storage sidecar diagnostics — 2026-10-16

The error classification, bounded diagnostic metadata and deterministic filesystem
race fixtures are independently authored from Ghost's existing storage policy.
The tests use synthetic files and real local SQLite sidecar lifecycle operations;
no external implementation, fixture, scanner rule or dependency was added.
The existing file ownership, type, link and identity checks remain enforced.

## One-command FalkorDB recording demo — 2026-10-18

The installed graph demo reuses Ghost's independently authored synthetic
walkthrough and terminal renderer. Its orchestration now lives in the packaged
infrastructure layer; the original example imports it. Stage callbacks,
interactive pauses, optional JSON output, CLI validation and interruption/load
cleanup tests are new independently written work. No external implementation,
asset or dependency was added; existing graph client/server licenses still apply.

## Native FalkorDB demo runtime — 2026-10-18

The optional process launcher, private-socket adapter, demo integration and
lifecycle checks are independently authored for Ghost. No upstream implementation,
documentation, fixtures or binaries are copied into Ghost's source or wheel.
The existing synthetic dataset, queries and recommendation validation are reused.

New separately installed dependencies are pinned/resolved in `uv.lock`:

- [FalkorDBLite 0.10.0](https://pypi.org/project/falkordblite/0.10.0/): its installed
  wrapper [license](https://github.com/FalkorDB/falkordblite/blob/master/LICENSE.txt)
  is BSD 3-Clause, inspected in the wheel. Ghost locates the installed native
  executables through distribution metadata and launches its own foreground
  child; it does not copy the package's server orchestration implementation.
- [psutil 7.2.2](https://pypi.org/project/psutil/7.2.2/): BSD 3-Clause, installed
  license inspected; a Lite dependency, not directly called by Ghost.
- [setuptools 84.0.0](https://pypi.org/project/setuptools/84.0.0/): MIT in installed
  metadata/license, with separately licensed vendored components and notices
  retained inside its installed distribution; a Lite dependency.

The tested Linux Lite wheel contains native FalkorDB **4.18.3** and Redis
**8.6.2**, as reported by the running module/server. The BSD wrapper license
does not replace the engines' terms: FalkorDB's
[v4.18.3 license](https://github.com/FalkorDB/FalkorDB/blob/v4.18.3/LICENSE.txt)
is SSPL v1; Redis's [8.6.2 license description](https://github.com/redis/redis/blob/8.6.2/README.md#license)
offers RSALv2/SSPLv1/AGPLv3. These upstream records were inspected separately.
No server binary is redistributed in Ghost's distributions; the optional wheel
is installed independently and retains its own notices. This is not a complete
binary/transitive license inventory; bundling it would require a separate review.

## Optional graph diagnostics — 2026-10-21

The data-free graph capability probe, installation details, CLI options,
error classification and regression scenarios are independently authored from
Ghost's setup failures and existing doctor contract. They call the existing
redis-py PING/COMMAND INFO APIs and reuse Ghost's native process owner. No
external implementation, documentation, fixtures, rules, assets or new
dependencies were added. Existing optional client/server licenses still apply.

## Node TLS environment-switch coverage — 2026-10-21

The GJS004 environment-assignment patterns, Node binding restrictions, shadowing
exclusions and 161-file positive/negative corpus are independently authored from
Ghost's detection requirements. The existing per-request TLS check and scanner
transport are reused. No external rule pack, implementation, fixture, asset or
dependency was added. The separately installed Semgrep retains the license
recorded above; its implementation was not copied or adapted into these rules.

## Ghost Challenge — 2026-10-22

The four-stage counterfactual workflow, structured unittest worker, selection
and inventory checks, persisted challenge evidence, application gates, CLI/REPL
presentation, synthetic importer demo and regressions are independently authored
from Ghost's evidence requirements. No external agent implementation, mutation
testing project, rule pack, fixture, documentation or asset was copied or adapted.
The mechanism reuses Ghost's source identities, worktrees, OS confinement,
repair proposals and existing storage. Python's separately installed standard
library unittest provides test execution. No application dependency or new
database table is added; existing dependencies retain their recorded licenses.


## Repair evidence reports — 2026-10-24

The Markdown export, patch identity, saved-evidence consistency checks and
regressions are independently authored from Ghost's existing Challenge contract.
They reuse Ghost's saved proposal and case records and Python standard-library
hashing/JSON/HTML escaping. No external implementation, documentation, asset or
new dependency was incorporated. Reports remain unsigned local evidence.


## Challenge application consistency — 2026-10-25

The shared application guard and synthetic recipe/LLM regressions are independently
authored from Ghost's existing report validator and repair workflow. Both application
paths reuse the same local record consistency checks, preserving source freshness
and approval requirements. No external implementation, fixture or dependency was
added. The guard does not turn local records into authenticated attestations.


## Adversarial Challenge snapshot review — 2026-10-25

The bounded snapshot fingerprint, final-run and pre-application comparisons, and
synthetic adversarial cases are independently authored from Ghost's own snapshot
reader and patch writer. Tests cover Git index hints, source/test edits, missing
records, changed paths and symlink swaps without executing external project code
or reading external reference implementations. No dependency or schema migration
was added; the optional record field remains backward-loadable.


## Solver snapshots and pre-install validation — 2026-10-25

The proposal byte/patch identity, pre-install callback, candidate integrity checks
and synthetic late-edit regressions are independently authored from Ghost's
existing solver snapshots and single-file writer. Tests reuse Ghost-owned sample
parsers and FakeProvider fixtures; no external implementation or new dependency
was added. New optional JSON record fields require no database migration and
retain backward loading, while older proposals need a fresh solve to apply.
