"""Actor-Critic verification loop plugin.

After every agent invocation, spawns a critic agent (same model, same tools,
fresh memory) that evaluates the actor's work. Bypass logic for non-verifiable
tasks is built into the critic's system prompt — no separate classifier needed.

Flow:
  Actor completes → Critic evaluates → BYPASS/PASS (done) or RETRY (resume with feedback)

Enable via environment variable: ACTOR_CRITIC_ENABLED=true
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent
from strands.hooks import AfterInvocationEvent
from strands.plugins import Plugin, hook

logger = logging.getLogger(__name__)


# --- Structured Output Models ---


class CriticVerdict(str, Enum):
    """Possible verdicts from the critic agent."""

    BYPASS = "BYPASS"
    PASS = "PASS"
    RETRY = "RETRY"


class CriticEvaluation(BaseModel):
    """Structured output from the critic agent.

    The critic must return exactly one of:
    - BYPASS: Task is not verifiable (research, questions, proposals, etc.)
    - PASS: Task was completed correctly
    - RETRY: Task has concrete gaps that need to be addressed
    """

    verdict: Literal["BYPASS", "PASS", "RETRY"] = Field(
        description=(
            "BYPASS if the task is not verifiable (research, questions, proposals, conversations). "
            "PASS if the actor completed the task correctly. "
            "RETRY if there are concrete, objective gaps or failures."
        )
    )
    reason: str = Field(
        description=(
            "One-line reason for the verdict. "
            "For BYPASS: why the task is not verifiable. "
            "For PASS: what was verified. "
            "For RETRY: summary of what's wrong."
        )
    )
    feedback: str | None = Field(
        default=None,
        description="Specific, actionable feedback for the actor. Required for RETRY, null for BYPASS/PASS.",
    )
    missed: list[str] | None = Field(
        default=None,
        description="List of concrete items not done. Required for RETRY, null for BYPASS/PASS.",
    )


# --- Critic System Prompt ---

CRITIC_SYSTEM_PROMPT = """You are a Critic Agent evaluating an Actor Agent's work.

You receive the original task and a summary of what the actor did (tool calls, results, final response).
Your job: determine if the actor completed the task correctly.

## BYPASS LOGIC (check this FIRST)

Some tasks are NOT verifiable — they're questions, research, analysis, proposals,
design discussions, opinions, or conversations. For these tasks, there is nothing
concrete to verify. The actor's response IS the deliverable.

If the task falls into ANY of these categories, respond BYPASS immediately:
- Questions ("what is...", "how does...", "why...")
- Research / analysis / deep dives
- Proposals / design docs / architecture discussions
- Reviews where the output is opinion/commentary (not code changes)
- Conversations / follow-ups / clarifications
- Explanations / summaries / digests
- Meta-reasoning / strategy discussions

Do NOT waste time analyzing these. Just BYPASS.

## VERIFICATION (only for actionable tasks)

For tasks that produce VERIFIABLE ARTIFACTS (code changes, PRs, commits, file
modifications, config changes, access grants, issue/comment creation, deployments),
verify the actor's work:

1. **Did the actor actually DO the thing?** (not just talk about it)
   - Check tool call results for success/failure
   - Look for actual git commits, PR URLs, file changes
2. **Were there errors?** (failed tool calls, wrong repo, syntax errors)
3. **Did the actor address ALL parts of the request?**
   - Multi-part requests: check each part
   - If the request said "do X AND Y", both must be done
4. **Obvious mistakes?** (wrong branch, wrong file, incomplete implementation)

You have the same tools as the actor. If you need to verify something concrete
(check if a PR exists, check git status, check file contents), USE the tools.
Don't guess — verify.

## RESPONSE FORMAT

Use the CriticEvaluation structured output tool to respond with your verdict.

