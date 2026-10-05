# Ghost launch readiness

Release status: **more hardening is required before a production launch**.

This document is the handoff for launch-readiness work. The owner resumed the hourly improvement schedule. Keep work bounded, preserve user changes, test behavior before marking an item complete, commit and push verified improvements to GitHub, and leave release decisions to the owner.

## Debugger capture completeness and verification gates (2026-10-05)

- Reproduced a false-verification gap with a real isolated command: an
  81,000-byte stdout stream exceeded the 64,000-byte capture limit but exited 0.
  The debugger dropped the truncation flag and accepted that exit code as
  verification. The reproduction preserved developer source and removed its
  worktree; the problem was evidence promotion after bounded execution.
- Debugger reproductions, clean-baseline comparisons, file reversals and repeated
  runs now persist output-limit and OS-confinement metadata. Truncated output,
  missing confinement, timeout or termination makes the experiment inconclusive.
  An incomplete control stops before patch generation. Repeated runs retain an
  incomplete run's exit/output and aggregate capture/confinement/timeout flags,
  so a later successful repeat cannot hide an earlier interrupted command.
- Added one shared executable verification predicate for application, CLI exit
  status, saved report/history labels and the runnable debugger demo. All recorded
  checks must pass with complete capture and confirmed confinement, and match the
  command-to-exit map. Verification stops at the first failed/incomplete command.
  Exit 0 with output truncation cannot authorize application, even with `--apply`.
  Reports expose the reason; the CLI recommends reducing verbosity and retrying.
- Older records deserialize without a migration. Missing capture provenance is
  explicitly unknown and cannot establish verification or causal confidence.
  Recorded experiment conclusions remain readable beside the incomplete-evidence
  label. Previously recorded application stays labeled applied as an action;
  historical browsing still does not reverify current source.
- The affected debugger, execution, locks, model deadlines, patch application,
  privacy, security repair, demo, history and architecture checks passed **215
  tests in 347.22s**, before the final repeat-provenance and history-rendering
  refinements. The final evidence/history suite then passed **56 tests in 30.78s**.
  The 41 new regression cases cover every experiment kind, either repeated run,
  missing confinement, timeouts/signals, forged supported labels, legacy records,
  CLI exit gates, and actual noisy stdout/stderr in isolated reproductions and
  broader verification. Source signatures and worktree cleanup were checked.
- The globally installed CLI passed three disposable-repository scenarios:
  noisy reproduction stopped after one command with exit **1**; noisy broader
  verification returned exit **1** despite all command exit codes being zero;
  complete verification with explicit `--apply` returned exit **0** and applied
  only the sample fix. Incomplete runs preserved source and all extra worktrees
  were removed. Saved JSON retained the capture flags. Actual REPL report views
  passed at **40/96 columns** and **40-column NO_COLOR**; redirected reports at
  **24/40/96 columns** showed the incomplete reason and unverified patch. Runtime
  captures remain ignored. Wheel content comparison, compilation and whitespace
  checks passed. macOS was exercised; Linux/Windows were not tested here.
- Remaining limits: this checks subprocess capture completeness, not whether test
  coverage is adequate or the output tells the truth. Stored output summaries
  remain intentionally short. Changed/skipped collection and normalized failure
  comparisons still need work; trusted project tests can pass despite an incorrect
  patch. This is additional debugger hardening; the security repair path already
  rejected output truncation. Privacy, durability, platform and release blockers
  remain, and production readiness is not established.

## Security review history and inspection (2026-10-05)

- Added `ghost audits [--limit 20] [--json]` and REPL `/audits` to browse saved
  security reviews without scanning again. The history view distinguishes scan
  completeness, suspected static findings and baseline local access verdicts;
  candidate verification never hides the original access failure. Empty history
  offers `scope` and `find`. Wide terminals use a compact table; narrow terminals
  use cards or stacked text, with explicit UTC timestamps and text status labels.
- `ghost findings --audit ID` selects a saved review by full ID or unique literal
  prefix, combined with existing finding selection, severity filters or complete
  JSON export. Empty, unknown and ambiguous audit IDs fail explicitly and never
  fall back to the latest record. Inspection does not change the latest audit
  used by repairs or chat context. Historical views explain that source was not
  rechecked and direct users to rerun `find` before requesting a repair.
- Added recorded start time and base commit to finding reports, literal metadata
  boundaries for audit headers, and rejection of empty finding selectors. Updated
  REPL command discovery/help, the review guide, AI capability guidance and README
  usage examples. History and selected-record inspection return 0 for valid reads;
  this is not the saved scan's result or a current security gate.
- Initial history, security presentation, keyboard discovery, guidance and
  architecture checks passed **88 tests in 44.00s**. Security repairs, other
  histories, sessions, connections and themes passed **141 tests in 138.28s**.
  After visual refinements, the final affected history, security presentation,
  guide and architecture suite passed **73 tests in 42.81s**. The 25 new history
  tests cover scope, ordering, exact/prefix matching, SQL wildcard/injection
  selectors, unchanged latest state, filters, baseline/candidate distinction,
  malformed metadata, timestamps, narrow output and real vulnerable/safe/invalid
  source scans. A historical finding could not authorize a repair from the latest
  incomplete scan; checkout signatures and worktree counts stayed unchanged.
- Globally installed Ghost passed three real disposable-repository scans with
  expected exits **1 / 0 / 2**, followed by history/selected-record inspection.
  Real macOS REPL PTYs passed at **24/40/96 columns**, plus **40-column NO_COLOR**:
  `/aud` arrow selection, insertion before explicit submission, historical finding
  inspection, invalid-ID recovery and exit. Redirected plain history passed at
  all three widths. Real output inspection caught escaped layout newlines in the
  first narrow view; they were corrected without allowing metadata to forge line
  breaks, then tested again. Actual VT captures were inspected as PNGs. Runtime
  captures remain ignored. Final wheel build/content comparison, compilation and
  `git diff --check` passed; the new module is packaged, runtime files are excluded.
- Remaining limits: browsing preserves recorded evidence; it does not compare
  audits, infer that a vulnerability was fixed, reverify source or select old
  evidence for repairs. Linux/Windows terminal behavior and live resize were not
  exercised here. Existing security coverage, persistence/crash recovery, privacy,
  sandbox and release blockers remain; production readiness is not established.

## Agent model deadlines and cancellation (2026-10-04)

- Reproduced a stalled-model gap: a 50 ms investigation budget took **403 ms**
  to return from a 400 ms custom provider, and the provider was never cancelled.
  The outer harness deliberately drained shielded work to protect snapshots,
  but did not signal pending model I/O to stop.
- Every built-in hypothesis/patch reasoning call now has a provider-independent
  deadline: 60 seconds without provider limits, or its validated declared timeout
  up to 300 seconds. Existing HTTP/CLI defaults stay 60/120 seconds. Calls also
  observe the remaining investigation budget and stop event, polled every 50 ms
  during cooperative async I/O. Invalid deadlines fail before invoking
  the provider. Credential checks still run before requests.
- Model tasks are cancelled and drained separately from thread workers. Late
  answers, including answers returned during cancellation, cannot become patches;
  cleanup exceptions cannot replace the timeout with private provider details.
  Repeated cancellation retains ownership of provider cleanup, the worktree and
  repository lock. Thread workers retain their existing cooperative stop/drain
  behavior. A request timeout allows deterministic hypothesis fallback; an
  exhausted investigation budget stops the run and persists its final state.
- Verification on macOS: **172 tests passed in 165.60s** across model deadlines,
  execution, locks, privacy, real debugger scenarios, report history, HTTP/Claude
  transports and architecture. Connections and the real offline demo passed
  another **48 tests in 33.82s**. The 21 new regressions include invalid limits,
  late answers, cleanup errors, request versus investigation deadlines, a real
  verified deterministic fallback, a timed-out fixer, and repeated cancellation
  while a real snapshot/lock remain held. Compilation and `git diff --check` passed.
- The globally installed CLI passed two disposable Git-repository scenarios with
  a deliberately stalled Codex transport stub (no remote account request): a
  five-second budget stopped the run in **5.79s**, exit 1; SIGINT cancelled the
  run in **3.03s**, exit 130. Both saved accurate reports with zero experiment
  commands, preserved source signatures, removed all extra worktrees, killed
  the stub and its child process, and removed the provider's temporary directory.
- Remaining limits: cancellation is cooperative Python behavior. A custom
  provider that blocks the event loop, ignores cancellation indefinitely, or
  never finishes cleanup cannot be forcibly contained in-process. Cleanup and
  synchronous Git/filesystem work may extend past the budget. Linux/Windows
  process behavior remains unverified here; the other launch blockers remain.

