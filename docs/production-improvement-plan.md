# Production improvement plan

Ghost's production work proceeds in bounded iterations: reproduce a real gap,
implement on a feature branch, run focused and full regression checks, open a
separate PR, and record the remaining limitations. Merge and release decisions
remain with the repository owner. This plan describes the continuing work queue;
it does not install recurring jobs or execute work after a session ends.

## Completed iteration

[PR #23](https://github.com/Devesh36/ghost/pull/23), addressing
[issue #10](https://github.com/Devesh36/ghost/issues/10): version local history and
make upgrades transactional. The implementation preserves legacy rows and evidence
states, rejects future versions, checks every connection, and qualifies crash
rollback and concurrent startup. See [database upgrade and recovery instructions](database-upgrades.md).
Merged on 9 October 2026 after Linux, macOS, build/clean-install and deployment
checks passed. The final local suite passed 935 tests without failures or skips.

The preceding architecture iteration separated core investigations from terminal
reporting in [PR #21](https://github.com/Devesh36/ghost/pull/21). That boundary allows
headless integrations without giving presentation code mutable evidence models.

## Current iteration

The first recovery increment for [issue #4](https://github.com/Devesh36/ghost/issues/4)
adds `ghost recover`: bounded read-only planning, existing-lock coordination,
recorded snapshot associations and conservative retention of all paths. See the
[recovery plan guide](recovery-plan.md). This increment does not close the issue:
durable per-experiment attribution, process termination evidence and explicit
auditable cleanup are still required before destructive recovery is designed.

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
[#7](https://github.com/Devesh36/ghost/issues/7) can now build on the merged versioned
database.

## Gates for each iteration

- Record the concrete failure, bounded scope and acceptance criteria in the issue
  and PR. Keep unrelated feature work in separate branches.
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
