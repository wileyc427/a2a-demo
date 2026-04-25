"""
Demo runner — sends a solar project idea to the orchestrator and prints
the full negotiation transcript.

Usage:
    # Default — reads the idea from prompt.md at the project root:
    python run_demo.py

    # Pass an idea directly:
    python run_demo.py --idea "200MW solar farm in the Mojave Desert"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap
from pathlib import Path

import httpx

SEPARATOR = "=" * 72


async def wait_for_orchestrator(url: str, max_attempts: int = 30) -> None:
    print(f"Waiting for orchestrator at {url}...", flush=True)
    async with httpx.AsyncClient() as client:
        for _ in range(max_attempts):
            try:
                r = await client.get(f"{url}/health", timeout=3.0)
                if r.status_code == 200:
                    print("Orchestrator is ready.\n", flush=True)
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
    raise RuntimeError(f"Orchestrator at {url} did not become ready in time")


async def negotiate(client: httpx.AsyncClient, url: str, idea: str) -> None:
    print(SEPARATOR, flush=True)
    print(f"IDEA: {idea}", flush=True)
    print(SEPARATOR, flush=True)

    r = await client.post(f"{url}/run", json={"idea": idea}, timeout=300.0)
    r.raise_for_status()
    data = r.json()

    transcript = data.get("transcript", "")
    print(transcript, flush=True)

    out = Path(__file__).parent / "transcript.md"
    out.write_text(transcript)
    print(f"\nTranscript written to {out}", flush=True)


def _read_prompt_md() -> str:
    prompt_file = Path(__file__).parent / "prompt.md"
    if not prompt_file.exists():
        print("Error: prompt.md not found at the project root.", file=sys.stderr)
        print("Create a prompt.md with your solar project idea, or use --idea.", file=sys.stderr)
        sys.exit(1)
    idea = prompt_file.read_text().strip()
    if not idea:
        print("Error: prompt.md is empty.", file=sys.stderr)
        sys.exit(1)
    return idea


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a solar project negotiation against the orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python run_demo.py
              python run_demo.py --idea "80MW solar farm in West Texas"
        """),
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        metavar="URL",
        help="Orchestrator base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--idea",
        metavar="TEXT",
        help="Solar project idea (overrides prompt.md)",
    )
    args = parser.parse_args()

    idea = args.idea or _read_prompt_md()

    await wait_for_orchestrator(args.url)

    async with httpx.AsyncClient() as client:
        await negotiate(client, args.url, idea)

    print(SEPARATOR, flush=True)
    print("Done.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