## Repository-specific onboarding guide (2026-10-04)

- Expanded README project setup into five concrete steps: choose the repository
  with `cd`, check Git/dependencies, review source, record daily development,
  inspect/verify a supported repair and optionally connect AI advice. Added
  project switching, root selection from subdirectories/monorepos, per-repository
  evidence and shared user-theme behavior.
- Corrected ignore-rule wording: users add `.ghost/` to their own `.gitignore`;
  Ghost does not currently add it automatically. Clarified activated project
  environments for recorded commands versus Ghost's installed Python interpreter
  for repair tests, with a shared-environment installation example and an absolute
  executable fallback. No implementation behavior changed.
- Verification: **8 installed-CLI command checks passed** in an isolated Python
  repository: scope, recorded unittest tests, find (expected exit 1), finding
  inspection, solve, solution, timeline and status from a subdirectory. A genuine
  B307 finding was detected and its repair verified without applying it. Source
  and Git signatures stayed unchanged; sandbox worktrees were removed. The smoke
  initially exposed a missing `python` on PATH; the guide now explains activation
  and the `python3` alternative. Markdown diff checks passed. No new unit tests
  were needed for this documentation-only change; existing launch blockers remain.

## Selectable terminal themes (2026-10-04)

- Added seven named palettes: Ghost, Dracula, Nord, Catppuccin, Amber, Paper (light)
  and Mono (grayscale). `ghost theme` browses them without requiring Git;
  `theme <name>` saves and switches; `--preview <name>` renders a labeled sample
  without saving, scanning or contacting a model. `--json` exposes active/saved
  appearance settings. Reset with `ghost theme ghost`.
- `/theme` opens a keyboard picker, including when selected from `/`. Prefix
  filtering, Up/Down, insert-before-submit and Esc match the provider picker.
  Dynamic prompt styles update without restarting the REPL. Rendering reads the
  palette at draw time across branding, guides, replies, findings, connection
  cards, histories, status, help and command discovery. Session, watcher and chat
  state remain available. `clear` redraws the welcome screen in the current theme;
  previous scrollback keeps its already printed colors.
- Paper paints printed content and input surfaces for legibility on dark host
  terminals; it does not change terminal font/background preferences. Mono keeps
  text severity labels. Code/diff rendering selects a compatible syntax palette.
  Truecolor input rendering follows COLORTERM; explicit prompt-toolkit color-depth
  overrides remain respected. Existing NO_COLOR and reduced-motion behavior is
  preserved; project command output is not recolored.
- Saves only the palette name in `$XDG_CONFIG_HOME/ghost/theme.json` or
  `~/.config/ghost/theme.json`. Writes are atomic and owner-only. Settings reads
  are bounded to 1 KiB, and symlinks, hardlinks, directories and FIFOs are rejected.
  Malformed preferences fall back safely and can be reset; invalid choices and
  failed writes preserve the current palette. `GHOST_THEME` overrides startup;
  an explicit selection applies now, with a notice about the next-launch override.
  Previews restore the current palette even when rendering fails.
- Verification: **190 tests passed in 82.14s**, covering new themes/preferences,
  existing branding, keyboard picker, workflow guidance, architecture, connections,
  session views, security audit views and scope. After final discovery/help/preview
  refinements, the affected theme, branding, picker and architecture suite passed
  **82 tests in 11.21s**. Tests include a fresh process for each saved theme,
  palette/syntax validation, actual input events, live existing prompt/console
  updates, 24/40/96-column plain previews and adversarial settings files.
- Installed global Ghost passed real macOS PTY checks at **24/40/96 columns** for
  all seven live palettes, selection without saving, explicit submission, preview
  without changing the saved choice, Esc, Ctrl-C and Ctrl-D. A separate 40-column
  NO_COLOR PTY listed/switched themes with zero escape codes. Disposable sample
  source and Git state stayed unchanged. Actual terminal records were inspected
  as PNGs, including light and narrow output; a seven-theme contact sheet is in
  `assets/themes-preview.png`. Preference files and raw captures remain excluded
  from Git. Wheel build and content inspection passed.
- Existing security/repair launch blockers remain. Real Windows/Linux terminals,
  terminal resize during a theme menu and platform-native preference conventions
  have not been exercised in this run. This change does not establish production
  readiness or broader vulnerability coverage.

## Provider picker and Claude Code login (2026-10-04)

- `/connect` now opens a contextual provider menu in the interactive REPL. It also
  follows selection of Connect from the slash menu. All seven choices include
  setup descriptions: Codex, Claude Code login, Claude API, OpenAI, compatible
  services, OpenRouter and local Ollama. Prefix filtering works; an exact provider
  name wins over longer matching names. Enter inserts the provider, then a second
  submission saves settings. Browsing never starts login or a model request.
- CLI and plain REPL output share the provider catalog, with readable setup hints
  at narrow widths. Codex and Claude Code reuse their installed CLI authentication
  and accept optional models. `claude` remains the Anthropic API connection;
  `claude-code` is the separate CLI login choice. Base URL/key-variable settings,
  including environment overrides, are rejected for CLI login providers.
- Added a Claude Code adapter for both text and structured JSON calls used by the
  agent harness. Print mode disables built-in tools, slash skills, Chrome, MCP
  servers, customization sources and session persistence. Safe mode is required;
  hooks are explicitly disabled. API credentials, backend switches and runtime
  injection variables are excluded from the inherited environment. Prompts go
  through stdin from an empty disposable directory. Admin policy still applies;
  this is a trusted CLI binary, not an OS sandbox.
- Extracted the existing Codex subprocess transport for both CLI adapters. Default
  limits remain 120 seconds, 1 MiB request and 1 MiB per output stream. Timeout,
  cancellation and oversized responses clean up the process group and temporary
  directory. Provider failures never expose raw stderr or response bodies.
- Verification: the final affected input, connections, Claude adapter, branding,
  guidance and architecture suite passed **105 tests in 33.29s**. Provider transport
  and evidence privacy checks passed **58 tests in 13.66s**. Cases cover malformed,
  incomplete, denied, error and oversized CLI responses; request privacy; minimum
  environment; stdin; flags; deadlines; cancellation; adapter routing; safe saved
  settings; nested menus and explicit submission. A final Claude adapter smoke run
  after help/test readability edits passed **12 tests in 9.08s**; installed
  `ghost connect --help` lists both Claude choices and optional CLI model settings.
- Real macOS PTYs using the globally installed `ghost` passed at **24/40/96
  columns**: all seven providers reachable, both Claude modes, insertion without
  saving, explicit provider submission, Ctrl-C and Ctrl-D. A 40-column `NO_COLOR`
  PTY showed the provider list without escape codes. Actual terminal output was
  inspected through a VT emulator and PNG renders. Isolated sample source and Git
  state remained unchanged. Wheel build/contents inspection passed; new provider
  and transport included, runtime captures excluded.
- Live Codex text and structured JSON requests passed. The installed
  `ghost connect codex --check --json` also passed in a disposable sample. The
  installed Claude CLI accepted the guarded invocation but returned an expired
  OAuth authentication error. `ghost connect claude-code --check --json` exited 2
  with `connection_tested: false` and safe login guidance. Successful live Claude
  text/JSON verification remains blocked on the owner running `claude auth login`.
  Anthropic API behavior was verified against a real loopback HTTP server; no
  live Anthropic API account request was made. Existing launch blockers remain;
  Windows/Linux CLI process behavior has not been exercised in this run.

## Slash command picker with keyboard navigation (2026-10-04)

- Added a local `prompt-toolkit` input adapter for interactive REPL terminals.
  Typing `/` opens all registered commands with descriptions, a scrollable list
  and a mint selection highlight. `/sol` filters to matching names; Up/Down
  navigate. Enter inserts the selection and closes the menu; a second explicit
  submission is required to dispatch. Esc restores the original input.
- Ordinary command names still support Tab completion. Natural-language input,
  arguments and cursor positions inside tokens do not open automatic completion.
  Input history is memory-only. External-editor, system-shell and suspend bindings
  are disabled. Submitted `/command` uses the existing guarded dispatch path;
  unknown slash commands cannot turn into model questions or echo arguments.
- Pipes, basic terminals and `NO_COLOR` keep a plain input path without screen
  control codes; submitting `/` prints the complete help list. Picker hints adapt
  to terminal width. Reduced motion disables decorative startup motion while
  preserving normal keyboard interaction.
