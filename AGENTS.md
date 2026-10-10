# Ghost contribution rules

These rules apply across this repository.

- Read `docs/source-provenance.md` before adding external material or dependencies.
- The owner requires independently written Ghost implementations. Do not copy,
  port, translate or adapt source, tests, rules, documentation or assets from
  Apache-licensed projects into Ghost. This includes model-produced material
  derived from those projects. Folder-layout inspiration does not authorize
  copying implementations.
- Do not vendor third-party implementations. Separately installed dependencies
  keep their own licenses; record new dependencies and review their terms.
- Record the origin, version, license and required notices for any permitted
  external material. Preserve notices. Never relabel external material as MIT
  or remove attribution to conceal its origin.
- If provenance is unclear, use an independently designed implementation based
  on the feature requirements, or flag the uncertainty before including it.
- Maintain the local-first CLI/REPL scope, preserve developer source during
  experiments, and require executable evidence before claiming verification.
- Keep the website’s Phases section current for development work. For each
  conversation that changes Ghost or its development setup, add a dated outcome
  to `site/content/development-notes.json`: what changed and what it enables.
  Use Asia/Kolkata dates, describe the actual result, and never publish private
  chat transcripts, credentials, or unavailable conversation history.
- Run `npm run history:update` from `site` when maintaining the timeline to
  preserve available commits in `site/content/commit-history.json`. Website
  dev/check/build commands also discover new commits automatically; preserve
  the recorded history so shallow or Git-free deployments retain older phases.
