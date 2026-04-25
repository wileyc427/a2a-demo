"""
Tech Brief Orchestrator

Entry point for the pipeline. Receives a topic via HTTP, creates a root
tracentic span, then fans out to Trend Analyzer and Impact Assessor
concurrently before calling Report Writer to synthesise the results.

The orchestrator is NOT an A2A agent itself — it is the pipeline root
that drives the workflow and creates the top-level span manually. All
three specialist agents use ObservableAgentExecutor and receive trace
context injected into their A2A message metadata, automatically
continuing the trace across process boundaries.

Tree produced in the dashboard:

  Tech Brief Orchestrator          depth 0   (manual span)
    ├── Trend Analyzer             depth 1   (ObservableAgentExecutor, fan-out)
    ├── Impact Assessor            depth 1   (ObservableAgentExecutor, fan-out)
    └── Report Writer              depth 1   (ObservableAgentExecutor, sequential)

Endpoints:
  POST /run    {"topic": "..."} → {"trace_id": "...", "report": "..."}
  GET  /health
"""
from __future__ import annotations

import os

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tracentic import RemoteCollector, configure, get_tracer
from tracentic.integrations.a2a import ObservableA2AClient, A2AError

TRACENTIC_URL = os.getenv("TRACENTIC_URL", "http://localhost:4000")
TREND_ANALYZER_URL = os.getenv("TREND_ANALYZER_URL", "http://localhost:8001")
IMPACT_ASSESSOR_URL = os.getenv("IMPACT_ASSESSOR_URL", "http://localhost:8002")
REPORT_WRITER_URL = os.getenv("REPORT_WRITER_URL", "http://localhost:8003")
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")  # overridden per container in docker-compose

# Configure tracentic once at process startup. The orchestrator uses the same
# RemoteCollector as the agents — all spans from all processes end up in the
# same dashboard database, linked by trace_id.
configure(
    collector=RemoteCollector(TRACENTIC_URL),
    custom_pricing={
        "claude-haiku-4-5": (0.80, 4.00),    # $0.80 / 1M input, $4.00 / 1M output
        "claude-sonnet-4-6": (3.00, 15.00),  # $3.00 / 1M input, $15.00 / 1M output
    },
)

# Shared HTTP client for all outbound A2A calls. A single client instance
# reuses connections across requests — important for low-latency fan-out.
_http = httpx.AsyncClient(timeout=90.0)

# ObservableA2AClient handles trace context propagation and fan-out automatically.
# No need to pass parent_ctx or fan-out IDs manually in any call below.
_client = ObservableA2AClient(_http)


async def run_pipeline(topic: str) -> tuple[str, str]:
    """
    Execute the full three-agent pipeline for a given topic.
    Returns (trace_id, report_markdown).

    Span structure:
      1. Root span created here (depth 0)
      2. Trend Analyzer + Impact Assessor called concurrently via fan-out (depth 1)
      3. Report Writer called sequentially after both complete (depth 1)
    """
    tracer = get_tracer()

    # ── Root span ────────────────────────────────────────────────────────────
    # The orchestrator is not an A2A agent, so we create the root span manually.
    # start_span() returns a Span in the "submitted" state. We immediately
    # transition it to "working" and record it so the dashboard shows the
    # pipeline as in-progress before the first agent call completes.
    root = tracer.start_span(
        agent_name="Tech Brief Orchestrator",
        agent_url=f"http://{AGENT_HOST}:8080",
        skill_id="orchestrate",
        input_message={"topic": topic},
        # agent_card_snapshot is shown in the Agent Card panel of the dashboard.
        agent_card_snapshot={
            "name": "Tech Brief Orchestrator",
            "version": "1.0.0",
            "description": (
                "Drives the tech brief pipeline: fans out to Trend Analyzer and "
                "Impact Assessor concurrently, then calls Report Writer to synthesise "
                "their outputs into a structured brief."
            ),
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text", "file"],
            "skills": [
                {
                    "id": "orchestrate",
                    "name": "Generate Tech Brief",
                    "description": (
                        "Accepts a technology topic and returns a full tech brief "
                        "backed by trend analysis and business impact assessment."
                    ),
                    "tags": ["orchestration", "pipeline", "tech-brief"],
                }
            ],
        },
    )
    root.record_state_transition("working")
    await tracer.record(root)

    # set_context() writes the root span into the current asyncio task's context var.
    # ObservableA2AClient reads this automatically on every send() / fan_out() call —
    # no need to pass parent context explicitly anywhere below.
    tracer.set_context(root)

    # delegated_agents is shown in the "Delegated Agents" panel of the dashboard,
    # giving a high-level view of the pipeline topology from the orchestrator's span.
    root.delegated_agents = [
        {"name": "Trend Analyzer", "url": TREND_ANALYZER_URL, "version": "1.0.0"},
        {"name": "Impact Assessor", "url": IMPACT_ASSESSOR_URL, "version": "1.0.0"},
        {"name": "Report Writer", "url": REPORT_WRITER_URL, "version": "1.0.0"},
    ]

    try:
        # ── Stage 1: Fan-out ─────────────────────────────────────────────────────
        # fan_out() fires both calls concurrently and links them as parallel siblings
        # in the dashboard. Each A2AResponse includes duration_ms — the client-side
        # wall-clock time for that individual agent call.
        trend_resp, impact_resp = await _client.fan_out([
            (TREND_ANALYZER_URL, topic),
            (IMPACT_ASSESSOR_URL, topic),
        ])

        # ── Stage 2: Sequential synthesis ────────────────────────────────────────
        # Pass structured data to Report Writer — no string serialisation round-trip.
        # The receiving agent reads the data part directly as a dict.
        report_resp = await _client.send(REPORT_WRITER_URL, {
            "topic": topic,
            "trend_analysis": trend_resp.data or str(trend_resp),
            "impact_assessment": impact_resp.data or str(impact_resp),
        })

        # ── Close root span ──────────────────────────────────────────────────────
        # Record per-agent client-side timing from the fan-out alongside the
        # completion message. duration_ms is not a content field so it is never
        # stripped by the serialiser — pure operational signal, no PII risk.
        root.output_messages = [
            {"agent": "Trend Analyzer",  "duration_ms": trend_resp.duration_ms},
            {"agent": "Impact Assessor", "duration_ms": impact_resp.duration_ms},
            {"role": "assistant", "text": f"Tech brief complete for: {topic}"},
        ]
        root.record_state_transition("completed")
        root.close()
        await tracer.record(root)

        return root.trace_id, str(report_resp)

    except A2AError as exc:
        # A2A protocol error — agent returned a JSON-RPC error object.
        # Use error_type="protocol" to distinguish from internal application errors.
        root.error_type = "protocol"
        root.error_message = f"[{exc.code}] {exc.message}"
        root.record_state_transition("failed")
        root.close()
        await tracer.record(root)
        raise
    except Exception as exc:
        root.error_type = "application"
        root.error_message = str(exc)
        root.record_state_transition("failed")
        root.close()
        await tracer.record(root)
        raise


async def handle_run(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    topic = (body.get("topic") or "").strip()
    if not topic:
        return JSONResponse({"error": "topic is required"}, status_code=400)

    try:
        trace_id, report = await run_pipeline(topic)
        return JSONResponse({"trace_id": trace_id, "report": report})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app = Starlette(routes=[
    Route("/run", handle_run, methods=["POST"]),
    Route("/health", health),
])


if __name__ == "__main__":
    port = 8080
    print(f"[Tech Brief Orchestrator] Starting on port {port}", flush=True)
    print(f"[Tech Brief Orchestrator] Tracentic dashboard: {TRACENTIC_URL}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