- Verification: **79 tests passed in 27.85s** across picker input, branding,
  workflow guidance, provider connections and architecture. Actual input-event
  tests cover filtering, descriptions, arrow selection, Enter without execution,
  explicit submission, Esc restoring input, reopening the list and EOF cleanup.
  Slash dispatch and invalid arguments are covered alongside conversation tests.
- Real macOS PTYs using the installed global `ghost` at 24/40/96 columns reached
  all **29** registered commands by keyboard, filtered, inserted without running,
  submitted a read-only guide and completed Esc, Ctrl-C and Ctrl-D. A separate
  40-column `NO_COLOR` PTY printed `/` help with zero escape codes. Terminal output
  was inspected through a VT emulator with real cursor-position replies and PNG
  renders; source and Git changes in the disposable sample remained unchanged.
- Updated the local editable `ghost` installation with the input dependency.
  Built and inspected a wheel: adapter and declared dependency included; runtime
  captures and the terminal emulator used for verification excluded. Existing
  launch blockers remain; actual Windows/Linux and resize-during-picker behavior
  have not been exercised in this run.

## REPL startup and practical workflow guides (2026-10-04)

- The startup animation now materializes both the serif wordmark and the mascot,
  then blinks once before the prompt. It is decorative, not a loading or scan
  indicator. Pipes, basic terminals, `NO_COLOR` and `GHOST_NO_ANIMATION=1` skip
  motion. The welcome screen introduces Code / Review / Verify, with access
  checks as a separate configured action.
- Added `ghost guide [daily|review|repair]` and matching REPL `guide` commands.
  The overview presents three paths; each path explains concrete commands,
  expected use and evidence limits. Examples use the correct CLI or REPL prefix.
  Guides run no code, make no model requests and work outside a repository on
  the CLI. They are also available through help and REPL completion.
- Daily guidance distinguishes watched edits and Ghost-run commands from other
  terminal activity. Review guidance covers source scope and configured local
  access checks. Repair guidance explains supported Python recipes, executable
  verification, the default-No apply prompt and rescanning. Very narrow screens
  use unboxed steps so headings remain readable.
- Verification: **69 tests passed in 24.58s** across workflow guidance, terminal
  behavior, provider connections and architecture. New cases verify no side
  effects outside Git, actual command-parser acceptance of every step, recovery
  from invalid workflow arguments without echoing their values, 24/40/96-column
  layouts, partial logo reveal and immediate reduced-motion output.
- Real macOS PTYs at 96 (animated), 40 (`NO_COLOR`) and 24 (reduced motion)
  completed startup, all four guide views and exit. Checked animation cursor
  restoration, inspected rendered terminal output, and verified sample source
  and Git changes were preserved. `ghost demo --security` exited 0 after real
  mixed-stack findings, isolated Python verification, sample-only application
  and rescan; the unresolved TypeScript finding remained visible. Built a wheel
  and checked the new guide is included with runtime artifacts excluded.
- Existing launch blockers remain. Guides explain workflows; they do not infer
  that a review, scan or repair has completed. Actual Linux terminal behavior and
  resize-during-animation behavior have not been validated in this run.

## Serif identity and readable terminal replies (2026-10-04)

- Refreshed Ghost's shared identity with an ivory serif wordmark, soft mint
  mascot, lavender accents and consistent semantic status colors. The terminal
  draws static serif letterforms with cell pixels; SVG assets use Georgia with
  serif fallbacks. No font binaries or font installation are required. Body
  fonts remain the terminal application's setting; CLI output cannot choose a
  serif font for individual paragraphs without disrupting cell alignment.
- Made the welcome screen more compact, shortened long project paths, surfaced
  `ask` beside security commands and improved connection and finding cards.
  Severity, confidence, evidence state, full finding IDs and audit scope remain
  visible. Configured connections are not presented as live verification.
- Model replies and the offline capabilities guide now render paragraphs,
  headings, lists and fenced code. Model prompts encourage concrete, concise
  writing. Controls and direction overrides are escaped before parsing;
  hyperlinks are visible text rather than terminal links. Replies remain advice
  and cannot execute commands. Very narrow replies use an unboxed layout.
- Verification: the affected terminal, connections, security audit, scope and
  architecture suite passed **89 tests in 66.54s**. After final card spacing and
  text-weight refinements, terminal/security tests passed **48 in 46.97s** and
  connections passed **35 in 21.60s**. Adversarial reply cases cover 24/40/96
  columns, command preservation, ANSI/OSC/clipboard and bidi controls, and
  disabled clickable links. Existing motion and plain-output checks pass.
- Real `NO_COLOR` PTYs at 24, 40 and 96 columns completed welcome, offline
  capabilities, help and exit without styled controls or rendered output
  overflow. Built a wheel and inspected inclusion of the serif geometry and
  reply renderer, with no runtime artifacts or bundled font binaries.
- Captured actual 96-column REPL output including a live Codex reply, command
  help and connection settings. An isolated Python fixture produced a B307
  finding; `solve` reproduced function-call evaluation, rejected it after the
  patch, preserved three literal cases, passed three project tests and completed
  a Python rescan. Its developer checkout was not patched. Inspected rendered
  welcome, replies, finding cards and SVG branding; refreshed the README preview.
- Carried-forward launch blockers remain: scanner coverage is bounded, repairs
  are limited to supported Python recipes, application reachability needs
  configured executable evidence, and wider platform/provider validation and
  harness hardening are still required. This visual refresh is not evidence of
  production readiness.

## Conversational REPL and provider connections (2026-10-04)

- Prioritized the owner's report that `what can you do?` was treated as an unknown
  command. REPL prose now reaches a bounded conversation service; ordinary command
  dispatch, command-typo suggestions and explicit execution/patch gates remain.
  An offline capabilities guide answers that question without pretending a model
  is connected. `ask`, `connect` and REPL `forget` are discoverable in help.
- Added Claude Messages, OpenAI Responses, installed Codex CLI/login, OpenRouter,
  local Ollama and arbitrary OpenAI-compatible connections. No API model is fixed.
  Debugging uses the same provider selection. Existing three-variable compatible
  configuration still works; environment overrides are documented.
- `connect` saves only provider/model/endpoint/key-variable names in an atomically
  replaced owner-only `.ghost/llm.json`. It refuses linked/special settings files,
  URL credentials and remote plain HTTP. Keys stay in the environment. `--check`
  makes a real bounded request; configuration status alone is not a live check.
- Chat responses are literal advice, never executable Ghost actions. History is
  bounded, memory-only, cleared by `forget` or explicit provider selection.
  Repository context requires `ask --context`, which sends only a bounded saved
  audit summary without source, captured logs, finding titles, contract headers
  or markers. Recognized credentials are blocked before requests. Questions,
  answers and provider execution have byte limits and total deadlines.
- HTTP adapters share the existing bounded streaming transport. Codex is called
  in an empty disposable directory with explicit read-only/ephemeral flags,
  user configuration/rules disabled and a restricted inherited environment.
  Completed JSON events are required; failures, partial responses, oversized output,
  cancellation and timeouts are covered. Process groups are reaped on failure.
- Verification on macOS: focused connection, transport, architecture and terminal
  suite **81 passed in 34.57s** after the final recognized-credential settings guard.
  The broader suite passed **336 tests in 484.05s**, including actual isolated
  debugger, authorization and security repair scenarios. That run collected
  before the final connection/history/privacy refinements; the final affected
  81-test run above covers those changes and their added adversarial cases.
  Native/compatible API protocols exercised actual
  local HTTP servers without paid API keys. An installed Codex login passed a
  **live** request and the installed `ghost connect codex --check --json`; a real
  isolated-repository REPL answered two questions, preserved conversation, cleared
  history and left the checkout untouched. Inspected real 24/40-column `NO_COLOR`
  PTYs running the offline guide, connection status and command help, plus piped
  live Codex REPL output. Built a wheel and checked all new adapters were included
  with no runtime artifacts. Installed global `ghost ask --help` exposes the command.
- Carried forward the interrupted findings UI improvement: `--severity` and
  `--limit` focus saved static cards while retaining the full audit status, scope,
  severity counts and authorization evidence. JSON continues to export all findings.
  Filtering never turns an incomplete or nonempty audit into a clean report.
