# Ghost × FalkorDB: submission brief and readiness record

**Status: runnable technical demo; event eligibility and submission are unverified.**
This is a prepared submission package, not confirmation that Ghost has entered or
qualified for the event.

## Event rules verification

Requested event: <https://www.wemakedevs.org/hackathons/falkordb>.
On **16 October 2026 (Asia/Kolkata)**, this environment's outbound proxy denied
access to the event website with HTTP 403. The organizer's public website
repository, `WeMakeDevs/wemakedevs`, at commit
`62a6fc788845850666037d46eb3c1f3fb9f6cbaa`, did not contain the FalkorDB event page.
That older source snapshot cannot establish the current rules.

Consequently, the event dates, exact judging criteria, permitted reuse, any AI/LLM
requirement, registration, team limits, required video duration/hosting, and
submission destination have **not** been verified. Do not treat the technical
checklist below as the organizer's official requirements. Reconcile this record
with the live rules or organizer-provided text before submitting.

The initial FalkorDB implementation was committed on 16 October 2026 in
[`b440b19`](https://github.com/Devesh36/ghost/commit/b440b19), after baseline
[`825a9a5`](https://github.com/Devesh36/ghost/commit/825a9a52ef111e19ba93c9d619fdbd9dbcd52f79).
This establishes when the work was added to Ghost, **not** that it falls inside
the event's build window. Ghost predates this feature. If the event prohibits
pre-existing application foundations or these dates fall outside its window,
the smallest next step is an eligibility clarification from the organizer.
Do not change commit dates or describe older Ghost features as new event work.

## Prepared project description

**Name:** Ghost Graph Triage

**One line:** Find the security issue to investigate first by querying its service,
internet-exposure, ownership and incident relationships in FalkorDB.

Security findings alone miss operational context. Ghost's new graph triage demo
asks one question: “Which finding should we fix first, and why?” It loads a wholly
synthetic scenario into FalkorDB. Cypher traverses the relationships, calculates a
transparent priority score, and orders the findings. Ghost's bounded deterministic
agent then fetches the winning finding's service and incident evidence and shows
the relationship paths and owning team.

The demo prioritizes medium-severity F-002 at 115 points because it affects a
public API and links to an open incident. A higher-severity finding scores 75.
Removing only the incident relationship makes the higher-severity F-003 win;
restoring it makes F-002 win again. Every answer comes from fresh FalkorDB queries.
There is no local ranking fallback or model call. The score is a demo policy;
findings remain suspected and require investigation before repair.

**Repository:** <https://github.com/Devesh36/ghost>

**Implementation guide:** [setup, schema, queries and provenance](graph-hacks.md).

**Demo assets:** [terminal screenshot](../examples/graph_triage/demo-terminal.png),
[actual CLI output](../examples/graph_triage/demo-output.txt),
[answer and Cypher trace](../examples/graph_triage/demo-result.json),
[captioned demo video](../examples/graph_triage/demo-video.mp4), and
[all three walkthrough answers](../examples/graph_triage/walkthrough-result.json).

The video is a roughly 60-second, 1600×1000 H.264 MP4 with on-screen explanations
and no audio. It is an edited replay rendered from freshly executed FalkorDB
results, not a continuous screen recording. Its format has not been checked
against event requirements. The source recording can be regenerated from the
checkout with `python -m scripts.capture_graph_walkthrough` in the graph-enabled
environment; this additionally needs Node with Playwright, Chromium, FFmpeg and
ffprobe installed separately. Regeneration queries a new disposable graph and
replaces the video, poster and walkthrough JSON; it never reads cached answers.

## Technical evidence prepared

These are the requested Ghost feature's acceptance checks, not a claim about
unread event rules.

| Check | Evidence | Status |
| --- | --- | --- |
| FalkorDB performs reasoning | Cypher computes scores, traverses relationships and orders results; Ghost consumes the first returned row. | Implemented and tested with the real server. |
| Recommendation explains why | Package, service, public exposure, team and incident paths accompany the recommendation. | Implemented and tested. |
| Graph changes affect the answer | The disposable walkthrough produces F-002/115 → F-003/75 → F-002/115. | Executed against FalkorDB. |
| One reproducible demo | Packaged synthetic dataset, pinned local server, locked optional client, one question. | Runnable without credentials or a model. |
| Public/synthetic data only | All example services, teams, incidents and findings are synthetic. | No private audit import. |
| New implementation boundary | Initial feature commit, baseline and new/reused table in the guide. | Recorded; event-window eligibility pending. |
| Existing Ghost preserved | Optional dependency and separate graph; normal audits and repairs use their existing flows. | Existing regression suite and graph boundary tests passed. |
| Clear setup and explanation | Local commands, schema, score policy, full query traces, limitations and provenance. | Documented. |
| Live agent/LLM criteria, if any | Current graph agent is deterministic and supports one fixed question. | Must compare with the actual event rules. |
| Registration, rules acceptance and entry submission | No event account or submission receipt is available in this workspace. | Not completed or claimed. |

## Judge walkthrough

From the repository checkout:

```bash
docker compose -f examples/graph_triage/compose.yaml up -d --wait
uv sync --locked --extra graph
uv run --locked --extra graph ghost triage --load-demo
uv run --locked --extra graph ghost triage "Which finding should we fix first, and why?"
uv run --locked --extra graph ghost demo --graph
```

The last command creates its own uniquely named synthetic graph, runs the three
stages, validates the expected results, and deletes only that temporary graph.
It preserves the graph used by `ghost triage`. Each stage contains the real
ranked answer, owners, evidence paths and read-only query trace. Export it with:

```bash
uv run --locked --extra graph ghost demo --graph --json > walkthrough.json
```

Use `--port 6380` on the Ghost commands if you changed the Compose host port.
Both installed `ghost triage` and `ghost demo --graph` work outside a checkout.
Both fail when FalkorDB is unavailable; neither substitutes a recorded answer.
Successful JSON is printed only after cleanup. The terminal graph demo pauses
between stages for recording; `--no-pause`, redirected output and JSON skip
those pauses. With the virtual environment activated, `ghost demo --graph` is
the only command needed to present all three stages against a running server.

Suggested presentation sequence (adjust to the event's verified duration):

1. Explain the problem: severity alone misses where vulnerable code is used.
2. Run `ghost triage --load-demo`; show F-002, its 115-point breakdown and owner.
3. Trace F-002 → task-runner ← public-api → internet, plus F-002 → INC-042.
4. Run the walkthrough; show the incident-link removal changes the winner to
   F-003, and restoration changes it back. This is the central graph experiment.
5. Open `--json` output to show the actual Cypher, then disclose synthetic data,
   deterministic reasoning and the new-versus-reused implementation boundary.

## Remaining event checks

Before claiming all requirements are complete, verify the live rules and record:

- The build/submission window and whether the recorded implementation dates fit.
- Whether extending an existing open-source CLI is permitted and how reuse must
  be disclosed. The guide already discloses it.
- Whether a deterministic graph agent qualifies, or whether an actual model,
  additional interaction, deployment or particular FalkorDB service is required.
- The entrant/team details, registration and required consent.
- Any video format/duration, accessible hosting, public repository and form fields.
- The submitted entry URL/receipt after the real form is completed.

These cannot be inferred from a working demo. No organizer has been contacted,
no participant identity has been invented, and no submission has been sent.

## Validation for this preparation

On 16 October 2026, **29 focused tests passed**, including all eight real-server
integration tests and the existing graph/architecture checks. They cover the
walkthrough's changed recommendation, removal of its temporary graph on success
and evidence-query failure, and preservation of the existing graph. The normal
CLI demo and the complete walkthrough also ran directly. The video uses those
real queries; all five frames passed overflow checks and the output was decoded
with FFmpeg. Earlier full-suite results are recorded separately in the guide;
this documentation/demo increment did not rerun the entire scanner suite.