Rules:
- Be concise. Don't write essays.
- RETRY only for concrete, objective failures (not style preferences).
- If in doubt between PASS and RETRY, PASS. Don't create busywork.
- For RETRY: feedback must be specific and actionable, missed must list concrete items.
- For BYPASS/PASS: feedback and missed should be null.
"""


# --- Plugin ---


@dataclass
class ActorCriticConfig:
    """Configuration for Actor-Critic verification loop."""

    max_retries: int = 2
    time_budget_seconds: float = 120  # Max time for critic evaluation


class ActorCriticPlugin(Plugin):
    """Actor-Critic verification loop plugin.

    After every agent invocation, spawns a critic agent (same model, same tools,
    fresh memory) that evaluates the actor's work. Bypass logic for non-verifiable
    tasks is built into the critic's system prompt — no separate classifier needed.

    Enable via: ACTOR_CRITIC_ENABLED=true

    Flow:
      Actor completes → Critic evaluates → BYPASS/PASS (done) or RETRY (resume)
    """

    name = "actor-critic"

    def __init__(self, config: ActorCriticConfig | None = None):
        super().__init__()
        self.config = config or ActorCriticConfig()
        self._retry_count = 0
        self._start_time: float | None = None

    @hook
    def on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Run critic after actor completes. Set event.resume if retry needed."""

        # Guard: max retries
        if self._retry_count >= self.config.max_retries:
            if self._retry_count > 0:
                logger.info(
                    "Actor-Critic: max retries (%d) reached, accepting",
                    self.config.max_retries,
                )
            return

        # Guard: time budget
        if (
            self._start_time
            and (time.time() - self._start_time) > self.config.time_budget_seconds
        ):
            logger.info("Actor-Critic: time budget exceeded, accepting")
            return

        if self._start_time is None:
            self._start_time = time.time()

        # Build context for critic
        critic_input = self._build_critic_input(event)
        if not critic_input:
            logger.info("Actor-Critic: no result to evaluate, skipping")
            return

        # Create critic: same model, same tools, fresh memory
        try:
            critic = Agent(
                model=event.agent.model,
                system_prompt=CRITIC_SYSTEM_PROMPT,
                tools=list(event.agent.tool_registry.get_all_tools_map().values()),
                # No session_manager — fresh memory
                # No plugins — critic doesn't get its own critic
            )

            logger.info(
                "Actor-Critic: running critic (attempt %d/%d)",
                self._retry_count + 1,
                self.config.max_retries,
            )

            # Use structured output — SDK handles parsing via Pydantic
            result = critic(
                critic_input, structured_output_model=CriticEvaluation
            )
            evaluation: CriticEvaluation | None = result.structured_output

        except Exception as e:
            logger.warning(
                "Actor-Critic: critic failed (%s), accepting actor's work", e
            )
            return

        # Handle structured output parsing failure
        if evaluation is None:
            logger.warning(
                "Actor-Critic: structured output parsing failed, accepting"
            )
            return

        # Handle verdict
        verdict = evaluation.verdict

        if verdict == "BYPASS":
            logger.info(
                "Actor-Critic: BYPASS — %s", evaluation.reason
            )
            return

        if verdict == "PASS":
            logger.info("Actor-Critic: PASS ✅ — %s", evaluation.reason)
            return

        if verdict == "RETRY":
            self._retry_count += 1
            feedback = evaluation.feedback or evaluation.reason
            missed = evaluation.missed or []

            logger.info(
                "Actor-Critic: RETRY %d/%d — %s",
                self._retry_count,
                self.config.max_retries,
                feedback[:100],
            )

            # Build resume prompt with critic feedback
            missed_str = (
                "\n".join(f"- {item}" for item in missed) if missed else "None specified"
            )

            event.resume = (
                f"[Critic Feedback — Retry {self._retry_count}/{self.config.max_retries}]\n\n"
                f"A verification agent reviewed your work and found issues:\n\n"
                f"**Feedback:** {feedback}\n\n"
                f"**Missed items:**\n{missed_str}\n\n"
                f"Address these specific issues. Don't redo work that was already correct."
            )
            return

        # Unknown verdict — accept
        logger.warning("Actor-Critic: unknown verdict '%s', accepting", verdict)

    def _build_critic_input(self, event: AfterInvocationEvent) -> str | None:
        """Build the input prompt for the critic from actor's work."""

        # Extract original prompt (first user message)
        original_prompt = ""
        for msg in event.agent.messages[:3]:
            if msg.get("role") == "user":
                for block in msg.get("content", []):
                    if isinstance(block, dict) and "text" in block:
                        original_prompt += block["text"] + "\n"
                break

        if not original_prompt:
            return None

        # Extract tool call summary from conversation
        tool_summary = self._extract_tool_summary(event.agent.messages)

        # Extract actor's final response
        final_response = ""
        if event.result and event.result.message:
            for block in event.result.message.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    final_response += block["text"]

        # Truncate to keep critic's context manageable
        original_prompt = original_prompt[:3000]
        tool_summary = tool_summary[:3000]
        final_response = final_response[:4000]

        return (
            f"## Original Task\n{original_prompt}\n\n"
            f"## Actor's Tool Calls\n{tool_summary}\n\n"
            f"## Actor's Final Response\n{final_response}"
        )

    def _extract_tool_summary(self, messages: list) -> str:
        """Extract a summary of tool calls and their results."""
        calls = []
        for msg in messages:
            for block in msg.get("content", []):
                if isinstance(block, dict):
                    if "toolUse" in block:
                        tool_name = block["toolUse"].get("name", "?")
                        tool_input = str(block["toolUse"].get("input", {}))[:200]
                        calls.append(f"- **{tool_name}**: {tool_input}")
                    if "toolResult" in block:
                        status = block["toolResult"].get("status", "?")
                        content = ""
                        for c in block["toolResult"].get("content", []):
                            if isinstance(c, dict) and "text" in c:
                                content = c["text"][:150]
                        calls.append(f"  → {status}: {content}")

        # Take last 40 entries to keep it reasonable
        return "\n".join(calls[-40:]) or "No tool calls made"