- Remaining limits: no live Claude/OpenAI/OpenRouter account checks or real Ollama
  service were available; local protocol fixtures are not remote-service validation.
  Chat does not autonomously run security reviews or fixes. Codex is a trusted
  external agent binary: its read-only sandbox permits broad reads, and the prompt's
  no-tool instruction is not a complete tool-access boundary. Service retention is
  governed by the account. Secret detection remains heuristic. Provider-independent
  deadlines were added for chat; harness-wide enforcement remains a blocker.
  Linux and resize/editing behavior were not exercised; Typer help still truncates
  some option text at very narrow widths. Release readiness is not established.

## Agent Git helper boundary (2026-10-04)

- Reproduced a guardrail bypass: an agent `git diff` accepted inherited
  `GIT_EXTERNAL_DIFF`, then executed a writable repository helper despite the
  read-only subcommand and active macOS OS sandbox. The synthetic helper wrote
  only a marker in an isolated test repository.
- Agent `git diff`, `show` and `log` now force `--no-ext-diff` and
  `--no-textconv`. Agent processes drop inherited `GIT_*` overrides, including
  checkout redirection, and disable Git terminal prompts. Interactive developer
  `ghost run` commands keep their existing environment and semantics.
- Verification on macOS: the execution, debugger and security workflow suites
  passed **75 tests in 242.67s**. Tests covered inherited and repository-configured
  external diff helpers and inherited checkout redirection. A real isolated
  macOS sandbox run of agent `git diff`, `show HEAD` and `log -p -1` completed
  with no helper marker despite both hostile configurations.
- Remaining limitation: local repository configuration, Git attributes,
  subcommands and environment controls need continued adversarial review. The
  OS sandbox still allows broad reads and is not a hostile-code boundary;
  Linux/bubblewrap behavior is untested.

## Literal watcher and history metadata (2026-10-04)

- The CLI watcher start/event view, session status and timeline now render
  repository, branch, filename and saved command metadata literally. Filenames
  containing ANSI, terminal clipboard controls, Unicode direction marks or Rich
  markup can no longer alter those screens. The watch start view keeps clear
  labels and folds long paths at narrow terminal widths.
- Reproduced raw terminal-control characters in the prior timeline view. The
  final brand, session and debugger suites passed **52 tests in 152.61s**;
  adversarial UI tests covered 24, 40 and 80 columns with `NO_COLOR`.
  After tightening the rendered-escape assertion, those three tests passed
  again in **0.53s**.
  A real isolated-repository `ghost watch` PTY recorded a file whose name
  contained an ANSI clear-screen sequence; the live event and subsequent
  redirected `ghost timeline` showed escaped text and no raw escape byte.
- Remaining limitation: other screens still need a complete audit for literal
  metadata and narrow-width behavior. This does not change what command output
  is saved in the local database, or protect a hostile repository from all
  filesystem and process interactions. Linux terminal behavior is untested.

## Safe live command output (2026-10-04)

- `ghost run` and `ghost retry` now escape terminal controls and Unicode direction
  characters in live stdout/stderr. Newlines and tabs remain readable. The live
  display follows the existing 64 KB per-stream capture limit and announces
  truncation; the command continues running to completion or timeout.
- Reproduced the prior issue with a command that emitted screen-clear and OSC
  hyperlink sequences: Ghost forwarded raw escape bytes before this change.
  After the change, a real isolated-repository CLI run under redirected output
  and a `NO_COLOR` PTY displayed literal escapes with no raw ANSI; the oversized
  redirected run showed a truncation notice and completed. The captured bounded
  stdout/stderr still contain the original bytes for local evidence.
- Verification on macOS: execution, retry, brand, core debugger and security
  workflow suites passed **100 tests in 262.49s**. A regression test covers
  chunk-split ANSI, OSC, carriage return, Unicode direction controls, stderr,
  raw evidence preservation, and bounded live output.
- Remaining limitation: raw command output remains in the local SQLite database
  and may contain secrets; live escaping is not secret redaction. Project code
  run explicitly through `run` or `retry` still executes in the working tree.
  Linux terminal behavior has not been tested.

## Source scope browser (2026-10-04)

- Added `ghost scope` to the CLI and REPL. It lists Git-visible Python and
  JavaScript/TypeScript candidates, known unreviewed source, excluded paths,
  unreadable or over-budget source and deleted tracked paths. It checks source readability
  without importing project code or running a scanner; `--json` exports the
  full categorized inventory, while terminal output limits each section.
- The screen explicitly says no scan ran and Gitignored paths are absent.
  It warns when candidate count or size may exceed a scanner budget and does
  not turn a path inventory into a security verdict.
- Verification on macOS: the scope, terminal brand and security audit suites
  passed **44 tests in 39.31s**. Tests covered Python/JS/TS selection, known
  unsupported source, tracked exclusions, symlinked sources, deleted files,
  scanner count budgets, Gitignored omissions, literal control-character paths,
  JSON/REPL output and no project-code execution. Real 24-column redirected
  and PTY `NO_COLOR` runs showed the scope screen without ANSI or overflow.
  Python compilation and a wheel build including the new command passed.
- Remaining limitation: source suffixes and readability do not establish that
  Bandit/Semgrep parsed or analyzed a file. Gitignored files are not enumerated,
  and `ghost find` remains the executable coverage check. Broader language,
  dependency and configuration coverage remains open.

## Authorization request-order check (2026-10-04)

- For both Python ASGI and Node handler contracts, Ghost now runs the configured
  owner/other requests twice, reversing actor and case order in a fresh worktree.
  It compares each actor's status and protected-marker observation. A changed
  result becomes inconclusive with an explicit note instead of proving an
  exposure or verifying a candidate from one process's request sequence.
- One authorization time budget now covers the repeated baseline and candidate
  runs; exhausted budget fails closed. The real checkout and contract remain
  unchanged, and each worktree is removed after its run.
- Verification on macOS: the Python counter-based example reproduced a false
  confirmation before the change. The final authorization suite passed
  **41 tests in 316.78s**, including Python and Node order-sensitive baseline
  and candidate cases, checkout isolation and a shared-deadline regression.
  A real 40-column `NO_COLOR` CLI run reported the changed request order as
  inconclusive with exit 2, no ANSI and no protected marker in output. Python
  compilation, Node syntax checking and a wheel build with both updated workers
  passed. Linux behavior remains untested.
- Remaining limitation: two orders cannot establish independence from every
  stateful behavior or external service. Each order still runs actors inside
  one project process, and OS confinement is not a hostile-code boundary.

## Authorization contract preflight (2026-10-04)

- Added `ghost auth --check` to CLI and REPL. It validates the private contract
  and safely reads the configured local app source without importing or running
  project code. `--json` returns bounded status, runtime, source path and case
  count without actor headers, protected markers or app contents.
- Missing markers, missing contracts and unsafe/symlinked app sources get
  actionable failures. The success card stays legible at 24 and 40 columns,
  under `NO_COLOR` and in the REPL. The command guide and runnable examples
  now show the preflight step before executing an authorization check.
- Verification on macOS: the authorization and terminal brand suites passed
  **46 tests in 109.14s**. After the final CLI adjustment, the
  preflight tests passed **7 tests in 4.94s**. A real 24-column redirected run
  and 24-column PTY run both showed the complete `ghost find --auth` next step
  with no ANSI, and an app that would raise on import was not executed. The
  wheel build and Python compilation passed.
- Remaining limitation: preflight does not resolve app imports or dependencies,
  execute routes, test the OS sandbox or prove access is safe. Use
  `ghost find --auth` for bounded local behavioral evidence.

## Protected-content authorization proof (2026-10-04)

- Cross-user checks now require a synthetic `protected_marker` in each local
  authorization case. The confined Python and Node workers inspect bounded
  response bodies in memory and return only owner/other marker-presence booleans.
  Ghost never saves the body or marker in the audit. The contract rejects a
  marker that appears in the request path or actor headers.
- An owner response without the protected marker is inconclusive. The other
  actor seeing that marker is a confirmed exposure even with HTTP 403; an
  expected 401/403/404 without it is denied. An unrelated HTTP 200 response
  without the marker is inconclusive instead of a false confirmation.
- Older status-only audit records load as incomplete/inconclusive, so historical
  evidence is not silently promoted to content proof. Existing local contracts
  must add a synthetic `protected_marker` to each case; malformed ones fail
  before project code executes.
- Verification on macOS: the final authorization suite passed **29 tests in
  89.45s**, including Python and Node checks where an unrelated HTTP 200 must
  stay inconclusive, a leaking HTTP 403 must be confirmed, an owner response
  without the marker must be inconclusive, old SQLite audit records must load
  conservatively, and candidate fixes must leave the checkout unchanged.
  The adjacent security audit, security workflow and terminal brand suites
  passed **60 tests in 114.96s**.
  A real 40-column `NO_COLOR` CLI run and 40-column PTY run both showed the
  new marker observations with exit 1, no ANSI and no leaked marker. The wheel
  build succeeded and contains both updated workers. Linux remains untested.
