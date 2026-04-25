"""
Solar Developer Agent — acts as an experienced utility-scale solar developer.

Receives a project idea and full negotiation history, responds as a professional
developer would: proposing projects, responding to underwriter concerns, and
negotiating financing terms.

Runs on port 8001. Requires ANTHROPIC_API_KEY (passed via start.sh).
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

PORT = 8001
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")

SYSTEM_PROMPT = """\
You are a senior project developer at a utility-scale solar development firm.
You have 15 years of experience developing projects across the Southwest US.
You communicate in a professional, confident, and technically precise manner.
You negotiate firmly but constructively with lenders and underwriters.

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


class SolarDeveloperExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = _extract_text(context)

        await updater.update_status(
            TaskState.working,
            message=new_agent_text_message("[Solar Developer] Thinking..."),
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
        name="Solar Developer",
        description=(
            "Acts as an experienced utility-scale solar project developer. "
            "Proposes projects, responds to lender/underwriter concerns, "
            "and negotiates financing terms."
        ),
        url=f"http://{AGENT_HOST}:{PORT}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="solar-development",
                name="Solar Project Development",
                description="Develop and negotiate utility-scale solar project proposals",
                tags=["solar", "renewable energy", "project finance", "development"],
                examples=["100MW solar farm in the Arizona desert"],
            )
        ],
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
    )


def main() -> None:
    card = create_agent_card()
    executor = SolarDeveloperExecutor()

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    builder = A2AFastAPIApplication(agent_card=card, http_handler=handler)
    app = builder.build()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    print(f"[Solar Developer] Starting on port {PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
