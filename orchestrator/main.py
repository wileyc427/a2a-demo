"""
Solar Project Negotiation Orchestrator

Receives a solar development idea and facilitates a dynamic multi-turn
professional negotiation between the Solar Developer and Underwriter agents.
The loop runs until either agent signals [NEGOTIATION_COMPLETE] or MAX_TURNS
is reached, whichever comes first.

Endpoints:
  POST /run    {"idea": "..."} → {"request_id": "...", "transcript": "..."}
  GET  /health
"""
from __future__ import annotations

import os
from uuid import uuid4

import httpx
import uvicorn
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import Message, MessageSendParams, Part, Role, Task, TextPart
from a2a.utils import get_message_text
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

SOLAR_DEVELOPER_URL = os.getenv("SOLAR_DEVELOPER_URL", "http://localhost:8001")
UNDERWRITER_URL = os.getenv("UNDERWRITER_URL", "http://localhost:8002")
MAX_TURNS = 10

_http = httpx.AsyncClient(timeout=180.0)

_AGENTS = [
    ("Solar Developer", SOLAR_DEVELOPER_URL),
    ("Underwriter", UNDERWRITER_URL),
]


async def _call_agent(url: str, text: str) -> str:
    transport = JsonRpcTransport(_http, url=url)
    params = MessageSendParams(
        message=Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id=str(uuid4()),
        )
    )
    result = await transport.send_message(params)
    if isinstance(result, Task):
        if result.status and result.status.message:
            return get_message_text(result.status.message)
        return ""
    if isinstance(result, Message):
        return get_message_text(result)
    return str(result)


def _build_message(idea: str, turns: list[tuple[str, str]], turn_num: int, agent_name: str) -> str:
    parts = [
        f"[TURN:{turn_num} of {MAX_TURNS}]",
        f"PROJECT IDEA: {idea}",
        "",
    ]

    if turns:
        parts.append("CONVERSATION HISTORY:")
        parts.append("")
        for i, (speaker, content) in enumerate(turns):
            excerpt = content[:600] + "…" if len(content) > 600 else content
            parts.append(f"[Exchange {i + 1} — {speaker}]:")
            parts.append(excerpt)
            parts.append("")

    parts.append(
        f"You are responding as the {agent_name}. "
        f"This is turn {turn_num + 1} of a maximum {MAX_TURNS} turns. "
        f"When the negotiation reaches a natural conclusion (deal agreed or definitively rejected), "
        f"include [NEGOTIATION_COMPLETE] on its own line at the very end of your response."
    )

    return "\n".join(parts)


def _format_transcript(idea: str, turns: list[tuple[str, str]]) -> str:
    lines = [
        "# Solar Project Negotiation Transcript",
        "",
        f"**Project Idea:** {idea}",
        "",
        "---",
        "",
    ]
    for i, (speaker, content) in enumerate(turns):
        lines.append(f"## [{speaker}] — Exchange {i + 1}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


async def run_negotiation(idea: str) -> tuple[str, str]:
    request_id = str(uuid4())
    turns: list[tuple[str, str]] = []

    print(f"\n[Orchestrator] Starting negotiation: {idea[:80]}", flush=True)

    for n in range(MAX_TURNS):
        agent_name, agent_url = _AGENTS[n % 2]
        print(f"[Orchestrator] Turn {n + 1}/{MAX_TURNS} → {agent_name}...", flush=True)
        message = _build_message(idea, turns, n, agent_name)
        response = await _call_agent(agent_url, message)
        turns.append((agent_name, response))
        print(f"[Orchestrator] Turn {n + 1}/{MAX_TURNS} ← {agent_name} ({len(response)} chars)", flush=True)

        if "[NEGOTIATION_COMPLETE]" in response:
            print(f"[Orchestrator] Negotiation complete after {n + 1} turns.", flush=True)
            break
    else:
        print(f"[Orchestrator] Reached max turns ({MAX_TURNS}).", flush=True)

    transcript = _format_transcript(idea, turns)
    return request_id, transcript


async def handle_run(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    idea = (body.get("idea") or "").strip()
    if not idea:
        return JSONResponse({"error": "idea is required"}, status_code=400)

    try:
        request_id, transcript = await run_negotiation(idea)
        return JSONResponse({"request_id": request_id, "transcript": transcript})
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
    print(f"[Solar Negotiation Orchestrator] Starting on port {port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