- The later request-order check detects inconsistent results across opposite
  request orders. It does not cover all stateful handlers or external services.
  A marker can prove only the configured resource content and actors. Broader
  data-flow and tenant isolation coverage remain open.

## Terminal experience pass (2026-10-03)

- Reworked the REPL welcome and command guide for narrow terminals. At 24–40
  columns they now show concise starting actions and grouped command names,
  without breaking descriptions into unreadable fragments. Wider terminals
  retain short explanations. `help <command>` also covers REPL-only commands.
- Unknown commands suggest a close match without echoing arbitrary arguments.
  Repository and branch labels escape terminal control and direction characters.
- `NO_COLOR` now disables styling sequences in Ghost screens and Typer help on
  a real TTY while keeping its measured width. Reduced-motion and redirected
  output continue to avoid decorative animation.
- Updated the README terminal preview from the current welcome screen and
  rendered the SVG to PNG for visual inspection. Real 40-column no-color REPL,
  80-column no-color help, and 80-column styled/reduced-motion PTY runs passed.
  The full suite passed **270 tests in 626.86s** on macOS. After the final Typer
  no-color and explicit `clear` adjustments, the focused terminal/REPL suite
  passed **11 tests in 8.14s**. A no-color PTY `clear` run then confirmed the
  screen cleared and the welcome view redrew.
  `git diff --check`, Python compilation and SVG parsing passed; the wheel
  includes the new terminal module. Linux PTY behavior remains untested.

## Configured cross-user access proof (2026-10-03)

- `ghost auth --init` writes a private example contract under ignored `.ghost/`.
  A developer defines synthetic owner and other-user headers and a local GET route.
- `ghost find --auth` runs those requests against a Python ASGI app or a CommonJS
  request handler in an OS-confined disposable worktree. It records status codes,
  scope, marker-presence booleans and verdict, not headers or bodies. Owner
  failure, timeout, unavailable runtime, malformed results or disabled
  confinement make the check incomplete.
- `ghost auth --prepare-candidate` copies the app into a private proposed-fix file.
  `ghost auth --candidate` runs the baseline and proposed app in **separate fresh
  worktrees**, then verifies that an observed cross-user failure is denied while
  the owner still succeeds. The tested candidate hash is saved. The real checkout is not changed; its active failure
  keeps exit 1 until the developer updates it and reruns the check.
- CLI and REPL help, JSON persistence, narrow/no-color output and Python/JS
  examples document the supported behavior. The tests use a real FastAPI app and
  a local Node handler; both demonstrate confirmed exposure before the fix and
  expected denial after it.

This is a developer-authored local contract, not automatic IDOR discovery, a live
network test, or general Express support. It runs trusted project code with OS
confinement that still allows broad file reads. No claim of universal security
coverage or production readiness follows from a passing case. Broader tenant and
authorization workflows remain open.

Verification on macOS: the full suite passed **262 tests in 325.05s**. After
adding a world-readable-contract and malicious-candidate regression, the focused
authorization suite passed **21 tests in 62.71s** after the final candidate-hash
recording change. A fresh wheel install
included both worker files and the `auth` command. Its installed CLI ran the Node
sample end to end: baseline confirmed, candidate denied, real checkout unchanged,
worktrees cleaned. No-color terminal output showed both cards without ANSI. The
test fixture also used a real FastAPI app for Python. This is evidence for the
configured examples, not measured recall on real projects. Linux remains untested.

## Current product direction — security first (2026-10-03)

The owner selected **Python and JavaScript/TypeScript, with Python fixes first**.
Primary workflow: explicit `watch`/`run` context → `find` → inspect `findings` →
`solve <id>` → executable verification → approval. Keep CLI/REPL polish and useful
commands recurring priorities. The existing debugger remains available; new work
should prioritize security proof, useful coverage, triage and safe repairs.
Do not claim all-terminal capture, universal vulnerability discovery, or better
accuracy than competitors without benchmarks. Capture remains explicit. The
previously recorded Ghost Security naming overlap still requires an owner decision.

### Implemented in the security pivot

- `find` checks Python with Bandit and JS/TS with four local Semgrep rules, saves
  per-engine coverage and a bounded session metadata summary, and rejects source
  changes between engine runs. `audit` retains the Python-only path.
- The JS worker strips inherited Semgrep controls, disables metrics/version checks,
  uses trusted bundled configuration, ignores project suppressions, and executes
  under existing OS confinement. The macOS profile now permits read-only system
  metadata (`sysctl-read`) required by the scanner; write/network denial remains.
- A constant-false parse coverage rule forces JS/TS parsing even without security
  keywords. This closes a demonstrated incomplete-parse accounting gap; strict
  scanner errors prevent a passing review. Four security rules are unchanged.
- `solve` supports one deliberately narrow Python B307 literal-parser recipe.
  Passing baseline tests, original/modified trusted helper probes, unchanged
  project files, matching positive test counts with no skipped cases, Python
  rescan and fresh checkout identity are required. No LLM statement is used as proof.
  Tests run only in isolated worktrees; the checkout lock includes approval/apply.
- `solution` retains repair evidence separately from static candidates. The source
  audit always remains suspected. Noninteractive repair defaults to no application;
  `--apply` is explicit authorization. Unsupported/stale/failed repairs are persisted.
- CLI and REPL now lead with security commands. README, terminal preview and logo
  tagline reflect the new direction. `demo --security` runs mixed-language scanning,
  Python reproduction/repair and post-application rescanning in its generated sample.

### Scope still missing

This is a first security repair, not a general vulnerability-fixing agent. The
probe establishes helper behavior only, not attacker input or remote reachability.
It intentionally narrows expression evaluation to literals; `literal_eval` is not
resource-exhaustion protection. Project tests are trusted code. Summaries/counts
are imperfect coverage evidence and do not defeat malicious test output. No new
regression-test file is retained in the project yet. JS/TS repairs, framework-aware
automatic authorization/tenant discovery, dependency CVEs and benchmarked triage remain open.

Repair validation reads at most 1,000 regular project files, 512 KB each and 16 MB
total, after worktree creation. Five subprocesses are bounded to 120 seconds each.
Initial worktree copying, source signatures, Git operations and cleanup are not
covered by a single wall deadline. Read confidentiality, detached processes,
transaction durability and Linux execution coverage remain existing blockers.

### Verification completed for the security pivot

- Full suite on macOS: `pytest -q` — **243 passed in 286.76s**. This includes the
  prior debugger, sandbox, persistence and terminal tests plus new real scanning
  and isolated repair cases. This run preceded final presentation and error text
  changes.
- Focused security, architecture and brand suite after those changes:
  **54 passed in 100.28s**. One final CLI regression for the stale finding error
  passed separately (**1 passed in 9.30s**) after the last error handling edit.
- Ran `ghost demo --security` from a fresh installed wheel. It found Python and
  TypeScript candidates, reproduced and verified the Python repair in a worktree,
  applied it only to the generated sample, then rescanned. The TypeScript candidate
  remained open. A generated fixture also confirmed that declined interactive
  approval leaves the developer checkout unchanged.
- A real Semgrep parse error (`eval(!!!!`) returned an incomplete result; an
  earlier malformed TypeScript fixture exposed a prefilter gap, which the bundled
  parse coverage rule closed. An inherited Semgrep baseline/configuration override,
  project suppressions, no tests, skipped/failed tests, unsafe parser shapes,
  stale source, checkout changes and test-induced source mutation were exercised.
- Fresh wheel installation and the global editable installation both included
  Semgrep 1.179.0 and the CLI commands. `ghost doctor --json` passed the actual
  macOS sandbox probe after the profile change: local writes worked, outside writes
  and network binds were denied. Linux/bubblewrap was not executed.
- Inspected real interactive/no-color REPL output and a rendered terminal preview;
  `git diff --check` and Python compilation passed. No package was published.

This evidence supports the bounded workflow above, not production readiness or
complete vulnerability detection.

## Completed in the first hardening pass

