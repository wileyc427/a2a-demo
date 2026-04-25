"""
Impact Assessor Agent — evaluates the business and operational impact of a
technology topic across industry verticals, with risk and timeline estimates.

Runs on port 8002. Uses ObservableAgentExecutor so every call is
automatically wrapped in a span and sent to the Tracentic dashboard.
"""
from __future__ import annotations

import os

import uvicorn
from a2a.server.agent_execution import RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TaskState, TextPart
from a2a.utils import new_agent_text_message

from tracentic import RemoteCollector, configure
from tracentic.integrations.a2a import ObservableAgentExecutor  # ← the key integration
from tracentic.models import Span, TokenUsage

PORT = 8002
TRACENTIC_URL = os.getenv("TRACENTIC_URL", "http://localhost:4000")
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")  # overridden per container in docker-compose

# Configure tracentic once at process startup. RemoteCollector ships every span
# to the dashboard over HTTP. custom_pricing enables cost estimates in the UI.
configure(
    collector=RemoteCollector(TRACENTIC_URL),
    custom_pricing={
        "claude-haiku-4-5": (0.80, 4.00),    # $0.80 / 1M input, $4.00 / 1M output
        "claude-sonnet-4-6": (3.00, 15.00),  # $3.00 / 1M input, $15.00 / 1M output
    },
)


def _extract_text(context: RequestContext) -> str:
    """Pull the first text part from the incoming A2A message."""
    if not (context.message and context.message.parts):
        return ""
    for part in context.message.parts:
        # A2A SDK wraps parts in a union type; unwrap if needed
        if hasattr(part, "root") and hasattr(part.root, "text"):
            return part.root.text
        if isinstance(part, TextPart):
            return part.text
    return ""


class ImpactAssessorExecutor(ObservableAgentExecutor):
    """
    Subclass ObservableAgentExecutor instead of AgentExecutor.

    The base class wraps execute() so you only implement run(). It handles:
      - Extracting parent trace context from the incoming message metadata
      - Creating a child span at the correct depth
      - Recording state transitions (working → completed / failed)
      - Persisting the span to Tracentic on every status change
    """

    def agent_name(self) -> str:
        # Used as the span's agent_name in the dashboard
        return "Impact Assessor"

    def agent_url(self) -> str:
        # Used as the span's agent_url; AGENT_HOST resolves to the Docker service name
        return f"http://{AGENT_HOST}:{PORT}"

    async def run(
        self, context: RequestContext, updater: TaskUpdater, span: Span
    ) -> None:
        """
        Implement your agent logic here. The span is already created and in
        the "working" state when run() is called — no need to open or close it.

        span is a live Span object. Assign to span.token_usage,
        span.output_messages, or span.output_artifacts at any point before
        returning and they will be persisted when the base class closes the span.
        """
        topic = _extract_text(context)

        # Send an intermediate status update visible in the A2A task stream
        await updater.update_status(
            TaskState.working,
            message=new_agent_text_message(f"Assessing impact for: {topic}"),
        )

        # ── LLM call ────────────────────────────────────────────────────────
        # This is a mock. To use a real LLM:
        #
        #   response = await _claude.messages.create(
        #       model="claude-haiku-4-5",
        #       max_tokens=1024,
        #       messages=[{"role": "user", "content": topic}],
        #   )
        #   self.record_tokens(span, response)  # accumulates token usage on the span
        #   result = response.content[0].text
        #
        result = (
            f"**Business Impact Assessment: {topic}**\n\n"
            f"**Impact Score:** 8.1 / 10\n"
            f"**Realisation Horizon:** 18–36 months to mainstream enterprise adoption\n\n"
            f"**Sectors Most Affected:**\n"
            f"- Financial Services — workflow automation, compliance monitoring\n"
            f"- Healthcare — diagnostic assistance, administrative burden reduction\n"
            f"- Professional Services — knowledge work augmentation\n"
            f"- Retail & E-commerce — personalisation, demand forecasting\n\n"
            f"**Key Risk Factors:**\n"
            f"- Regulatory uncertainty: **Medium** — frameworks still emerging\n"
            f"- Integration complexity: **High** — requires modernisation of data layer\n"
            f"- Skills gap: **Medium** — growing but uneven talent supply\n"
            f"- Vendor lock-in: **Low–Medium** — open-source alternatives available\n\n"
            f"**Recommended Action:** Initiate structured pilot programme within 90 days; "
            f"allocate budget for capability building in parallel."
        )

        # Attach token usage to the span so the dashboard shows cost estimates.
        # With a real LLM, use self.record_tokens(span, response) instead.
        span.token_usage = TokenUsage(
            input_tokens=410, output_tokens=240, model="claude-haiku-4-5"
        )
        # output_messages is shown in the span detail panel in the dashboard
        span.output_messages = [{"role": "assistant", "text": result}]

        # Complete the A2A task — this also triggers the base class to close
        # the span and record its final state
        await updater.complete(message=new_agent_text_message(result))


def create_agent_card() -> AgentCard:
    """
    The AgentCard is the A2A equivalent of a service manifest.
    It is injected into the executor (executor._agent_card = card) so the
    ObservableAgentExecutor can snapshot it onto every span — making the
    Agent Card panel in the dashboard fully populated for each call.
    """
    return AgentCard(
        name="Impact Assessor",
        description=(
            "Evaluates the business and operational impact of a technology topic. "
            "Produces a structured assessment covering affected sectors, risk factors, "
            "adoption timeline, and recommended actions."
        ),
        url=f"http://{AGENT_HOST}:{PORT}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="impact-assessment",
                name="Impact Assessment",
                description="Assess business impact, sector exposure, risk factors, and adoption timeline for a technology topic",
                tags=["impact", "business", "risk", "strategy"],
                examples=["Real-time AI inference at the edge"],
            )
        ],
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
    )


def main() -> None:
    card = create_agent_card()
    executor = ImpactAssessorExecutor()

    # Inject the card so ObservableAgentExecutor can snapshot it on every span.
    # Without this the Agent Card section in the dashboard will be empty.
    executor._agent_card = card

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),  # in-memory task state; fine for stateless agents
    )
    builder = A2AFastAPIApplication(agent_card=card, http_handler=handler)
    app = builder.build()

    # Health endpoint used by docker-compose healthcheck and the demo runner
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    print(f"[Impact Assessor] Starting on port {PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
