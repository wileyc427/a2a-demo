"""
Demo runner — fires several tech brief pipelines at the orchestrator
and prints results as they complete.

Run standalone:
    python run_demo.py [--url http://localhost:8080] [--loops 2]

Or via Docker Compose (starts automatically when healthy):
    docker compose --profile demo up --build
"""
from __future__ import annotations

import argparse
import asyncio

import httpx

# Topics sent to the orchestrator. Each becomes a full pipeline run:
#   Trend Analyzer + Impact Assessor (concurrent) → Report Writer (sequential)
# Vary these to populate the dashboard with diverse traces.
TOPICS = [
    "Agentic AI frameworks for enterprise automation",
    "Real-time AI inference at the edge",
    "Multi-modal foundation models in healthcare",
    "Retrieval-augmented generation for knowledge management",
]


async def wait_for_orchestrator(url: str, max_attempts: int = 30) -> None:
    """Poll the orchestrator health endpoint until it responds 200.

    Docker Compose starts the demo runner only after the orchestrator passes
    its healthcheck, so in practice this loop exits on the first attempt.
    The manual retry loop here is a safety net for local runs where the
    orchestrator may still be warming up.
    """
    print(f"Waiting for orchestrator at {url}...", flush=True)
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            try:
                r = await client.get(f"{url}/health", timeout=3.0)
                if r.status_code == 200:
                    print("Orchestrator is ready.\n", flush=True)
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
    raise RuntimeError(f"Orchestrator at {url} did not become ready in time")


async def run_topic(client: httpx.AsyncClient, url: str, topic: str) -> None:
    """POST a single topic to the orchestrator and print the trace ID.

    The orchestrator runs the full pipeline synchronously and returns
    the trace_id once all agents have completed. Open the Tracentic
    dashboard at http://localhost:4000 to explore the resulting trace tree.
    """
    print(f"  → {topic}", flush=True)
    r = await client.post(f"{url}/run", json={"topic": topic}, timeout=60.0)
    r.raise_for_status()
    data = r.json()
    trace_id = data.get("trace_id", "")
    print(f"    trace={trace_id[:8]}  ✓", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fire tech brief pipelines at the orchestrator."
    )
    parser.add_argument(
        "--url", default="http://localhost:8080",
        help="Orchestrator URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--loops", type=int, default=2,
        help="Number of rounds to run (default: 2)",
    )
    args = parser.parse_args()

    await wait_for_orchestrator(args.url)

    # Run each topic sequentially within a loop. Topics are not parallelised
    # here so that the dashboard shows clearly distinct trace start times,
    # making it easier to distinguish individual pipeline runs.
    async with httpx.AsyncClient() as client:
        for i in range(args.loops):
            print(f"Round {i + 1}/{args.loops}", flush=True)
            for topic in TOPICS:
                await run_topic(client, args.url, topic)
                await asyncio.sleep(0.5)  # brief pause between topics
            if i < args.loops - 1:
                print(flush=True)
                await asyncio.sleep(1.0)  # pause between rounds

    print(flush=True)
    print("Done. Open http://localhost:4000 to explore the traces.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
