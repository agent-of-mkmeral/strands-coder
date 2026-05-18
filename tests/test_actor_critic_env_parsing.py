"""Regression tests for actor-critic env var parsing.

Bug: When repo variables aren't defined, GitHub Actions still injects them
as empty strings into the environment. `os.getenv(name, default)` only
returns the default when the var is *unset*, not when it's an empty string.
This caused `int("")` to crash the agent.

These tests pin down the parsing behavior so we don't regress.
"""

import os

import pytest


def parse_int_env(name: str, default: str) -> int:
    """Mirror of the parsing pattern used in agent_runner.py."""
    return int(os.getenv(name) or default)


def parse_float_env(name: str, default: str) -> float:
    """Mirror of the parsing pattern used in agent_runner.py."""
    return float(os.getenv(name) or default)


class TestEnvVarParsing:
    """The parsing pattern must handle: unset, empty, and valid values."""

    def test_int_with_unset_var(self, monkeypatch):
        monkeypatch.delenv("ACTOR_CRITIC_MAX_RETRIES", raising=False)
        assert parse_int_env("ACTOR_CRITIC_MAX_RETRIES", "2") == 2

    def test_int_with_empty_string(self, monkeypatch):
        # The bug case: GitHub Actions injects empty string for missing repo vars
        monkeypatch.setenv("ACTOR_CRITIC_MAX_RETRIES", "")
        assert parse_int_env("ACTOR_CRITIC_MAX_RETRIES", "2") == 2

    def test_int_with_valid_value(self, monkeypatch):
        monkeypatch.setenv("ACTOR_CRITIC_MAX_RETRIES", "5")
        assert parse_int_env("ACTOR_CRITIC_MAX_RETRIES", "2") == 5

    def test_float_with_unset_var(self, monkeypatch):
        monkeypatch.delenv("ACTOR_CRITIC_TIME_BUDGET", raising=False)
        assert parse_float_env("ACTOR_CRITIC_TIME_BUDGET", "120") == 120.0

    def test_float_with_empty_string(self, monkeypatch):
        # The bug case
        monkeypatch.setenv("ACTOR_CRITIC_TIME_BUDGET", "")
        assert parse_float_env("ACTOR_CRITIC_TIME_BUDGET", "120") == 120.0

    def test_float_with_valid_value(self, monkeypatch):
        monkeypatch.setenv("ACTOR_CRITIC_TIME_BUDGET", "300")
        assert parse_float_env("ACTOR_CRITIC_TIME_BUDGET", "120") == 300.0

    def test_old_buggy_pattern_still_breaks(self, monkeypatch):
        """Demonstrate that the OLD pattern (using getenv default) still breaks
        on empty strings — proving why we need the `or` fallback."""
        monkeypatch.setenv("ACTOR_CRITIC_MAX_RETRIES", "")
        with pytest.raises(ValueError, match="invalid literal for int"):
            int(os.getenv("ACTOR_CRITIC_MAX_RETRIES", "2"))


class TestAgentRunnerSnippet:
    """Verify the actual code in agent_runner.py uses the safe pattern."""

    def test_agent_runner_uses_or_fallback(self):
        """The fix uses `os.getenv(NAME) or DEFAULT` instead of `os.getenv(NAME, DEFAULT)`."""
        import inspect

        from strands_coder import agent_runner

        source = inspect.getsource(agent_runner.run_agent)

        # Must NOT use the buggy pattern with default kwarg
        assert 'os.getenv("ACTOR_CRITIC_MAX_RETRIES", "2")' not in source, (
            "Buggy pattern detected: empty env var will crash int() — "
            "use `os.getenv(...) or '2'` instead"
        )
        assert 'os.getenv("ACTOR_CRITIC_TIME_BUDGET", "120")' not in source, (
            "Buggy pattern detected: empty env var will crash float() — "
            "use `os.getenv(...) or '120'` instead"
        )

        # Must use the safe pattern
        assert 'os.getenv("ACTOR_CRITIC_MAX_RETRIES") or "2"' in source
        assert 'os.getenv("ACTOR_CRITIC_TIME_BUDGET") or "120"' in source
