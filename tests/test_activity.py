"""Tests for activity tracking and throttle enforcement.

Tests the core throttle logic including:
- _get_internal_owners() configuration
- is_external_repo() classification
- enforce_throttle() gating
- check_throttle_cached() caching behaviour
- get_agent_activity() internal owner handling
- Integration with environment variables (kill-switch, limits)
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from strands_coder.activity import (
    _CACHE_TTL_SECONDS,
    _get_internal_owners,
    check_throttle,
    check_throttle_cached,
    enforce_throttle,
    get_agent_activity,
    invalidate_throttle_cache,
    is_external_repo,
)


# ---------------------------------------------------------------------------
# _get_internal_owners
# ---------------------------------------------------------------------------
class TestGetInternalOwners:
    """Test the internal owners resolution logic."""

    def test_includes_hardcoded_mkmeral(self) -> None:
        """mkmeral should always be in the internal owners set."""
        owners = _get_internal_owners("agent-of-mkmeral")
        assert "mkmeral" in owners

    def test_includes_agent_owner(self) -> None:
        """The agent's own account should be internal."""
        owners = _get_internal_owners("agent-of-mkmeral")
        assert "agent-of-mkmeral" in owners

    def test_reads_env_var(self) -> None:
        """STRANDS_INTERNAL_OWNERS env var should be merged."""
        with patch.dict(os.environ, {"STRANDS_INTERNAL_OWNERS": "my-org,another-org"}):
            owners = _get_internal_owners("agent-of-mkmeral")
            assert "my-org" in owners
            assert "another-org" in owners
            assert "mkmeral" in owners
            assert "agent-of-mkmeral" in owners

    def test_case_insensitive(self) -> None:
        """All owners should be lowercased."""
        owners = _get_internal_owners("Agent-Of-Mkmeral")
        assert "agent-of-mkmeral" in owners

    def test_empty_agent_owner_reads_env(self) -> None:
        """When agent_owner is empty, reads from GITHUB_REPOSITORY_OWNER."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "my-agent"}):
            owners = _get_internal_owners("")
            assert "my-agent" in owners
            assert "mkmeral" in owners

    def test_no_agent_owner_at_all(self) -> None:
        """When no agent owner can be determined, still includes hardcoded."""
        env = os.environ.copy()
        env.pop("GITHUB_REPOSITORY_OWNER", None)
        with patch.dict(os.environ, env, clear=True):
            owners = _get_internal_owners("")
            assert "mkmeral" in owners


# ---------------------------------------------------------------------------
# is_external_repo
# ---------------------------------------------------------------------------
class TestIsExternalRepo:
    """Test the is_external_repo classification logic."""

    def test_none_is_external(self) -> None:
        """None target is treated as external (safe default)."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo(None) is True

    def test_empty_string_is_external(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo("") is True

    def test_own_repo_is_internal(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo("agent-of-mkmeral/strands-coder") is False

    def test_own_repo_case_insensitive(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "Agent-Of-Mkmeral"}):
            assert is_external_repo("agent-of-mkmeral/strands-coder") is False

    def test_own_owner_only(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo("agent-of-mkmeral") is False

    def test_different_owner_is_external(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo("strands-agents/sdk-python") is True

    def test_mkmeral_is_internal(self) -> None:
        """mkmeral repos are internal — they belong to the user."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo("mkmeral") is False

    def test_mkmeral_repo_is_internal(self) -> None:
        """mkmeral/some-repo should be internal."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral"}):
            assert is_external_repo("mkmeral/some-repo") is False

    def test_env_internal_owners(self) -> None:
        """STRANDS_INTERNAL_OWNERS env var should make repos internal."""
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "STRANDS_INTERNAL_OWNERS": "my-org",
        }):
            assert is_external_repo("my-org/some-repo") is False

    def test_no_env_var_fails_open(self) -> None:
        """When GITHUB_REPOSITORY_OWNER is not set, treat as internal (fail open)."""
        env = os.environ.copy()
        env.pop("GITHUB_REPOSITORY_OWNER", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_external_repo("strands-agents/sdk-python") is False


# ---------------------------------------------------------------------------
# enforce_throttle
# ---------------------------------------------------------------------------
class TestEnforceThrottle:
    """Test the enforce_throttle gate-check function."""

    def setup_method(self) -> None:
        invalidate_throttle_cache()

    def test_disabled_via_env(self) -> None:
        """STRANDS_THROTTLE_ENABLED=false bypasses all checks."""
        with patch.dict(os.environ, {"STRANDS_THROTTLE_ENABLED": "false"}):
            allowed, msg = enforce_throttle("strands-agents/sdk-python")
            assert allowed is True
            assert "disabled" in msg.lower()

    def test_internal_repo_always_allowed(self) -> None:
        """Mutations to the agent's own repos are never throttled."""
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "STRANDS_THROTTLE_ENABLED": "true",
        }):
            allowed, msg = enforce_throttle("agent-of-mkmeral/strands-coder")
            assert allowed is True
            assert "internal" in msg.lower()

    def test_mkmeral_repo_always_allowed(self) -> None:
        """Mutations to mkmeral repos are never throttled (user's own repos)."""
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "STRANDS_THROTTLE_ENABLED": "true",
        }):
            allowed, msg = enforce_throttle("mkmeral/some-repo")
            assert allowed is True
            assert "internal" in msg.lower()

    @patch("strands_coder.activity.check_throttle_cached")
    def test_external_repo_blocked_when_throttled(self, mock_cached: MagicMock) -> None:
        """External mutations are blocked when daily limit is reached."""
        mock_cached.return_value = (False, "🛑 Daily throttle limit reached (30/30)")
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "STRANDS_THROTTLE_ENABLED": "true",
        }):
            allowed, msg = enforce_throttle("strands-agents/sdk-python")
            assert allowed is False
            assert "throttle" in msg.lower()

    @patch("strands_coder.activity.check_throttle_cached")
    def test_external_repo_allowed_when_under_limit(self, mock_cached: MagicMock) -> None:
        """External mutations proceed when under the daily limit."""
        mock_cached.return_value = (True, "✅ 25 actions remaining (5/30 used)")
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "STRANDS_THROTTLE_ENABLED": "true",
        }):
            allowed, msg = enforce_throttle("strands-agents/sdk-python")
            assert allowed is True

    @patch("strands_coder.activity.check_throttle_cached")
    def test_none_target_treated_as_external(self, mock_cached: MagicMock) -> None:
        """When target is None, treat as external (precautionary)."""
        mock_cached.return_value = (False, "🛑 Throttled")
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "STRANDS_THROTTLE_ENABLED": "true",
        }):
            allowed, msg = enforce_throttle(None)
            assert allowed is False


