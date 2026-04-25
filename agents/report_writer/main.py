"""
Report Writer Agent — synthesises trend analysis and impact assessment
results into a concise, structured tech brief.

Runs on port 8003. Uses ObservableAgentExecutor so every call is
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
from tracentic.models import ArtifactRef, Span, TokenUsage

PORT = 8003
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


def _parse_topic(text: str) -> str:
    """Pull the topic line out of the combined input from the orchestrator."""
    for line in text.splitlines():
        if line.startswith("Topic:"):
            return line.removeprefix("Topic:").strip()
    return "the requested technology"


class ReportWriterExecutor(ObservableAgentExecutor):
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
        return "Report Writer"

    def agent_url(self) -> str:
        # Used as the span's agent_url; AGENT_HOST resolves to the Docker service name
        return f"http://{AGENT_HOST}:{PORT}"

    async def run(
        self, context: RequestContext, updater: TaskUpdater, span: Span
    ) -> None:
        """
        Implement your agent logic here. The span is already created and in
        the "working" state when run() is called — no need to open or close it.

        This agent receives combined output from Trend Analyzer + Impact Assessor
        (concatenated by the orchestrator) and synthesises it into a final brief.
        """
        input_text = _extract_text(context)
        topic = _parse_topic(input_text)

        # Send an intermediate status update visible in the A2A task stream
        await updater.update_status(
            TaskState.working,
            message=new_agent_text_message(f"Writing tech brief for: {topic}"),
        )

        # ── LLM call ────────────────────────────────────────────────────────
        # This is a mock. In production, pass input_text to an LLM that
        # synthesises the upstream analysis into a coherent brief:
        #
        #   response = await _claude.messages.create(
        #       model="claude-sonnet-4-6",
        #       max_tokens=2048,
        #       messages=[{"role": "user", "content": input_text}],
        #   )
        #   self.record_tokens(span, response)  # accumulates token usage on the span
        #   brief = response.content[0].text
        #
        brief = (
            f"# Tech Brief: {topic}\n\n"
            f"---\n\n"
            f"## Executive Summary\n\n"
            f"**{topic}** is an emerging technology area with high strategic relevance. "
            f"Trend analysis places it in the Early Majority adoption stage with strong "
            f"momentum driven by enterprise demand and maturing tooling. Business impact "
            f"is rated 8.1/10 with a realisation horizon of 18–36 months.\n\n"
            f"---\n\n"
            f"## Trend Positioning\n\n"
            f"Primary classification: **AI Infrastructure & Agentic Tooling**. "
            f"Adjacent trends include Foundation Model Commoditisation, MLOps/LLMOps "
            f"convergence, and Edge Inference. Technology readiness is 7/10.\n\n"
            f"---\n\n"
            f"## Business Impact\n\n"
            f"Highest impact sectors: Financial Services, Healthcare, Professional Services. "
            f"Key risk factors are integration complexity (High) and regulatory uncertainty "
            f"(Medium). Vendor lock-in risk is Low–Medium given open-source alternatives.\n\n"
            f"---\n\n"
            f"## Recommendations\n\n"
            f"1. Initiate a structured pilot programme within 90 days\n"
            f"2. Allocate budget for internal capability building in parallel\n"
            f"3. Monitor regulatory developments in primary sectors\n"
            f"4. Evaluate open-source alternatives to reduce lock-in risk\n\n"
            f"---\n\n"
            f"*Generated by the Tech Brief Generator pipeline.*"
        )

        # Attach token usage. Report Writer uses Sonnet (more capable model)
        # to synthesise the multi-source input — hence higher token counts.
        span.token_usage = TokenUsage(
            input_tokens=1_850, output_tokens=420, model="claude-sonnet-4-6"
        )
        # output_messages is shown in the span detail panel in the dashboard
        span.output_messages = [{"role": "assistant", "text": brief}]

        # output_artifacts registers a file artifact in the dashboard's artifact panel.
        # ArtifactRef stores metadata only — the content itself is in the message.
        # For large files, you'd store only a hash + size here and upload content
        # to object storage separately.
        span.output_artifacts = [
            ArtifactRef(
                artifact_id=f"brief-{context.task_id[:8]}",
                name="tech-brief.md",
                content_type="text/markdown",
                size_bytes=len(brief.encode()),
            )
        ]

        # Complete the A2A task — this also triggers the base class to close
        # the span and record its final state
        await updater.complete(message=new_agent_text_message(brief))


def create_agent_card() -> AgentCard:
    """
    The AgentCard is the A2A equivalent of a service manifest.
    It is injected into the executor (executor._agent_card = card) so the
    ObservableAgentExecutor can snapshot it onto every span — making the
    Agent Card panel in the dashboard fully populated for each call.
    """
    return AgentCard(
        name="Report Writer",
        description=(
            "Synthesises trend analysis and impact assessment outputs into a concise, "
            "structured tech brief with an executive summary, trend positioning, "
            "business impact section, and actionable recommendations."
        ),
        url=f"http://{AGENT_HOST}:{PORT}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="tech-brief",
                name="Write Tech Brief",
                description="Synthesise upstream analysis into a formatted markdown tech brief",
                tags=["writing", "synthesis", "report", "strategy"],
                examples=["Topic: Agentic AI\nTrend Analysis: ...\nImpact Assessment: ..."],
            )
        ],
        defaultInputModes=["text"],
        defaultOutputModes=["text", "file"],
    )


def main() -> None:
    card = create_agent_card()
    executor = ReportWriterExecutor()

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

    print(f"[Report Writer] Starting on port {PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
