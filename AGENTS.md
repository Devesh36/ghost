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
