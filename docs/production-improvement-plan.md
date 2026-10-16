# Production improvement plan

Ghost's production work proceeds in bounded iterations: reproduce a real gap,
implement a focused change, run applicable regression checks, and record the
remaining limitations. Completed increments land on main after validation;
package releases remain a separate owner decision. This plan describes the continuing work queue;
it does not install recurring jobs or execute work after a session ends.

## Current iteration

The 16 October 2026 reliability cycle distinguishes repeated safe SQLite-sidecar
replacement from unsafe storage and adds deterministic race regressions plus
sanitized diagnostic notes. It preserves all link/ownership checks and the
bounded retry policy. Follow the [review improvement schedule](review-improvement-plan.md)
and [ten-minute development checkpoint procedure](continuous-development.md).

Versioned local history is present in the codebase: transactional upgrades retain
legacy rows, reject future versions and check every connection. See
[database upgrade and recovery instructions](database-upgrades.md). An intermittent
storage failure observed during investigation cancellation on 12 October remains
unexplained despite subsequent passing checks. A 12-worker stress run completed
3,600 writes and 3,600 reads without reproducing it. New deterministic cases
reproduce an ambiguous error message during safe sidecar replacement, not the
original cancellation failure. Keep that investigation open before reviewer
decisions add new writes.

The preceding architecture iteration separated core investigations from terminal
reporting in [PR #21](https://github.com/Devesh36/ghost/pull/21). That boundary allows
headless integrations without giving presentation code mutable evidence models.

## Next iterations in priority order

| Priority | Work | Acceptance gate |
| --- | --- | --- |
| 1 | [Interrupted-run recovery #4](https://github.com/Devesh36/ghost/issues/4) | Read-only recovery plan, verified ownership and explicit cleanup; retain uncertain evidence and unrelated worktrees. |
| 2 | [Patch durability #5](https://github.com/Devesh36/ghost/issues/5) | Failure-injection tests for staging, sync and replacement; refuse ambiguous recovery and preserve developer edits. |
| 3 | [Process cleanup #13](https://github.com/Devesh36/ghost/issues/13) | Qualify detached descendants on supported Linux/macOS backends; block verification when termination is inconclusive. |
| 4 | [Project interpreter #3](https://github.com/Devesh36/ghost/issues/3) and [verification equivalence #14](https://github.com/Devesh36/ghost/issues/14) | Explicit trusted test environment, matching failure identity and executed-test coverage; unrelated failures and skipped tests cannot verify a repair. |
| 5 | [Model-sharing policy #12](https://github.com/Devesh36/ghost/issues/12) | Inspectable restrictions apply before provider transmission; invalid policy blocks sharing while offline review remains usable. |
| 6 | [Install qualification #2](https://github.com/Devesh36/ghost/issues/2) and [dependency inventory #16](https://github.com/Devesh36/ghost/issues/16) | Clean-host installation evidence, reviewed resolved dependencies and a release-pinned distribution before a stable-channel claim. |

Source freshness, review navigation and accessibility remain in the
[review improvement schedule](review-improvement-plan.md). Review decisions in
[#7](https://github.com/Devesh36/ghost/issues/7) can build on the versioned database
after the storage reliability investigation above.

## Gates for each iteration

- Record the concrete failure, bounded scope and acceptance criteria in the issue
  or improvement record. Keep unrelated feature work in separate increments.
- Preserve local evidence, source bytes and existing export meanings. Introduce
  dependencies only after provenance review.
- Run focused behavioral checks, then the full applicable suite. The hosted
  Linux/macOS matrix and clean-install smoke check qualify the supported paths.
  Document failures or untested combinations before requesting review.
- Update operational instructions and the readiness record with measured results.
  Keep blockers open until their criteria pass; a passing sample is not a claim
  that all applications, platforms or hostile workloads are supported.
- Do not publish a package, create a release tag or merge a PR as part of an
  improvement iteration without the owner's release or merge instruction.

The launch decision still requires the remaining gates in
[launch readiness](launch-readiness.md#remaining-launch-blockers-in-priority-order).
