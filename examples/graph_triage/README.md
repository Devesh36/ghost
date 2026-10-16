# Ghost × FalkorDB — Graph Hacks demo

All findings, services, teams and incidents are synthetic. From the Ghost checkout:

```bash
docker compose -f examples/graph_triage/compose.yaml up -d --wait
uv sync --locked --extra graph
uv run --locked --extra graph ghost triage --load-demo
uv run --locked --extra graph ghost triage "Which finding should we fix first, and why?"
uv run --locked --extra graph ghost triage --json
```

Expected first priority: **F-002, 115 points**, owned by Platform Engineering.
FalkorDB discovers its public-service and open-incident relationships; the
severity-only HIGH candidates rank lower at 75 and 35 points.

[Terminal screenshot](demo-terminal.png) · [Recorded output](demo-output.txt) ·
[Full JSON and executed queries](demo-result.json)

See [the complete setup, schema, queries and event-work record](../../docs/graph-hacks.md).
The sample is packaged at [config/triage_demo.json](../../config/triage_demo.json).
Use `docker compose -f examples/graph_triage/compose.yaml down` to stop the server.
