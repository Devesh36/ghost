# Ghost 0.1.0 — early access

Ghost is an open-source, local-first security review CLI for Python and
JavaScript/TypeScript. This first version is for evaluation and feedback; it
does not certify an application as secure.

## What is included

- Offline Python checks through Bandit and four bundled Ghost rules for selected
  JavaScript/TypeScript risks.
- Optional local cross-user access checks for configured Python ASGI apps and a
  supported CommonJS handler.
- Evidence-based investigations that test a proposed Python repair in an
  isolated Git worktree and ask before applying it to the project.
- A CLI and interactive REPL, session history, saved findings, local themes,
  and optional model connections for advice.
- `ghost demo --security`, which runs a real mixed-language review and a
  verified Python repair against a disposable sample.

## Install

Requires Python 3.12 or newer, Git, and an OS sandbox for experiments:
`sandbox-exec` on macOS or `bubblewrap` (`bwrap`) on Linux.

Download the wheel attached below, then run:

```bash
python -m pip install ghost_debugger-0.1.0-py3-none-any.whl
ghost --help
ghost demo --security
```

Local security checks need no model API key. See [Get started](https://github.com/Devesh36/ghost#get-started)
and the [release guide](https://github.com/Devesh36/ghost/blob/main/docs/releases.md).

## Coverage and safety limits

Ghost is an early security tool with intentionally bounded coverage. Its four
JavaScript/TypeScript rules do not provide application-wide data-flow analysis.
Static findings are leads for review, not proof of exploitability. Automatic
repair is limited to a supported Python pattern; each fix requires executable
verification and explicit approval. Optional access checks execute the
configured local application inside an isolated worktree. Read the full
[current limitations](https://github.com/Devesh36/ghost#current-limitations)
and [safety model](https://github.com/Devesh36/ghost#safety-and-local-data)
before relying on Ghost in a release process.

Ghost source is MIT licensed. Dependencies and model tools retain their own
licenses and terms; see [source provenance](https://github.com/Devesh36/ghost/blob/main/docs/source-provenance.md).
`SHA256SUMS` lets you check the attached archive bytes; it is not a digital
signature. The release pipeline and green tests are not a production security
certification.
