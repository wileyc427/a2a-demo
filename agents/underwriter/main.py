"""
Underwriter Agent — acts as a senior infrastructure debt underwriter at a
commercial bank or infrastructure lending institution.

Reviews solar project proposals, raises financing concerns, and issues
conditional approvals — responding as a real credit professional would.

Runs on port 8002. Requires ANTHROPIC_API_KEY (passed via start.sh).
"""
from __future__ import annotations

import os

import anthropic
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TaskState, TextPart
from a2a.utils import new_agent_text_message

PORT = 8002
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")

SYSTEM_PROMPT = """\
You are a senior infrastructure debt underwriter at a leading commercial bank.
You have 20 years of experience underwriting utility-scale renewable energy projects.
You are rigorous, analytical, and commercially minded — you protect the bank's \
credit interests while working constructively toward bankable transactions.
You speak in precise financial and legal terms.

When the negotiation has reached a natural conclusion — deal agreed or \
definitively rejected — include the exact token [NEGOTIATION_COMPLETE] \
on its own line at the very end of your response.
"""

_claude: anthropic.AsyncAnthropic | None = None


def _get_claude() -> anthropic.AsyncAnthropic:
    global _claude
    if _claude is None:
        _claude = anthropic.AsyncAnthropic()
    return _claude


def _extract_text(context: RequestContext) -> str:
    if not (context.message and context.message.parts):
        return ""
    for part in context.message.parts:
        if hasattr(part, "root") and hasattr(part.root, "text"):
            return part.root.text
        if isinstance(part, TextPart):
            return part.text
    return ""


class UnderwriterExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = _extract_text(context)

        await updater.update_status(
            TaskState.working,
            message=new_agent_text_message("[Underwriter] Reviewing..."),
        )

        async with _get_claude().messages.stream(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": text}],
        ) as stream:
            message = await stream.get_final_message()

        result = next(
            (block.text for block in message.content if hasattr(block, "text")),
            "",
        )
        await updater.complete(message=new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()


def create_agent_card() -> AgentCard:
    return AgentCard(
        name="Underwriter",
        description=(
            "Acts as a senior infrastructure debt underwriter. Reviews solar project "
            "proposals, raises credit concerns, and issues conditional financing approvals."
        ),
        url=f"http://{AGENT_HOST}:{PORT}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="project-finance-underwriting",
                name="Project Finance Underwriting",
                description="Underwrite utility-scale renewable energy project finance transactions",
                tags=["underwriting", "project finance", "solar", "credit", "infrastructure"],
                examples=["100MW solar farm in the Arizona desert"],
            )
        ],
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
    )


def main() -> None:
    card = create_agent_card()
    executor = UnderwriterExecutor()

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    builder = A2AFastAPIApplication(agent_card=card, http_handler=handler)
    app = builder.build()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    print(f"[Underwriter] Starting on port {PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