- Added a per-investigation execution harness: a default 600-second time budget, 24 experiment/verification commands, 120 seconds per command, and 64,000 captured bytes per stream. `ghost debug --time-budget` and `--max-commands` expose the principal limits.
- Added cooperative cancellation: command workers observe cancellation, terminate their process groups, and finish worktree cleanup before the snapshot is removed. Final state and command counts are persisted, including cancellation and exhausted budgets.
- Fixed timeout handling when a command closes stdout/stderr while continuing to run. Pipe draining is bounded after the deadline; output truncation is observable.
- Rejected several concrete command-policy bypasses: versioned Python inline execution, attached inline flags, absolute-path Git mutations, Git option overrides/output writes, execution wrappers, and versioned Python package installation.
- Isolated internal Git operations from inherited `GIT_*` environment overrides and disabled Git hooks/fsmonitor for those operations.
- Made timed-out or signal-terminated experiments inconclusive, including reproduction. They cannot establish a high-confidence root cause.
- Added `ghost doctor` / `doctor` and JSON output. The sandbox check executes a controlled probe: writes inside its own temporary directory must work; writes outside and host network access must fail.
- Protected snapshot cleanup when recording an investigation event fails; failed investigations retain their final status.
- Refined the session panel and diagnostic screen with consistent colors, typography, and literal rendering of repository metadata. Saved reports show execution state and command usage.

## Verification for this pass

- Targeted command-policy, timeout, cancellation, command-budget, Git-scope, and diagnostic tests passed on macOS.
- The existing executable investigation test passed after harness integration.
- `ghost doctor --json` passed an actual macOS sandbox write/network probe.
- Full suite: `pytest -q` — 56 passed in 131.08 seconds.
- Additional deadline regression: `pytest -q tests/test_execution.py -k expired_investigation_time_budget` — 1 passed, 22 deselected in 3.11 seconds. This test was added after the full-suite run; application code was unchanged.
- `ghost demo` completed the real isolated investigation and verification pipeline successfully, then removed its sample repository.
- Globally installed `ghost doctor --json` and `ghost debug --help` exposed the new diagnostics and budget controls.
- The Rich diagnostic screen was rendered and visually inspected; `git diff --check` and Python compilation passed.
- These results were obtained on macOS. Linux sandbox behavior remains unverified in this pass.

Time budgets are cooperative around filesystem/Git operations. Cleanup can extend past the budget. The built-in HTTP provider has a total request deadline; an uncooperative third-party provider still needs additional deadline enforcement. Command screening is defense in depth; process confinement is the execution boundary.

## Completed in the provider transport pass

- Bounded serialized model requests and raw HTTP responses to 1 MiB each by default, with validated `ProviderLimits` for embedded clients. Oversized requests fail before network access; oversized responses stop streaming and close the connection.
- Added a 60-second total deadline across connection setup and body streaming, including servers that continuously send small chunks. Cancellation propagates and closes the response.
- Refused redirects and compressed response bodies. The client requests identity encoding to avoid decompression before enforcing its byte limit.
- Required complete, nonempty text responses (`finish_reason: "stop"`), valid JSON without non-finite numbers, and JSON objects for tool responses. Existing agent models retain responsibility for field validation.
- Replaced HTTP error details with bounded messages that omit provider bodies, endpoint URLs, and transport exception text. This does not redact outbound prompts or other local logs.

### Verification for the provider transport pass

- `pytest -q tests/test_provider.py`: 32 passed in 6.79 seconds. Includes response/request limits, multibyte request accounting, compression refusal, malformed/nested JSON, HTTP errors, redirect refusal, transport error privacy, cancellation, and deadlines.
- A real loopback HTTP server continuously sent chunks; the total deadline terminated the request and closed the connection.
- An actual isolated investigation reproduced a regression and identified its cause, then refused an incomplete model patch response. The developer source signature was unchanged and no worktrees leaked.
- Full suite: `pytest -q` — 89 passed in 150.07 seconds on macOS, including the guided demo and existing worktree isolation/approval checks. No external model service or real API key was used.
- `git diff --check` and Python compilation passed. Linux sandbox behavior was not tested in this pass.

## Completed in the session browsing pass

- Added `ghost sessions` / REPL `sessions` with bounded listing, local start times, branch names, honest open/ended labels, and `--json` output containing full IDs.
- Added `--session` / `-s` to status, timeline, failures, and report. Exact IDs and unique literal prefixes resolve historical sessions; missing or ambiguous IDs fail with recovery guidance. Browsing does not switch the current session or its watcher.
- Added a responsive mint/violet history screen: wide tables, narrow cards, actionable empty states, and command hints. The new screen escapes control and bidi formatting characters in metadata, renders Rich markup literally, and stays static for interactive and piped output.
- Added REPL command discovery and documented historical-session examples. Existing commands still inspect the latest session when no selector is supplied.

### Verification for the session browsing pass

- `pytest -q tests/test_sessions.py tests/test_brand.py`: 15 passed in 7.13 seconds. Covers historical selection across all four inspection commands, JSON output, empty history, ambiguous/missing IDs, SQL wildcard/injection strings, bounded lists, metadata controls, and a live REPL watcher that stays on its original session.
- Rendered and visually inspected the colored screen at 40 and 100 columns; automated layout checks passed at 24, 40, 80, and 120 columns with ASCII/no-color output.
- Exercised `watch`, `sessions`, historical `status`, `help sessions`, latest `status`, and `exit` through an actual PTY REPL with reduced motion. The watcher continued during history inspection and stopped on exit.
- The installed `ghost sessions --json` returned parseable JSON without terminal controls from a disposable sample repository.
- Full suite: `pytest -q` — 101 passed in 146.10 seconds on macOS, including existing isolated debugging and guided-demo checks. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the single-file patch installation pass

- Reproduced two defects before implementation: patch application converted CRLF to LF and followed an in-repository symlink to modify its referent. Both regressions now pass.
- Moved patch installation into a deterministic filesystem tool. It validates all hunks for one target, stages complete bytes beside the target, flushes and syncs them, and uses atomic rename for replacements. Failures before installation preserve the original target; temporary files are removed during normal exception handling. Failures during post-install cleanup and crashes still require recovery work.
- Existing permission bits and uniform CRLF endings survive replacement. Newly created files use owner-only mode and an exclusive link operation that refuses to overwrite concurrent file creation. Binary, oversized, hardlinked, special-permission, protected, and non-regular targets are rejected.
- Directory descriptors and no-follow opens reject symlink traversal. Preparation checks verify the directory chain and file identity/content before committing; edits observed during that preparation stop installation. This is optimistic conflict detection, not atomic compare-and-swap or hostile-filesystem containment.
- Multiple replacement hunks in one file are supported. Multi-file batches and combined create/delete sequences are rejected before mutation until transaction recovery is available. Ghost's current causal fixer already restricts proposals to one file.
- The watcher ignores reserved `.ghost-patch-*.tmp` staging names while still observing the installed target.

### Verification for the single-file patch installation pass

- Before implementation: the CRLF and symlink regression tests both failed, demonstrating the existing defects.
- `pytest -q tests/test_patch_application.py`: 21 passed in 0.22 seconds. Covers partial writes, fsync/rename failures, editor writes during preparation, parent symlink swaps, concurrent creation, multi-file rejection, multiple-hunk validation, nested creation/deletion, cleanup, protected paths (including case variants), hardlinks, and watcher filtering.
- Full suite: `pytest -q` — 122 passed in 142.13 seconds on macOS, including real worktree investigations, provider-generated fixes, explicit approval, source protection, and the guided demo. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the investigation history pass

- Added `ghost investigations` and REPL `investigations` with bounded results, session selection, full-record JSON export, responsive tables/cards, and actionable empty states.
- Added `ghost report --id` for exact IDs or unique literal prefixes. ID lookups search the repository's sessions unless explicitly restricted by `--session`; invalid, ambiguous, or mismatched selections never fall back to a different report.
- Reproduced and fixed the saved-investigation ordering bug: updating an old investigation previously changed its SQLite row ID and made it appear latest. Saves now update existing records in place, and listing/latest queries use recorded start time with a deterministic ID tie-break and a matching index.
- Shared literal rendering across the session/history views and saved reports. Model text, experiment conclusions, command names, patch excerpts, and notes escape terminal/direction controls. Patch labels require recorded successful verification and reject timed-out verification details. These are saved results, not a fresh verification or liveness check.

### Verification for the investigation history pass

- Before implementation, the regression test confirmed that updating an older investigation incorrectly changed the latest report.
- `pytest -q tests/test_investigations.py tests/test_sessions.py tests/test_brand.py`: 30 passed in 7.53 seconds. Covers history ordering, selection/scoping, literal SQL prefixes, malformed/ambiguous selections, empty history, JSON, REPL discovery, saved-report control characters, patch labels, and layouts from 24 to 120 columns.
- Rendered and visually inspected colored history screens at 40 and 110 columns with synthetic saved-record fixtures. Exercised listing, selecting a stopped report, command help, and exit through an actual reduced-motion PTY REPL.
- The installed CLI returned valid, control-free JSON for the history list and a selected report in a disposable repository.
- Full suite: `pytest -q` — 137 passed in 140.25 seconds on macOS, including the existing real debugging, approval, isolation, and demo checks. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the investigation locking pass

