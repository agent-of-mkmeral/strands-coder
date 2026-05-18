"""Tests for GitHub guardrails — node ID resolution & strict mutation mode.

Tests the three guardrail layers added in issue #57:
- Fix 1: resolve_node_owner() — pre-flight resolution of opaque node IDs
- Fix 2: extract_node_ids_from_variables() — detection of node IDs in variables
- Fix 3: validate_graphql_owner(is_mutative=True) — strict mode for mutations

Also tests backward compatibility:
- Queries are NOT affected by the new guardrails
- Mutations with explicit owner variables still work
- Non-node-ID variables don't trigger false positives
"""

import os
from unittest.mock import MagicMock, patch

from strands_coder.tools.github_guardrails import (
    NODE_ID_PATTERN,
    extract_node_ids_from_variables,
    resolve_node_owner,
    validate_graphql_owner,
    validate_repo_owner,
)


# ---------------------------------------------------------------------------
# Fix 2: extract_node_ids_from_variables
# ---------------------------------------------------------------------------
class TestExtractNodeIds:
    """Test detection of GitHub node IDs in GraphQL variables."""

    def test_detects_pr_node_id(self) -> None:
        """PR node IDs should be detected."""
        variables = {"prId": "PR_kwDOLMoxBs6cEfv5", "body": "review text", "event": "COMMENT"}
        node_ids = extract_node_ids_from_variables(variables)
        assert "PR_kwDOLMoxBs6cEfv5" in node_ids

    def test_detects_issue_node_id(self) -> None:
        """Issue node IDs should be detected."""
        variables = {"issueId": "I_kwDOOqJOzs8AAAABF1234", "title": "Bug"}
        node_ids = extract_node_ids_from_variables(variables)
        assert "I_kwDOOqJOzs8AAAABF1234" in node_ids

    def test_detects_repo_node_id(self) -> None:
        """Repository node IDs should be detected."""
        variables = {"repositoryId": "R_kgDOLMoxBg"}
        node_ids = extract_node_ids_from_variables(variables)
        assert "R_kgDOLMoxBg" in node_ids

    def test_detects_issue_comment_node_id(self) -> None:
        """IssueComment node IDs should be detected."""
        variables = {"commentId": "IC_kwDOOqJOzs5abc123"}
        node_ids = extract_node_ids_from_variables(variables)
        assert "IC_kwDOOqJOzs5abc123" in node_ids

    def test_detects_multiple_node_ids(self) -> None:
        """Multiple node IDs in the same variables dict should all be detected."""
        variables = {
            "prId": "PR_kwDOLMoxBs6cEfv5",
            "issueId": "I_kwDOOqJOzs8AAAABF1234",
            "body": "text",
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 2
        assert "PR_kwDOLMoxBs6cEfv5" in node_ids
        assert "I_kwDOOqJOzs8AAAABF1234" in node_ids

    def test_ignores_plain_strings(self) -> None:
        """Regular strings should NOT be detected as node IDs."""
        variables = {"body": "This is a review body", "event": "COMMENT"}
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 0

    def test_ignores_short_strings(self) -> None:
        """Short strings that match the pattern should be filtered out."""
        variables = {"status": "A_bc"}
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 0

    def test_ignores_non_string_values(self) -> None:
        """Non-string values (int, bool, list) should be skipped."""
        variables = {"count": 42, "enabled": True, "tags": ["a", "b"]}
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 0

    def test_ignores_empty_variables(self) -> None:
        """Empty dict should return empty list."""
        assert extract_node_ids_from_variables({}) == []

    def test_ignores_owner_repo_variables(self) -> None:
        """Owner/repo strings should NOT be detected as node IDs."""
        variables = {"owner": "strands-agents", "name": "sdk-python"}
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 0

    def test_ignores_legacy_mdq6_user_ids(self) -> None:
        """Legacy MDQ6 user IDs (no underscore) should NOT be detected as repo-scoped."""
        variables = {"subjectId": "MDQ6VXNlcjg0OTQzNzc="}
        node_ids = extract_node_ids_from_variables(variables)
        # MDQ6 user IDs don't have underscores and aren't repo-scoped
        assert len(node_ids) == 0


class TestNodeIdPattern:
    """Test the NODE_ID_PATTERN regex matches expected formats."""

    def test_matches_pr_id(self) -> None:
        assert NODE_ID_PATTERN.match("PR_kwDOLMoxBs6cEfv5") is not None

    def test_matches_issue_id(self) -> None:
        assert NODE_ID_PATTERN.match("I_kwDOOqJOzs8AAAABF1234") is not None

    def test_matches_repo_id(self) -> None:
        assert NODE_ID_PATTERN.match("R_kgDOLMoxBg") is not None

    def test_matches_ic_id(self) -> None:
        assert NODE_ID_PATTERN.match("IC_kwDOOqJOzs5abc123") is not None

    def test_no_match_legacy_no_underscore(self) -> None:
        """Legacy MDQ6 IDs without underscores should NOT match (they're user/org IDs)."""
        assert NODE_ID_PATTERN.match("MDQ6VXNlcjg0OTQzNzc=") is None

    def test_no_match_lowercase_prefix(self) -> None:
        """Lowercase prefix should not match (GitHub node IDs start with uppercase)."""
        assert NODE_ID_PATTERN.match("pr_kwDOLMoxBs6cEfv5") is None

    def test_no_match_plain_text(self) -> None:
        assert NODE_ID_PATTERN.match("This is plain text") is None

    def test_no_match_empty(self) -> None:
        assert NODE_ID_PATTERN.match("") is None

    def test_no_match_no_underscore(self) -> None:
        assert NODE_ID_PATTERN.match("PRkwDOLMoxBs6cEfv5") is None


# ---------------------------------------------------------------------------
# Fix 1: resolve_node_owner
# ---------------------------------------------------------------------------
class TestResolveNodeOwner:
    """Test pre-flight resolution of GitHub node IDs to repository owners."""

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_resolves_pr_to_owner(self, mock_post: MagicMock) -> None:
        """A PR node ID should resolve to its repository owner."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"node": {"repository": {"nameWithOwner": "NCAR/rda-dsspellchecker"}}}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("PR_kwDOLMoxBs6cEfv5", "fake-token")
        assert owner == "NCAR"

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_resolves_issue_to_owner(self, mock_post: MagicMock) -> None:
        """An Issue node ID should resolve to its repository owner."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"node": {"repository": {"nameWithOwner": "strands-agents/sdk-python"}}}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("I_kwDOOqJOzs8AAAABF1234", "fake-token")
        assert owner == "strands-agents"

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_resolves_repository_node(self, mock_post: MagicMock) -> None:
        """A Repository node ID should resolve to its owner via nameWithOwner."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"node": {"nameWithOwner": "mkmeral/my-repo"}}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("R_kgDOLMoxBg", "fake-token")
        assert owner == "mkmeral"

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_resolves_nested_pr_review_comment(self, mock_post: MagicMock) -> None:
        """A PullRequestReviewComment should resolve via pullRequest → repository."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"node": {"pullRequest": {"repository": {"nameWithOwner": "strands-agents/tools"}}}}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("RC_kwDOLMoxBs6cEfv5", "fake-token")
        assert owner == "strands-agents"

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_resolves_nested_discussion_comment(self, mock_post: MagicMock) -> None:
        """A DiscussionComment should resolve via discussion → repository."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"node": {"discussion": {"repository": {"nameWithOwner": "strands-agents/sdk-python"}}}}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("DC_kwDOOqJOzs5abc123", "fake-token")
        assert owner == "strands-agents"

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_returns_none_on_null_node(self, mock_post: MagicMock) -> None:
        """Deleted or inaccessible nodes return null → should return None."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"node": None}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("PR_kwDODeletedNode", "fake-token")
        assert owner is None

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_returns_none_on_graphql_errors(self, mock_post: MagicMock) -> None:
        """GraphQL errors in the response should return None."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errors": [{"message": "Could not resolve to a node with the global id"}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("PR_kwDOInvalidId", "fake-token")
        assert owner is None

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_returns_none_on_network_error(self, mock_post: MagicMock) -> None:
        """Network errors should return None (fail open for resolution, not for the guardrail)."""
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError("Network unreachable")

        owner = resolve_node_owner("PR_kwDOLMoxBs6cEfv5", "fake-token")
        assert owner is None

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_returns_none_on_timeout(self, mock_post: MagicMock) -> None:
        """Timeouts should return None."""
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout("Request timed out")

        owner = resolve_node_owner("PR_kwDOLMoxBs6cEfv5", "fake-token")
        assert owner is None

    @patch("strands_coder.tools.github_guardrails.requests.post")
    def test_returns_none_on_empty_node(self, mock_post: MagicMock) -> None:
        """Node that resolves but has no repository info should return None."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"node": {}}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        owner = resolve_node_owner("PR_kwDOSomeUnknown", "fake-token")
        assert owner is None


# ---------------------------------------------------------------------------
# Fix 3: validate_graphql_owner — strict mutation mode
# ---------------------------------------------------------------------------
class TestValidateGraphqlOwnerStrict:
    """Test the enhanced validate_graphql_owner with mutation-aware guardrails."""

    # --- Backward compatibility: queries ---

    def test_query_with_explicit_allowed_owner_passes(self) -> None:
        """Queries with explicit allowed owner should pass."""
        error, owner = validate_graphql_owner(
            {"owner": "strands-agents", "name": "sdk-python"},
            is_mutative=False,
        )
        assert error is None
        assert owner == "strands-agents"

    def test_query_with_unknown_owner_passes(self) -> None:
        """Queries without identifiable owner should still pass (backward compat)."""
        error, owner = validate_graphql_owner(
            {"someId": "abc123"},
            is_mutative=False,
        )
        assert error is None
        assert owner is None

    def test_query_with_blocked_owner_fails(self) -> None:
        """Queries targeting a disallowed owner should still be blocked."""
        error, owner = validate_graphql_owner(
            {"owner": "evil-corp", "name": "bad-repo"},
            is_mutative=False,
        )
        assert error is not None
        assert "evil-corp" in error
        assert owner is None

    # --- Mutations with explicit owner (Layer 1) ---

    def test_mutation_with_allowed_owner_passes(self) -> None:
        """Mutations with explicit allowed owner should pass."""
        error, owner = validate_graphql_owner(
            {"owner": "agent-of-mkmeral", "name": "strands-coder-private"},
            is_mutative=True,
            token="fake-token",
        )
        assert error is None
        assert owner == "agent-of-mkmeral"

    def test_mutation_with_blocked_owner_fails(self) -> None:
        """Mutations targeting a disallowed owner should be blocked."""
        error, owner = validate_graphql_owner(
            {"owner": "NCAR", "name": "rda-dsspellchecker"},
            is_mutative=True,
            token="fake-token",
        )
        assert error is not None
        assert "NCAR" in error
        assert owner is None

    # --- Mutations with node IDs (Layer 2) ---

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_mutation_with_allowed_node_id_passes(self, mock_resolve: MagicMock) -> None:
        """Mutations with node IDs that resolve to allowed owners should pass."""
        mock_resolve.return_value = "strands-agents"

        error, owner = validate_graphql_owner(
            {"prId": "PR_kwDOOqJOzs7NZ3zq", "body": "review", "event": "COMMENT"},
            is_mutative=True,
            token="fake-token",
        )
        assert error is None
        assert owner == "strands-agents"
        mock_resolve.assert_called_once_with("PR_kwDOOqJOzs7NZ3zq", "fake-token")

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_mutation_with_blocked_node_id_fails(self, mock_resolve: MagicMock) -> None:
        """Mutations with node IDs that resolve to disallowed owners should be BLOCKED.

        This is the EXACT scenario from issue #57: addPullRequestReview with a
        hallucinated node ID that points to NCAR/rda-dsspellchecker.
        """
        mock_resolve.return_value = "NCAR"

        error, owner = validate_graphql_owner(
            {"prId": "PR_kwDOLMoxBs6cEfv5", "body": ".", "event": "COMMENT"},
            is_mutative=True,
            token="fake-token",
        )
        assert error is not None
        assert "NCAR" in error
        assert "PR_kwDOLMoxBs6cEfv5" in error
        assert "not in the allowed list" in error
        assert owner is None

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_mutation_with_unresolvable_node_id_blocked(self, mock_resolve: MagicMock) -> None:
        """Mutations with node IDs that can't be resolved should be BLOCKED (Fix 3).

        This is the strict mode: when we detect a node ID but can't verify who owns it,
        we block the mutation rather than allowing it.
        """
        mock_resolve.return_value = None  # Resolution failed

        error, owner = validate_graphql_owner(
            {"prId": "PR_kwDOLMoxBs6cEfv5", "body": ".", "event": "COMMENT"},
            is_mutative=True,
            token="fake-token",
        )
        assert error is not None
        assert "Cannot verify" in error
        assert "PR_kwDOLMoxBs6cEfv5" in error
        assert owner is None

    # --- Mutations without identifiable owner (Layer 3 / edge cases) ---

    def test_mutation_with_no_variables_passes(self) -> None:
        """Mutations with empty variables should pass (schema introspection etc.)."""
        error, owner = validate_graphql_owner(
            {},
            is_mutative=True,
            token="fake-token",
        )
        assert error is None
        assert owner is None

    def test_mutation_with_non_node_id_variables_passes(self) -> None:
        """Mutations with variables that don't contain node IDs should pass.

        For example, updateUserStatus which only takes a message string.
        """
        error, owner = validate_graphql_owner(
            {"message": "Working on something cool", "emoji": "🚀"},
            is_mutative=True,
            token="fake-token",
        )
        assert error is None
        assert owner is None

    # --- Token handling ---

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_mutation_uses_provided_token(self, mock_resolve: MagicMock) -> None:
        """The provided token should be used for node ID resolution."""
        mock_resolve.return_value = "strands-agents"

        validate_graphql_owner(
            {"prId": "PR_kwDOOqJOzs7NZ3zq", "body": "review"},
            is_mutative=True,
            token="my-specific-token",
        )
        mock_resolve.assert_called_once_with("PR_kwDOOqJOzs7NZ3zq", "my-specific-token")

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"})
    def test_mutation_falls_back_to_env_token(self, mock_resolve: MagicMock) -> None:
        """When no token is provided, GITHUB_TOKEN env var should be used."""
        mock_resolve.return_value = "strands-agents"

        validate_graphql_owner(
            {"prId": "PR_kwDOOqJOzs7NZ3zq", "body": "review"},
            is_mutative=True,
            token=None,
        )
        mock_resolve.assert_called_once_with("PR_kwDOOqJOzs7NZ3zq", "env-token")


# ---------------------------------------------------------------------------
# End-to-end scenario tests (the incident from #57)
# ---------------------------------------------------------------------------
class TestIncidentScenario:
    """Reproduce the exact incident from issue #57 and verify it's now blocked."""

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_hallucinated_pr_id_to_ncar_is_blocked(self, mock_resolve: MagicMock) -> None:
        """The exact incident: addPullRequestReview with hallucinated PR_kwDOLMoxBs6cEfv5.

        The agent hallucinated this node ID during a long-running session.
        PR_kwDOLMoxBs6cEfv5 belongs to NCAR/rda-dsspellchecker#129, which
        is NOT in the allowed owners list.

        Before the fix: the guardrail returned None (allowed) because it only
        checked explicit owner variables.

        After the fix: the guardrail resolves the node ID, sees "NCAR" is not
        in ALLOWED_OWNERS, and blocks the mutation.
        """
        mock_resolve.return_value = "NCAR"

        # This is the exact mutation variables from the incident log
        variables = {
            "prId": "PR_kwDOLMoxBs6cEfv5",
            "body": ".",
            "event": "COMMENT",
        }

        error, owner = validate_graphql_owner(
            variables,
            is_mutative=True,
            token="fake-token",
        )

        # MUST be blocked
        assert error is not None
        assert "NCAR" in error
        assert "not in the allowed list" in error
        assert owner is None

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_correct_pr_id_to_strands_is_allowed(self, mock_resolve: MagicMock) -> None:
        """The correct PR node ID (strands-agents/sdk-python#1968) should be allowed.

        After the agent self-corrected, it used PR_kwDOOqJOzs7NZ3zq which belongs
        to strands-agents/sdk-python. This should pass the guardrail.
        """
        mock_resolve.return_value = "strands-agents"

        variables = {
            "prId": "PR_kwDOOqJOzs7NZ3zq",
            "body": "Full review body here...",
            "event": "COMMENT",
        }

        error, owner = validate_graphql_owner(
            variables,
            is_mutative=True,
            token="fake-token",
        )

        # MUST be allowed
        assert error is None
        assert owner == "strands-agents"


# ---------------------------------------------------------------------------
# Existing tests (backward compat) — re-test with new signature
# ---------------------------------------------------------------------------
class TestValidateGraphqlOwnerBackwardCompat:
    """Ensure the new is_mutative parameter doesn't break existing behavior."""

    def test_default_is_mutative_false(self) -> None:
        """Default is_mutative=False should match old behavior."""
        # Old behavior: allow when owner unknown
        error, owner = validate_graphql_owner({"someId": "abc123"})
        assert error is None

    def test_allowed_owner_still_passes(self) -> None:
        """Explicitly allowed owners should still pass."""
        for test_owner in ["strands-agents", "mkmeral", "agent-of-mkmeral", "strands-labs"]:
            error, owner = validate_graphql_owner({"owner": test_owner})
            assert error is None, f"Owner {test_owner} should be allowed"
            assert owner == test_owner

    def test_blocked_owner_still_fails(self) -> None:
        """Disallowed owners should still be blocked."""
        error, owner = validate_graphql_owner({"owner": "evil-corp"})
        assert error is not None
        assert "evil-corp" in error
        assert owner is None

    def test_env_extended_owners(self) -> None:
        """STRANDS_ALLOWED_OWNERS env var should still work."""
        with patch.dict(os.environ, {"STRANDS_ALLOWED_OWNERS": "custom-org"}):
            error, owner = validate_graphql_owner({"owner": "custom-org"})
            assert error is None
            assert owner == "custom-org"


class TestValidateRepoOwner:
    """Test validate_repo_owner (unchanged, but verify no regression)."""

    def test_valid_owner(self) -> None:
        assert validate_repo_owner("strands-agents/sdk-python") is None

    def test_invalid_owner(self) -> None:
        result = validate_repo_owner("evil-corp/bad-repo")
        assert result is not None
        assert "evil-corp" in result

    def test_no_slash(self) -> None:
        result = validate_repo_owner("no-slash-here")
        assert result is not None
        assert "Invalid repo format" in result

    def test_case_insensitive(self) -> None:
        assert validate_repo_owner("Strands-Agents/sdk-python") is None
        assert validate_repo_owner("MKMERAL/some-repo") is None


# ---------------------------------------------------------------------------
# Fix 4: Recursive node ID extraction from nested input objects (issue #189)
# ---------------------------------------------------------------------------
class TestExtractNodeIdsNested:
    """Test detection of node IDs nested inside GraphQL input objects.

    Issue #189: The LLM can use two patterns for the same mutation:
    1. Flat:   {"subjectId": "PR_...", "body": "..."}  — caught ✅
    2. Nested: {"input": {"subjectId": "PR_...", "body": "..."}}  — was BYPASSED ❌

    The guardrails must recursively scan nested dicts and lists to find
    node IDs regardless of the GraphQL variable structure.
    """

    def test_detects_node_id_in_nested_input_dict(self) -> None:
        """Node ID inside an 'input' dict (AddCommentInput pattern) MUST be detected."""
        variables = {
            "input": {
                "subjectId": "PR_kwDOOqJRFs6avfk-",
                "body": "Some comment text",
            }
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert "PR_kwDOOqJRFs6avfk-" in node_ids

    def test_detects_node_id_in_deeply_nested_dict(self) -> None:
        """Node IDs at arbitrary nesting depth MUST be detected."""
        variables = {
            "outer": {
                "middle": {
                    "inner": {
                        "subjectId": "I_kwDOOqJOzs8AAAABF1234",
                    }
                }
            }
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert "I_kwDOOqJOzs8AAAABF1234" in node_ids

    def test_detects_node_id_in_list(self) -> None:
        """Node IDs inside lists MUST be detected."""
        variables = {
            "nodeIds": ["PR_kwDOOqJRFs6avfk-", "I_kwDOOqJOzs8AAAABF1234"],
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert "PR_kwDOOqJRFs6avfk-" in node_ids
        assert "I_kwDOOqJOzs8AAAABF1234" in node_ids

    def test_detects_node_id_in_list_of_dicts(self) -> None:
        """Node IDs inside a list of dicts MUST be detected."""
        variables = {
            "items": [
                {"id": "PR_kwDOOqJRFs6avfk-"},
                {"id": "I_kwDOOqJOzs8AAAABF1234"},
            ]
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert "PR_kwDOOqJRFs6avfk-" in node_ids
        assert "I_kwDOOqJOzs8AAAABF1234" in node_ids

    def test_detects_both_flat_and_nested_node_ids(self) -> None:
        """Mixed flat and nested node IDs should all be detected."""
        variables = {
            "topLevelId": "R_kgDOLMoxBg",
            "input": {
                "subjectId": "PR_kwDOOqJRFs6avfk-",
            },
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert "R_kgDOLMoxBg" in node_ids
        assert "PR_kwDOOqJRFs6avfk-" in node_ids
        assert len(node_ids) == 2

    def test_ignores_non_node_id_strings_in_nested_dict(self) -> None:
        """Regular strings nested in dicts should NOT be detected."""
        variables = {
            "input": {
                "body": "This is a comment body, not a node ID",
                "event": "COMMENT",
            }
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 0

    def test_ignores_non_string_values_in_nested_dict(self) -> None:
        """Non-string values nested in dicts should be skipped."""
        variables = {
            "input": {
                "count": 42,
                "enabled": True,
                "subjectId": "PR_kwDOOqJRFs6avfk-",
            }
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert len(node_ids) == 1
        assert "PR_kwDOOqJRFs6avfk-" in node_ids

    def test_create_pull_request_input_pattern(self) -> None:
        """CreatePullRequestInput pattern with repositoryId nested."""
        variables = {
            "input": {
                "repositoryId": "R_kgDOOqJRFg",
                "title": "fix: something",
                "body": "Description",
                "baseRefName": "main",
                "headRefName": "fix/branch",
                "headRepositoryId": "R_kgDORkYzxQ",
            }
        }
        node_ids = extract_node_ids_from_variables(variables)
        assert "R_kgDOOqJRFg" in node_ids
        assert "R_kgDORkYzxQ" in node_ids


class TestIncidentScenario189:
    """Reproduce the exact incident from issue #189 and verify it's now blocked.

    The agent used:
      mutation($input: AddCommentInput!) { addComment(input: $input) { ... } }
    with variables:
      {"input": {"subjectId": "PR_kwDOOqJRFs6avfk-", "body": "..."}}

    The hallucinated node ID PR_kwDOOqJRFs6avfk- resolves to
    isa17santos/ProjetoESgrupo2/pull/14 (external repo).

    Before the fix: guardrails never saw the subjectId (nested in input dict).
    After the fix: guardrails recursively find it, resolve it, and BLOCK.
    """

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_nested_input_hallucinated_node_id_is_blocked(self, mock_resolve: MagicMock) -> None:
        """The EXACT scenario from #189: addComment with nested input."""
        mock_resolve.return_value = "isa17santos"

        # This is the exact variable structure from the incident log
        variables = {
            "input": {
                "subjectId": "PR_kwDOOqJRFs6avfk-",
                "body": "Created PR #472 to fix the E501 lint failure.",
            }
        }

        error, owner = validate_graphql_owner(
            variables,
            is_mutative=True,
            token="fake-token",
        )

        # MUST be blocked
        assert error is not None
        assert "isa17santos" in error
        assert "not in the allowed list" in error
        assert owner is None
        mock_resolve.assert_called_once_with("PR_kwDOOqJRFs6avfk-", "fake-token")

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_nested_input_allowed_node_id_passes(self, mock_resolve: MagicMock) -> None:
        """Nested input with a valid node ID should pass."""
        mock_resolve.return_value = "strands-agents"

        variables = {
            "input": {
                "subjectId": "PR_kwDOOqJRFs7blJWY",
                "body": "Some comment",
            }
        }

        error, owner = validate_graphql_owner(
            variables,
            is_mutative=True,
            token="fake-token",
        )

        assert error is None
        assert owner == "strands-agents"

    @patch("strands_coder.tools.github_guardrails.resolve_node_owner")
    def test_nested_input_unresolvable_node_id_blocked(self, mock_resolve: MagicMock) -> None:
        """Nested input with unresolvable node ID should be blocked (strict mode)."""
        mock_resolve.return_value = None

        variables = {
            "input": {
                "subjectId": "PR_kwDOOqJRFs6avfk-",
                "body": "Some comment",
            }
        }

        error, owner = validate_graphql_owner(
            variables,
            is_mutative=True,
            token="fake-token",
        )

        assert error is not None
        assert "Cannot verify" in error
        assert owner is None