# ---------------------------------------------------------------------------
# check_throttle_cached
# ---------------------------------------------------------------------------
class TestCheckThrottleCached:
    """Test the caching behaviour of check_throttle_cached."""

    def setup_method(self) -> None:
        invalidate_throttle_cache()

    @patch("strands_coder.activity.check_throttle")
    def test_caches_result(self, mock_check: MagicMock) -> None:
        """Second call within TTL should not hit the API."""
        mock_check.return_value = (True, "ok")

        result1 = check_throttle_cached()
        result2 = check_throttle_cached()

        assert result1 == (True, "ok")
        assert result2 == (True, "ok")
        assert mock_check.call_count == 1  # Only one API call

    @patch("strands_coder.activity.check_throttle")
    def test_invalidate_forces_refresh(self, mock_check: MagicMock) -> None:
        """invalidate_throttle_cache() forces the next call to hit the API."""
        mock_check.return_value = (True, "ok")
        check_throttle_cached()
        assert mock_check.call_count == 1

        invalidate_throttle_cache()
        check_throttle_cached()
        assert mock_check.call_count == 2


# ---------------------------------------------------------------------------
# get_agent_activity
# ---------------------------------------------------------------------------
class TestGetAgentActivity:
    """Test the GitHub Events API querying logic."""

    def test_no_username_fails_open(self) -> None:
        """When username can't be determined, fail open."""
        env = os.environ.copy()
        env.pop("GITHUB_REPOSITORY_OWNER", None)
        env.pop("GITHUB_REPOSITORY", None)
        with patch.dict(os.environ, env, clear=True):
            result = get_agent_activity(username=None)
            assert result["can_proceed"] is True
            assert "error" in result

    def test_no_token_fails_open(self) -> None:
        """When no token is available, fail open."""
        env = {"GITHUB_REPOSITORY_OWNER": "test-agent"}
        with patch.dict(os.environ, env, clear=True):
            result = get_agent_activity(username="test-agent")
            assert result["can_proceed"] is True
            assert "error" in result

    @patch("strands_coder.activity.requests.get")
    def test_api_error_fails_open(self, mock_get: MagicMock) -> None:
        """API errors should fail open (not block the agent)."""
        mock_get.side_effect = Exception("Network error")
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "test-agent",
            "GITHUB_TOKEN": "fake-token",
        }):
            result = get_agent_activity(username="test-agent")
            assert result["can_proceed"] is True
            assert "error" in result

    @patch("strands_coder.activity.requests.get")
    def test_under_limit_can_proceed(self, mock_get: MagicMock) -> None:
        """When external actions < limit, can_proceed is True."""
        mock_response = MagicMock()
        mock_response.json.return_value = []  # No events
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "test-agent",
            "GITHUB_TOKEN": "fake-token",
            "STRANDS_THROTTLE_LIMIT": "30",
        }):
            result = get_agent_activity(username="test-agent")
            assert result["can_proceed"] is True
            assert result["external_actions"] == 0
            assert result["remaining_actions"] == 30

    @patch("strands_coder.activity.requests.get")
    def test_at_limit_cannot_proceed(self, mock_get: MagicMock) -> None:
        """When external actions >= limit, can_proceed is False."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        events = [
            {
                "type": "IssueCommentEvent",
                "repo": {"name": "other-org/some-repo"},
                "created_at": now.isoformat(),
                "payload": {"action": "created"},
            }
            for _ in range(30)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = events
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "test-agent",
            "GITHUB_TOKEN": "fake-token",
            "STRANDS_THROTTLE_LIMIT": "30",
        }):
            result = get_agent_activity(username="test-agent")
            assert result["can_proceed"] is False
            assert result["external_actions"] == 30
            assert result["remaining_actions"] == 0

    @patch("strands_coder.activity.requests.get")
    def test_internal_events_not_counted(self, mock_get: MagicMock) -> None:
        """Events on agent's own repos should not count toward throttle."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        events = [
            {
                "type": "PushEvent",
                "repo": {"name": "test-agent/my-repo"},
                "created_at": now.isoformat(),
                "payload": {"action": ""},
            }
            for _ in range(50)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = events
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "test-agent",
            "GITHUB_TOKEN": "fake-token",
            "STRANDS_THROTTLE_LIMIT": "30",
        }):
            result = get_agent_activity(username="test-agent")
            assert result["can_proceed"] is True
            assert result["external_actions"] == 0
            assert result["internal_actions"] == 50

    @patch("strands_coder.activity.requests.get")
    def test_mkmeral_events_not_counted_as_external(self, mock_get: MagicMock) -> None:
        """Events on mkmeral repos should be internal, not external."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        events = [
            {
                "type": "PushEvent",
                "repo": {"name": "mkmeral/some-repo"},
                "created_at": now.isoformat(),
                "payload": {"action": ""},
            }
            for _ in range(20)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = events
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "GITHUB_TOKEN": "fake-token",
            "STRANDS_THROTTLE_LIMIT": "30",
        }):
            result = get_agent_activity(username="agent-of-mkmeral")
            assert result["can_proceed"] is True
            assert result["external_actions"] == 0
            assert result["internal_actions"] == 20

    @patch("strands_coder.activity.requests.get")
    def test_mixed_internal_and_external(self, mock_get: MagicMock) -> None:
        """Mixed events: agent's own + mkmeral = internal, others = external."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        events = [
            # Internal: agent's own repo
            {"type": "PushEvent", "repo": {"name": "agent-of-mkmeral/my-repo"}, "created_at": now.isoformat(), "payload": {"action": ""}},
            # Internal: mkmeral's repo
            {"type": "IssueCommentEvent", "repo": {"name": "mkmeral/personal-repo"}, "created_at": now.isoformat(), "payload": {"action": "created"}},
            # External: strands-agents repo
            {"type": "IssueCommentEvent", "repo": {"name": "strands-agents/sdk-python"}, "created_at": now.isoformat(), "payload": {"action": "created"}},
            # External: random org
            {"type": "PullRequestEvent", "repo": {"name": "random-org/random-repo"}, "created_at": now.isoformat(), "payload": {"action": "opened"}},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = events
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "agent-of-mkmeral",
            "GITHUB_TOKEN": "fake-token",
            "STRANDS_THROTTLE_LIMIT": "30",
        }):
            result = get_agent_activity(username="agent-of-mkmeral")
            assert result["internal_actions"] == 2  # agent-of-mkmeral + mkmeral
            assert result["external_actions"] == 2  # strands-agents + random-org

    @patch("strands_coder.activity.requests.get")
    def test_custom_throttle_limit(self, mock_get: MagicMock) -> None:
        """STRANDS_THROTTLE_LIMIT env var should be respected."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "test-agent",
            "GITHUB_TOKEN": "fake-token",
            "STRANDS_THROTTLE_LIMIT": "100",
        }):
            result = get_agent_activity(username="test-agent")
            assert result["throttle_limit"] == 100
            assert result["remaining_actions"] == 100