- Reproduced concurrent entry: two investigations could enter the same checkout simultaneously. Added a nonblocking OS advisory lock before investigation persistence or snapshot creation.
- The lock covers the entire investigation, approval/application, worker drain, worktree cleanup, and final persistence. A competing CLI/REPL request returns a clear “Investigation not started” message and exit code 2 without creating a second investigation.
- Uses a persistent, empty `.ghost/investigation.lock` file opened without following symlinks; non-regular and hardlinked files are rejected. The file is never unlinked during normal operation, preventing different contenders from locking different inodes. Descriptor inheritance across exec is disabled.
- Process exit releases the OS lock; leftover lock-file existence is not used as a liveness indicator. Different checkout directories remain independent. Advisory locking coordinates cooperating Ghost processes, not editors or hostile lock-file replacement.

### Verification for the investigation locking pass

- The concurrency regression failed before implementation, confirming that the second investigation previously entered and persisted.
- `pytest -q tests/test_investigation_lock.py`: 11 passed in 0.44 seconds. Covers same-process overlap, separate-process exclusion and force-kill recovery, cancellation through worker cleanup, exception/final-persistence failure release, persistent inode reuse, independent checkouts, symlinks/hardlinks/FIFOs, and CLI/REPL recovery guidance.
- Full suite: `pytest -q` — 148 passed in 141.76 seconds on macOS, including real debugging, approval, isolation, and demo checks.
- With a separate process holding the lock, the installed CLI in a real terminal returned exit 2 and actionable guidance; it created no investigation, source edit, or worktree. After release, the installed CLI reproduced a real sample failure, verified and applied its fix, and cleaned all experiment worktrees.
- `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the model evidence privacy pass

- Confirmed the previous file reader exposed a synthetic `.env` credential; the new reader rejects that path. Common credential files/directories are excluded from source reads, listings, and searches, including aliases that resolve to credential paths.
- Added a provider-independent request check at both built-in agent reasoning call sites. It checks system text, evidence, and schemas before invoking a provider; the HTTP provider additionally checks explicitly configured API credentials against message content.
- Recognizes selected secret-named environment values (eight or more characters, including JSON-escaped forms), private-key headers, selected token formats, and quoted credential assignments. Blocks the entire request with a content-free reason; deterministic analysis can continue without sending redacted source for patch generation.
- Model patch proposals refuse credential paths even when the source file was deleted. This does not prevent deterministic local analysis, raw Git access, or sandboxed commands from accessing local evidence.

### Verification for the model evidence privacy pass

- Reproduced `.env` disclosure using the pre-change reader from Git against a synthetic fixture, then confirmed rejection by the new reader.
- `pytest -q tests/test_privacy.py tests/test_provider.py`: 57 passed in 7.11 seconds before the added local-fallback integration test.
- `pytest -q tests/test_privacy.py`: 26 passed in 6.47 seconds. Covers path exclusions, symlink aliases, quoted/multiline/Unicode environment values, credential patterns, system/schema boundaries, zero HTTP-client/provider invocation on rejection, and unchanged transmission of ordinary evidence.
- A real isolated investigation with a synthetic credential in runtime output made zero model calls, reproduced the bug, established a cause, verified a patch, left developer source unchanged, and cleaned its worktrees.
- Full suite: `pytest -q` — 174 passed in 145.34 seconds on macOS, including the final deleted-credential-file check, existing provider/guardrail tests, real investigations, and guided demo. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## OpenSRE-style source layout — 2026-10-02

Completed the owner's request to organize Ghost like the local OpenSRE project,
using its canonical architecture document as the reference:

- Moved the working implementation into `surfaces`, `bootstrap`, `core`,
  `infrastructure`, and `config`; removed the old `ghost/` package without adding
  forwarding modules. Existing CLI commands and `.ghost/` storage formats remain
  unchanged.
- Separated CLI/REPL composition in `surfaces/entrypoint.py`, session/provider
  composition in `bootstrap/runtime.py`, domain types in `core/domain`, and
  persistence, repository operations, masking, guardrails, and sandbox mechanics
  in `infrastructure`. Added the canonical source map in `docs/ARCHITECTURE.md`.
- Removed the core's import of terminal UI through a task-local progress callback;
  actual CLI/demo operations still receive the existing accessible activity UI.
  Some Rich tables and approval rendering remain in the orchestrator, documented
  as future presentation-decoupling work.
- Added an AST import-boundary test to reject upward dependencies, CLI/REPL peer
  imports, and retired `ghost.*` imports. Updated all test/example imports,
  monkeypatch paths, wheel package inclusion, and the console entrypoint.

Verification:

- Full macOS suite: `.venv/bin/python -m pytest -q` — **175 passed in 162.75s**,
  including real isolated investigations, adversarial safety tests, approval
  protection, persistence/history, and the new architecture check.
- Built a wheel with `uv build --wheel`, installed it in a fresh temporary virtual
  environment, and ran `ghost --help` and the complete `ghost demo` from `/tmp`.
  The demo reproduced the bug, established causal evidence, verified/applied the
  sample fix, passed both tests, and removed its worktrees/sample repository.
  Isolated Python imports confirmed packages loaded from the wheel's site-packages.
- Inspected a real PTY REPL (`help`, `status`, `exit`) and a piped 40-column REPL
  (`help status`, `sessions`, `exit`) with no color/reduced motion; the latter
  exited successfully with no ANSI escapes. Refreshed the development editable
  install and the user's global uv tool install, then checked `ghost repl --help`.
- Python compilation and final staged whitespace checks passed. This was local
  macOS verification; Linux and automated clean-install CI remain outstanding.

Later passes should use the canonical packages and preserve the checked dependency
boundaries. Reinstall older editable checkouts to refresh their entrypoint.

## Retry command and terminal workflow — 2026-10-02

- Added `ghost retry` and REPL `retry` to repeat the latest session's newest
  completed failure in the current checkout. `--dry-run` shows and validates the
  exact saved command without subprocess execution or new run events; `--timeout`
  defaults to 120 seconds. The command uses the same parsing/execution guards as
  `ghost run` and clearly identifies its current-working-tree semantics.
- Added a database query that selects failures by insertion order without a
  timeline-window cutoff. It excludes successful/incomplete commands and test
  summary/error events. It never falls back to an older session. Execution opens
  a new session if the source session ended; previews leave sessions untouched.
- New start/finish/error events retain the source session and failure timestamp
  as retry metadata. Commands retain their original quoting. Failures, timeouts,
  launch errors, and signal exits return observable exit statuses; successful
  execution is reported only after the actual command passes.
- Added a responsive command preview with literal rendering of saved metadata,
  safe handling of terminal/direction controls, and clear result/next-action text.
  CLI help and the REPL guide/completion expose the new command. Documented
  examples, scope, timeout behavior, and exit codes in the README.

Verification:

- Focused initial suite: retry, architecture, sessions, and execution tests —
  **53 passed in 27.50s**. Added one further signal/launch-error regression test
  afterward; the full-suite result is recorded below.
- Real installed CLI flow in a temporary Git project: captured failing unittest
  command, previewed without adding events, retried and reproduced the failure,
  ran `ghost debug --apply` with the model disabled, then retried successfully.
  The real investigation verified/applied the sample fix and cleaned its worktrees.
- Inspected piped 40-column/no-color/reduced-motion preview and success output;
  no ANSI escapes in the preview. Tests cover widths 24/40/80 with hostile saved
  command text, quote preservation, stdout/stderr capture, missing or blocked
  commands, ended/empty sessions, bounded execution, and REPL dispatch.
- Full macOS suite: `.venv/bin/python -m pytest -q` — **193 passed in 174.16s**.
  A real PTY REPL also passed `help retry`, `retry --dry-run`, `retry`, and `exit`;
  the retry executed both sample tests successfully. Python compilation and
  whitespace checks passed. Linux was not exercised in this pass.

Limitations: this is explicit developer-command replay, not sandbox execution.
As with `ghost run`, scripts run against the current working tree/environment.
Live stdout/stderr now escapes terminal controls as documented above; captured
output remains raw local evidence. Saved source session and timestamp are
provenance context, not a globally unique event identifier.

## Security direction and competitive research — 2026-10-02

The owner asked whether comparable products exist and authorized improvements
that make Ghost competitive as a pre-deployment security tool. Primary sources
show substantial overlap:

- [Ghost Security](https://ghostsecurity.ai/) already markets security agents and
  [AppSec tools](https://github.com/ghostsecurity). This creates a concrete naming
  and positioning overlap to review with the owner before launch. No trademark
  conclusion or automatic rename is implied.

- [Semgrep Agentic Workflows](https://semgrep.dev/products/semgrep-agentic-workflows/)
  advertises detection, dynamic validation, triage, and fixes. Its
  [workflow documentation](https://semgrep.dev/docs/workflows/overview) describes
  IDOR/authorization workflows and combining deterministic tools with agents.
- [Shannon](https://github.com/KeygraphHQ/shannon) describes source analysis and
  executable exploit validation for web applications and APIs.
- [Snyk CLI](https://snyk.io/platform/snyk-cli/) covers local and CI security checks;
  [its remediation-agent announcement](https://snyk.io/blog/snyk-remediation-agent-in-the-cli/)
  describes terminal-based dependency remediation.
- [Aikido](https://www.aikido.dev/blog/ai-pentesting-agent-security) documents
  enforced target scope and agent isolation. Its
  [local scanner](https://www.aikido.dev/code/local-scanner) also addresses local
  operation, so local-first execution alone is not a unique differentiator.

These are vendor-described capabilities, not an independently executed comparison.
Ghost must earn comparative claims through shared fixtures, measured false
positives, reproduced vulnerabilities, legitimate-behavior regression tests,
resource budgets, and privacy/scope checks. No superiority claim is supported yet.

### Shipped security foundation

- Added `ghost audit` and `ghost findings`, including JSON, finding-ID inspection,
  REPL help/dispatch, bounded terminal cards, and explicit coverage/evidence labels.
- Uses Bandit's established Python rules with no model/API key. Source is copied
  into a disposable bounded snapshot and scanned under OS confinement. Python
  isolated mode prevents project modules/sitecustomize from being imported.
  Project scanner configuration and nosec comments cannot silently suppress findings.
- Persisted findings contain rule/CWE, source location/hash, severity, scanner
  confidence/version, and the static/suspected evidence state. Raw code excerpts
  and issue messages that may contain password literals are not persisted.
- Missing/unsafe source reads, malformed reports, skipped scanner accounting,
  syntax errors, disabled sandbox, timeout, output limits, and detected source
  changes cannot produce a completed passing result. Other languages are explicitly
  outside the Python scope. No targets are contacted and no fixes are applied.

Verification so far: focused audit/architecture suite **28 passed in 29.60s**,
including six vulnerable/safe rule pairs (evaluation, pickle, YAML, shell execution,
weak hashing, and TLS verification), adversarial source/config cases, CLI/REPL
integration, private-literal omission, and 24/40/80-column rendering. This is a
regression suite for Ghost's behavior, not a benchmark win over competing engines.

Final verification:

- Full suite: **220 passed in 209.97s** before the final concurrent-runtime-artifact
  guard. The final audit/architecture suite then passed **29 tests in 33.72s**,
  including the added test proving `.ghost` activity does not invalidate source
  inventory. The updated security-first welcome screen passed all **3 brand tests**.
- Built and installed a wheel in a fresh temporary environment. The installed CLI
  detected the evaluation finding, returned 0 after a manual safe replacement,
  and returned 2 for malformed Python. Inspected real 40-column/no-color output
  and a PTY session running `audit`, `findings`, and `help audit` without losing
  the REPL on the findings exit code. Rebuilt the wheel after the final changes.
- Six rule pairs were scanned as source without installing their framework
  dependencies or executing their modules. A malicious source import side effect
  and repository `sitecustomize.py` were not executed. Secret-literal omission
  and persisted JSON round trips passed. Existing isolated debugging integration
  scenarios passed in the full suite. Linux was not exercised in this pass.
- The global editable installation now includes Bandit and the new commands.
  Scanner version used here: Bandit 1.9.4. No package was published.
- Ran the installed command against Ghost's own repository: 80 Python files,
  completed under OS confinement, exit 1 with 436 static candidates (3 medium,
  433 low). Of these, 403 are Bandit B101 assertion findings, largely in tests;
  these counts are not confirmed vulnerabilities. Added severity-first ordering
  and severity totals so higher-risk candidates are not buried in the first
  20 cards. Context-aware triage remains a concrete product gap.
- After the final ordering/UI changes, audit/architecture/brand checks passed
  **33 tests in 31.75s**. Rebuilt/reinstalled the final wheel and exercised piped
  REPL audit/findings/exit, confirming the security welcome shortcut, severity
  totals, successful exit, and no ANSI output. Compilation and whitespace checks
  passed.

### Next security milestones

1. Expand authorized local application contracts beyond one GET path and actor
   pair, retaining legitimate access checks and measuring false negatives.
2. Connect security findings to isolated investigation and patch verification with
   separate suspected/reproduced/fix-verified states; never promote static evidence.
3. Expand language/dependency coverage based on an explicit supported-stack policy,
   and measure recall/false positives/cost on a versioned benchmark before marketing
   comparative accuracy. Existing providers' breadth exceeds this first Python pass.
4. Continue UI/CLI improvements and execution/privacy hardening under the existing
   architecture boundaries. Audits should become a first-class recurring priority.

## Remaining launch blockers, in priority order

1. **Private data and model boundaries.** Credential-path exclusions, heuristic request blocking and cooperative model deadlines are now covered, but are not complete secret detection or hostile-provider containment. Add configurable policy, broader secret/encoded-value coverage, local output/history handling, containment for blocking or cancellation-resistant custom providers, and adversarial prompt-injection tests. Short/unrecognized/transformed secrets may still leave the machine; raw Git evidence and sandbox snapshots are not scrubbed. The OS sandbox permits broad reads needed by runtimes. Review credential access before claiming hostile-repository containment.
2. **Patch application durability.** Add crash recovery and durable transaction journaling before enabling multi-file application. Sync directory metadata for power-loss guarantees, recover orphaned staging files, and preserve ACLs/extended attributes/ownership where supported. Single-file staging, permission bits, CRLF preservation, and preparation-time conflict checks are now covered. A concurrent replacement/delete after the final check remains a race; coordinate writers or use stronger platform-specific primitives before claiming atomic compare-and-swap.
3. **Evidence integrity.** Debugger capture completeness and confinement gates now preserve failure metadata and reject incomplete verification. Compare normalized failure signatures across control/reversal/repeat runs; detect changed or skipped test coverage. Add multi-file, committed-regression, nondeterministic, missing-dependency, and malicious-output evaluation cases. Persist provenance and failure reasons consistently.
4. **Process and sandbox coverage.** Exercise Linux/bubblewrap in CI. Test detached descendants, signal storms, oversized/binary output, and sandbox backend failure. Process groups do not provide complete containment of deliberately detached descendants on every platform.
5. **Persistence and concurrency.** Investigation exclusion for one checkout is now covered by an OS lock. Add crash recovery, database schema migrations, interrupted-run recovery, and cleanup diagnostics for orphaned worktrees; OS lock release alone does not recover those artifacts. Extend coverage of overlapping watch/run/debug processes, linked checkouts, and filesystem/platform locking behavior.
6. **Packaging and release gates.** Add supported-platform CI, reproducible package builds, clean-install smoke tests, dependency review, and release/versioning documentation. Choose a license with the owner before distribution terms are advertised.
7. **Terminal polish and accessibility.** Test resizing, very narrow terminals, long editable commands with macOS readline/libedit, color contrast, and reduced motion. Extend literal metadata handling beyond session/history/saved-report views. Live command controls now escape safely; test more real command output formats and expand consistent actionable empty/error states beyond session browsing.

## Working rules for later passes

- Read current Git state and this document before choosing work; avoid repeating completed fixes. The hourly automation is active.
- Reproduce a concrete failure or unmet requirement, implement a coherent change, then add meaningful regression coverage.
- Run the affected end-to-end path. Broaden testing for changes to execution, isolation, persistence, or patch application.
- Record the exact checks performed and distinguish platform behavior actually tested from code paths only reviewed.
- Do not label Ghost production-ready while blockers remain. Review and commit completed, verified improvements, then push to the existing GitHub origin without force. The owner authorized GitHub pushes for this manual work. Preserve unrelated user changes and exclude secrets and runtime artifacts. Package releases still require separate authorization.
