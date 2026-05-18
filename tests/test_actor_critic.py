"""Tests for Actor-Critic verification loop plugin."""

import time
from unittest.mock import MagicMock, patch

import pytest

from strands_coder.plugins.actor_critic import (
    ActorCriticConfig,
    ActorCriticPlugin,
    CriticEvaluation,
    CRITIC_SYSTEM_PROMPT,
)


class TestCriticEvaluation:
    """Test the CriticEvaluation Pydantic model."""

    def test_bypass_verdict(self):
        eval = CriticEvaluation(
            verdict="BYPASS",
            reason="research question, no artifacts to verify",
        )
        assert eval.verdict == "BYPASS"
        assert eval.feedback is None
        assert eval.missed is None

    def test_pass_verdict(self):
        eval = CriticEvaluation(
            verdict="PASS",
            reason="PR created and pushed successfully",
        )
        assert eval.verdict == "PASS"
        assert eval.feedback is None
        assert eval.missed is None

    def test_retry_verdict(self):
        eval = CriticEvaluation(
            verdict="RETRY",
            reason="Tests not updated",
            feedback="Linter errors fixed but tests were not updated.",
            missed=["Update tests to match linter changes", "Run hatch run prepare"],
        )
        assert eval.verdict == "RETRY"
        assert eval.feedback is not None
        assert len(eval.missed) == 2

    def test_invalid_verdict_rejected(self):
        with pytest.raises(Exception):
            CriticEvaluation(
                verdict="INVALID",
                reason="bad",
            )

    def test_retry_without_optional_fields(self):
        eval = CriticEvaluation(
            verdict="RETRY",
            reason="Something was missed",
        )
        assert eval.verdict == "RETRY"
        assert eval.feedback is None
        assert eval.missed is None


class TestActorCriticConfig:
    """Test configuration defaults."""

    def test_defaults(self):
        config = ActorCriticConfig()
        assert config.max_retries == 2
        assert config.time_budget_seconds == 120

    def test_custom_config(self):
        config = ActorCriticConfig(max_retries=5, time_budget_seconds=300)
        assert config.max_retries == 5
        assert config.time_budget_seconds == 300


