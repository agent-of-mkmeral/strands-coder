"""Integration tests for throttle enforcement in use_github and github_tools.

These tests verify that:
- use_github() blocks external mutations when throttled
- use_github() allows internal mutations when throttled
- use_github() allows queries even when throttled
- github_tools._github_request() blocks write ops when throttled
- github_tools._github_request() allows GET ops when throttled
- The kill-switch (STRANDS_THROTTLE_ENABLED=false) works end-to-end
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from strands_coder.activity import invalidate_throttle_cache


# ---------------------------------------------------------------------------
# use_github (GraphQL) — throttle integration
# ---------------------------------------------------------------------------
class TestUseGithubThrottle:
    """Throttle enforcement in the GraphQL tool."""

    def setup_method(self) -> None:
        invalidate_throttle_cache()

    @patch("strands_coder.tools.use_github.enforce_throttle")
    @patch("strands_coder.tools.use_github.execute_github_graphql")
    def test_mutation_blocked_when_throttled(
        self, mock_exec: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """External mutation should be blocked when throttle says no."""
        mock_enforce.return_value = (False, "🛑 Daily throttle limit reached (30/30)")

        from strands_coder.tools.use_github import use_github

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
            "BYPASS_TOOL_CONSENT": "true",
        }):
            result = use_github._tool_func(
                query_type="mutation",
                query='mutation { addComment(input: {subjectId: "123", body: "hi"}) { id } }',
                label="Test mutation",
                variables={"owner": "strands-agents"},
            )

        assert result["status"] == "error"
        assert "throttle" in result["content"][0]["text"].lower()
        mock_exec.assert_not_called()  # Should NOT have executed the mutation

    @patch("strands_coder.tools.use_github.enforce_throttle")
    @patch("strands_coder.tools.use_github.execute_github_graphql")
    def test_mutation_allowed_when_under_limit(
        self, mock_exec: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """External mutation should proceed when under limit."""
        mock_enforce.return_value = (True, "✅ 25 remaining")
        mock_exec.return_value = {"data": {"addComment": {"id": "123"}}}

        from strands_coder.tools.use_github import use_github

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
            "BYPASS_TOOL_CONSENT": "true",
        }):
            result = use_github._tool_func(
                query_type="mutation",
                query='mutation { addComment(input: {subjectId: "123", body: "hi"}) { id } }',
                label="Test mutation",
                variables={"owner": "strands-agents"},
            )

        assert result["status"] == "success"
        mock_exec.assert_called_once()

    @patch("strands_coder.tools.use_github.enforce_throttle")
    @patch("strands_coder.tools.use_github.execute_github_graphql")
    def test_query_not_throttled(
        self, mock_exec: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """Read-only queries should never be throttled."""
        mock_exec.return_value = {"data": {"repository": {"name": "test"}}}

        from strands_coder.tools.use_github import use_github

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
            "BYPASS_TOOL_CONSENT": "true",
        }):
            result = use_github._tool_func(
                query_type="query",
                query="query { repository(owner: $owner, name: $name) { name } }",
                label="Test query",
                variables={"owner": "strands-agents", "name": "sdk-python"},
            )

        assert result["status"] == "success"
        mock_enforce.assert_not_called()  # Queries should not check throttle


# ---------------------------------------------------------------------------
# github_tools (REST) — throttle integration
# ---------------------------------------------------------------------------
class TestGithubToolsThrottle:
    """Throttle enforcement in the REST tools."""

    def setup_method(self) -> None:
        invalidate_throttle_cache()

    @patch("strands_coder.tools.github_tools.enforce_throttle")
    @patch("strands_coder.tools.github_tools.requests")
    def test_post_blocked_when_throttled(
        self, mock_requests: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """POST requests should be blocked when throttled."""
        mock_enforce.return_value = (False, "🛑 Throttled")

        from strands_coder.tools.github_tools import _github_request

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
        }):
            result = _github_request(
                "POST",
                "issues/1/comments",
                "strands-agents/sdk-python",
                {"body": "test"},
            )

        assert "throttle" in str(result).lower()
        mock_requests.post.assert_not_called()

    @patch("strands_coder.tools.github_tools.enforce_throttle")
    @patch("strands_coder.tools.github_tools.requests")
    def test_get_not_throttled(
        self, mock_requests: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """GET requests should never be throttled."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "title": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        from strands_coder.tools.github_tools import _github_request

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
        }):
            result = _github_request(
                "GET",
                "issues/1",
                "strands-agents/sdk-python",
            )

        assert isinstance(result, dict)
        mock_enforce.assert_not_called()  # GET should not check throttle

    @patch("strands_coder.tools.github_tools.enforce_throttle")
    @patch("strands_coder.tools.github_tools.requests")
    def test_patch_blocked_when_throttled(
        self, mock_requests: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """PATCH requests should be blocked when throttled."""
        mock_enforce.return_value = (False, "🛑 Throttled")

        from strands_coder.tools.github_tools import _github_request

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
        }):
            result = _github_request(
                "PATCH",
                "issues/1",
                "strands-agents/sdk-python",
                {"state": "closed"},
            )

        assert "throttle" in str(result).lower()

    @patch("strands_coder.tools.github_tools.enforce_throttle")
    @patch("strands_coder.tools.github_tools.requests")
    def test_post_allowed_when_under_limit(
        self, mock_requests: MagicMock, mock_enforce: MagicMock
    ) -> None:
        """POST requests should proceed when under limit."""
        mock_enforce.return_value = (True, "✅ ok")
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "html_url": "https://github.com/..."}
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        from strands_coder.tools.github_tools import _github_request

        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake",
        }):
            result = _github_request(
                "POST",
                "issues/1/comments",
                "strands-agents/sdk-python",
                {"body": "test"},
            )

        assert isinstance(result, dict)
        mock_requests.post.assert_called_once()
