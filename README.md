# A2A Demo — Tech Brief Pipeline

A multi-agent demo using the [A2A SDK](https://github.com/google-a2a/a2a-python) and [Tracentic](../tracentic) for distributed tracing. Three specialist agents collaborate to produce structured tech briefs, with every inter-agent call captured as a trace tree in the Tracentic dashboard.

## What it does

Given a technology topic, the pipeline:

1. **Trend Analyzer** (port 8001) — classifies the trend, rates momentum, identifies adoption stage
2. **Impact Assessor** (port 8002) — evaluates business impact across industry verticals *(runs concurrently with step 1)*
3. **Report Writer** (port 8003) — synthesises both outputs into a structured tech brief

The **Orchestrator** (port 8080) drives the workflow. All spans are collected by Tracentic and visualised as a trace tree.

```
Tech Brief Orchestrator          depth 0
  ├── Trend Analyzer             depth 1  (fan-out)
  ├── Impact Assessor            depth 1  (fan-out)
  └── Report Writer              depth 1  (sequential)
```

## Prerequisites

- Python 3.10+
- Tracentic Python SDK installed from source (see below)
- Tracentic backend running and accessible

## Setup

### 1. Install the Tracentic SDK from source

The demo depends on `tracentic.integrations.a2a` which is built from the SDK source:

```bash
pip install ../tracentic/tracentic-python/
```

### 2. Install demo dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the Tracentic backend

The orchestrator and agents send traces to `http://localhost:4000` by default. Start the Tracentic Cloud app before running the demo:

```bash
cd ../tracentic/tracentic-cloud/src/Tracentic.Cloud.Api
dotnet run
```

If your Tracentic backend is on a different URL or port, set the environment variable:

```bash
export TRACENTIC_URL=http://localhost:5169
```

## Running the demo

Open four terminal tabs and start each service:

```bash
# Terminal 1 — Orchestrator
PYTHONPATH=. python orchestrator/main.py

# Terminal 2 — Trend Analyzer
PYTHONPATH=. python agents/trend_analyzer/main.py

# Terminal 3 — Impact Assessor
PYTHONPATH=. python agents/impact_assessor/main.py

# Terminal 4 — Report Writer
PYTHONPATH=. python agents/report_writer/main.py
```

Once all four are running, fire the demo pipeline:

```bash
python run_demo.py
```

This sends 4 topics through the full pipeline across 2 rounds (8 total pipeline runs).

### Options

```
python run_demo.py --url http://localhost:8080  # orchestrator URL (default)
python run_demo.py --loops 3                   # number of rounds (default: 2)
```

## Seeing the output

### Terminal output

```
Waiting for orchestrator at http://localhost:8080...
Orchestrator is ready.

Round 1/2
  → Agentic AI frameworks for enterprise automation
    trace=a1b2c3d4  ✓
  → Real-time AI inference at the edge
    trace=e5f6g7h8  ✓
  → Multi-modal foundation models in healthcare
    trace=i9j0k1l2  ✓
  → Retrieval-augmented generation for knowledge management
    trace=m3n4o5p6  ✓
...

Done. Open http://localhost:4000 to explore the traces.
```

### Tracentic dashboard

Open [http://localhost:4000](http://localhost:4000) to explore each trace. For every pipeline run you'll see:

- **Trace tree** — orchestrator root with three child spans, timing at each depth
- **Agent Cards** — capability snapshots for each agent
- **Delegated Agents** — topology view from the orchestrator's perspective
- **Token usage & cost** — per-model token counts and cost estimates
- **Output artifacts** — the generated `tech-brief.md` metadata from the Report Writer
- **State transitions** — `submitted → working → completed` lifecycle for each span

### Direct API

You can also call the orchestrator directly:

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "Quantum computing for cryptography"}'
```

Response:

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "report": "# Tech Brief: Quantum computing for cryptography\n\n..."
}
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TRACENTIC_URL` | `http://localhost:4000` | Tracentic backend for trace collection and dashboard |
| `TREND_ANALYZER_URL` | `http://localhost:8001` | Trend Analyzer agent URL |
| `IMPACT_ASSESSOR_URL` | `http://localhost:8002` | Impact Assessor agent URL |
| `REPORT_WRITER_URL` | `http://localhost:8003` | Report Writer agent URL |

## Project structure

```
orchestrator/main.py          # Pipeline root (port 8080)
agents/trend_analyzer/main.py # Trend analysis agent (port 8001)
agents/impact_assessor/main.py# Business impact agent (port 8002)
agents/report_writer/main.py  # Report synthesis agent (port 8003)
shared/a2a_client.py          # Shared ObservableA2AClient wrapper
run_demo.py                   # Demo runner CLI
requirements.txt              # Python dependencies
Dockerfile                    # Container build (context: tracentic repo root)
```