class TestActorCriticPlugin:
    """Test plugin behavior."""

    def setup_method(self):
        self.plugin = ActorCriticPlugin(
            ActorCriticConfig(max_retries=2, time_budget_seconds=120)
        )

    def _make_event(self, messages=None, result_text="Done"):
        """Helper to create a mock AfterInvocationEvent."""
        event = MagicMock()
        event.agent.messages = messages or [
            {
                "role": "user",
                "content": [{"text": "fix the linter errors in agent_runner.py"}],
            },
            {
                "role": "assistant",
                "content": [
                    {"text": "I'll fix the linter errors."},
                    {
                        "toolUse": {
                            "name": "shell",
                            "input": {"command": "hatch run prepare"},
                        }
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "status": "success",
                            "content": [{"text": "All checks passed"}],
                        }
                    }
                ],
            },
        ]
        event.result.message = {"content": [{"text": result_text}]}
        event.resume = None
        event.agent.model = MagicMock()
        event.agent.tool_registry.get_all_tools_map.return_value = {}
        return event

    def test_max_retries_guard(self):
        """Plugin should stop after max retries."""
        self.plugin._retry_count = 2  # Already at max
        event = self._make_event()
        self.plugin.on_after_invocation(event)
        assert event.resume is None

    def test_time_budget_guard(self):
        """Plugin should stop when time budget exceeded."""
        self.plugin._start_time = time.time() - 200  # Well past 120s
        event = self._make_event()
        self.plugin.on_after_invocation(event)
        assert event.resume is None

    def test_no_messages_skips(self):
        """Plugin should skip when no user messages found."""
        event = self._make_event(messages=[])
        self.plugin.on_after_invocation(event)
        assert event.resume is None

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_bypass_verdict(self, mock_agent_class):
        """Plugin should not set resume on BYPASS verdict."""
        mock_result = MagicMock()
        mock_result.structured_output = CriticEvaluation(
            verdict="BYPASS",
            reason="research question",
        )
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_class.return_value = mock_agent_instance

        event = self._make_event()
        self.plugin.on_after_invocation(event)

        assert event.resume is None
        assert self.plugin._retry_count == 0

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_pass_verdict(self, mock_agent_class):
        """Plugin should not set resume on PASS verdict."""
        mock_result = MagicMock()
        mock_result.structured_output = CriticEvaluation(
            verdict="PASS",
            reason="code committed and pushed",
        )
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_class.return_value = mock_agent_instance

        event = self._make_event()
        self.plugin.on_after_invocation(event)

        assert event.resume is None
        assert self.plugin._retry_count == 0

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_retry_verdict_sets_resume(self, mock_agent_class):
        """Plugin should set event.resume on RETRY verdict."""
        mock_result = MagicMock()
        mock_result.structured_output = CriticEvaluation(
            verdict="RETRY",
            reason="Tests not updated",
            feedback="Linter errors fixed but tests were not updated.",
            missed=["Update unit tests", "Run hatch run prepare"],
        )
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_class.return_value = mock_agent_instance

        event = self._make_event()
        self.plugin.on_after_invocation(event)

        assert event.resume is not None
        assert "[Critic Feedback" in event.resume
        assert "Linter errors fixed" in event.resume
        assert "Update unit tests" in event.resume
        assert "Run hatch run prepare" in event.resume
        assert self.plugin._retry_count == 1

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_retry_increments_count(self, mock_agent_class):
        """Retry count increments each time."""
        mock_result = MagicMock()
        mock_result.structured_output = CriticEvaluation(
            verdict="RETRY",
            reason="Missing",
            feedback="Fix it",
            missed=["item1"],
        )
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_class.return_value = mock_agent_instance

        event = self._make_event()
        self.plugin.on_after_invocation(event)
        assert self.plugin._retry_count == 1

        event2 = self._make_event()
        self.plugin.on_after_invocation(event2)
        assert self.plugin._retry_count == 2

        # Third call should hit max_retries guard
        event3 = self._make_event()
        self.plugin.on_after_invocation(event3)
        assert event3.resume is None  # No resume — max retries hit

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_critic_failure_accepts_work(self, mock_agent_class):
        """If critic agent fails, accept the actor's work."""
        mock_agent_class.side_effect = Exception("Model unavailable")

        event = self._make_event()
        self.plugin.on_after_invocation(event)

        assert event.resume is None

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_structured_output_none_accepts(self, mock_agent_class):
        """If structured_output is None, accept the actor's work."""
        mock_result = MagicMock()
        mock_result.structured_output = None
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_class.return_value = mock_agent_instance

        event = self._make_event()
        self.plugin.on_after_invocation(event)

        assert event.resume is None

    @patch("strands_coder.plugins.actor_critic.Agent")
    def test_critic_gets_same_model_and_tools(self, mock_agent_class):
        """Critic should be created with same model and tools as actor."""
        mock_result = MagicMock()
        mock_result.structured_output = CriticEvaluation(
            verdict="PASS", reason="ok"
        )
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_class.return_value = mock_agent_instance

        event = self._make_event()
        mock_model = MagicMock()
        event.agent.model = mock_model
        mock_tools = {"shell": MagicMock(), "use_github": MagicMock()}
        event.agent.tool_registry.get_all_tools_map.return_value = mock_tools

        self.plugin.on_after_invocation(event)

        # Verify Agent() was called with correct args
        mock_agent_class.assert_called_once()
        call_kwargs = mock_agent_class.call_args
        assert call_kwargs.kwargs["model"] is mock_model
        assert call_kwargs.kwargs["system_prompt"] == CRITIC_SYSTEM_PROMPT
        assert len(call_kwargs.kwargs["tools"]) == 2

    def test_tool_summary_extraction(self):
        """Test tool summary extraction from messages."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "shell",
                            "input": {"command": "git status"},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "status": "success",
                            "content": [{"text": "On branch main"}],
                        }
                    }
                ],
            },
        ]
        summary = self.plugin._extract_tool_summary(messages)
        assert "shell" in summary
        assert "success" in summary

    def test_tool_summary_empty(self):
        """Test tool summary with no tool calls."""
        summary = self.plugin._extract_tool_summary([])
        assert summary == "No tool calls made"

    def test_plugin_name(self):
        assert self.plugin.name == "actor-critic"

    def test_retry_with_no_feedback(self):
        """RETRY with no feedback should use reason as fallback."""
        eval = CriticEvaluation(
            verdict="RETRY",
            reason="Something was missed",
        )
        # feedback is None, so reason should be used
        feedback = eval.feedback or eval.reason
        assert feedback == "Something was missed"


class TestCriticSystemPrompt:
    """Test properties of the critic system prompt."""

    def test_contains_bypass_logic(self):
        assert "BYPASS" in CRITIC_SYSTEM_PROMPT
        assert "questions" in CRITIC_SYSTEM_PROMPT.lower()
        assert "research" in CRITIC_SYSTEM_PROMPT.lower()
        assert "proposals" in CRITIC_SYSTEM_PROMPT.lower()

    def test_contains_verification_logic(self):
        assert "VERIFIABLE ARTIFACTS" in CRITIC_SYSTEM_PROMPT
        assert "tool call" in CRITIC_SYSTEM_PROMPT.lower()
        assert "git" in CRITIC_SYSTEM_PROMPT.lower()

    def test_contains_structured_output_instruction(self):
        assert "CriticEvaluation" in CRITIC_SYSTEM_PROMPT
        assert "structured output" in CRITIC_SYSTEM_PROMPT.lower()

    def test_contains_response_rules(self):
        assert "RETRY only for concrete" in CRITIC_SYSTEM_PROMPT
        assert "busywork" in CRITIC_SYSTEM_PROMPT.lower()
