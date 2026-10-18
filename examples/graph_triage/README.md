# Ghost × FalkorDB — Graph Hacks demo

All findings, services, teams and incidents are synthetic. From the Ghost checkout:

```bash
docker compose -f examples/graph_triage/compose.yaml up -d --wait
uv sync --locked --extra graph
uv run --locked --extra graph ghost demo --graph
uv run --locked --extra graph ghost triage --load-demo
uv run --locked --extra graph ghost triage "Which finding should we fix first, and why?"
uv run --locked --extra graph ghost triage --json
```

Expected first priority: **F-002, 115 points**, owned by Platform Engineering.
FalkorDB discovers its public-service and open-incident relationships; the
severity-only HIGH candidates rank lower at 75 and 35 points.

[Terminal screenshot](demo-terminal.png) · [Recorded output](demo-output.txt) ·
[Full JSON and executed queries](demo-result.json) · [Captioned video](demo-video.mp4)

See [the complete setup, schema, queries and event-work record](../../docs/graph-hacks.md).
The sample is packaged at [config/triage_demo.json](../../config/triage_demo.json).
Use `docker compose -f examples/graph_triage/compose.yaml down` to stop the server.

For a complete evidence walkthrough in a separate disposable graph:

```bash
ghost demo --graph
ghost demo --graph --json
```

Activate `.venv` first (`source .venv/bin/activate`), or prefix these commands
with `uv run --locked --extra graph`. The normal terminal demo pauses for Enter
between its live stages, making it suitable for recording. Use `--no-pause` to
run straight through. It needs the local server above; it never launches Docker
or installs dependencies itself. Ctrl+C attempts cleanup; cleanup failures are
reported explicitly. The installed command also works outside the checkout.

The real server returns F-002/115, then F-003/75 after removing the incident link,
then F-002/115 after restoring it. The temporary graph is deleted afterwards;
the normal demo graph is preserved. See the
[submission brief and pending event checks](../../docs/graph-hacks-submission.md).

[Recorded walkthrough JSON](walkthrough-result.json) contains all three answers
and executed query traces. The video is a roughly 60-second edited replay of
fresh results, with captions and no audio; it is not a continuous recording.
To regenerate it, install Node/Playwright, Chromium and FFmpeg separately, then
run `uv run --locked --extra graph python -m scripts.capture_graph_walkthrough`.
The tool uses Ghost's terminal palette and performs no external web requests.
