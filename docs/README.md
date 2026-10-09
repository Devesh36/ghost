# Ghost documentation

**Find what you missed before you ship.**

Ghost is an open-source security review tool that runs in your terminal. Use it
while you develop to record selected edits and commands, then review security
risks before shipping. It supports Python and JavaScript/TypeScript static
checks, configured local access checks, and verified repairs for a supported
Python pattern.

## Start here

- [Use Ghost in your repository](getting-started.md): installation, daily work,
  security review, evidence and repairs.
- [Prepare a security brief](security-brief.md): a compact saved-review summary
  and Markdown handoff.
- [Command reference](../README.md#commands): options, examples and providers.
- [Screenshots and demos](../README.md#screenshots): see the actual terminal
  experience and run a disposable sample.

## What Ghost does

1. **Remembers selected development activity.** `watch` records file changes;
   `run` captures commands you launch through Ghost, including their output.
2. **Finds security candidates.** `find` runs local Python and JS/TS static
   checks. `scope` explains file selection and gaps.
3. **Tests configured access rules.** `auth` can run local owner/other-user
   requests against a configured application in an isolated worktree.
4. **Investigates failures.** `debug` uses recorded failures, hypotheses,
   isolated experiments and executable verification.
5. **Verifies supported repairs.** `solve` tests the original behavior, patch
   and project tests in a Git worktree before asking to apply a change.
6. **Makes evidence readable.** `brief`, `findings`, `audits`, `compare`,
   `solution` and `report` help you inspect what happened.

```text
Your project
    |
    +-- optional watch / run --> local session evidence
    |
    +-- scope / find / auth --> saved security review
                                  |
                                  +-- brief / findings --> inspect or share
                                  |
                                  +-- solve --> isolated proof and tests
                                                   |
                                                   +-- your approval --> apply
```

## Understand the evidence

**Suspected** means a static scanner reported a pattern. It is a lead for review;
it does not establish application exploitability.

**Reproduced local access failure** means configured requests showed another
user receiving protected content in a local sandbox. This proof covers those
configured cases.

**Verified repair** means the supported security probe and required project tests
ran successfully against the patch. Inspect the proof and the behavior change.

**Incomplete** means Ghost could not complete part of its selected review.
Resolve the reported gaps before relying on its coverage.

Every report is a snapshot. Rerun checks after edits. A summary, completed scan
or passing test suite does not certify that the entire application is secure.

## Scope today

Ghost's Python checks use the installed Bandit scanner. JS/TS checks use four
bundled Ghost rules with the installed Semgrep scanner. Automatic security
repair currently supports a bounded Python expression-evaluation recipe.
Authorization checks require an explicit local application contract. Ghost is
an early-stage project; see [current limitations](../README.md#current-limitations).

Observation is opt-in. Ghost records watched edits and its own `run` commands;
it does not intercept shell history. Saved evidence stays in each repository's
`.ghost/`. Optional model connections transmit prompts and explicitly selected
context to the configured provider; local scans need no model API key.

## For contributors and maintainers

- [Architecture](ARCHITECTURE.md): packages and dependency boundaries.
- [Development](../README.md#development): locked environments and tests.
- [Safety and local data](../README.md#safety-and-local-data): execution,
  privacy, storage and approval boundaries.
- [Launch readiness](launch-readiness.md): executable results and remaining gaps.
- [Reviews and findings schedule](review-improvement-plan.md): dated milestones
  and acceptance checks for triage, source freshness, history and reviewer decisions.
- [Release process](releases.md) and [v0.1.0 notes](release-notes-v0.1.0.md).
- [Source provenance](source-provenance.md): independent implementation policy
  and separate dependency licenses.

Ghost's own source is [MIT licensed](../LICENSE). Dependencies and model tools
retain their own licenses and terms.
