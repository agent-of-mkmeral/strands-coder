"""Tests for generate_stable_session_id() — stable, deterministic session IDs."""

import json
import os
from unittest.mock import patch

import pytest

from strands_coder.agent_runner import generate_stable_session_id


class TestStableSessionIdExplicitOverride:
    """SESSION_ID env var always wins."""

    def test_explicit_session_id_overrides_everything(self):
        """SESSION_ID env var takes absolute precedence."""
        env = {
            "SESSION_ID": "my-custom-session",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "99999",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issue_comment",
                "event": {"issue": {"number": 42}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            assert generate_stable_session_id() == "my-custom-session"

    def test_explicit_empty_string_is_not_override(self):
        """Empty string SESSION_ID falls through to auto-generation."""
        env = {
            "SESSION_ID": "",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issues",
                "event": {"issue": {"number": 7}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            # Empty string is falsy, so it should NOT be used as override
            result = generate_stable_session_id()
            assert result == "gh-org-repo-issue-7"


class TestStableSessionIdIssueEvents:
    """Issues and issue comments produce stable per-issue IDs."""

    def test_issue_opened(self):
        env = {
            "GITHUB_REPOSITORY": "agent-of-mkmeral/strands-coder-private",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issues",
                "event": {"action": "opened", "issue": {"number": 137}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            result = generate_stable_session_id()
            assert result == "gh-agent-of-mkmeral-strands-coder-private-issue-137"

    def test_issue_comment_created(self):
        env = {
            "GITHUB_REPOSITORY": "myorg/myrepo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issue_comment",
                "event": {
                    "action": "created",
                    "issue": {"number": 42},
                    "comment": {"body": "hello"},
                },
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            result = generate_stable_session_id()
            assert result == "gh-myorg-myrepo-issue-42"

    def test_issue_comment_on_same_issue_is_stable(self):
        """Two different comments on the same issue produce the same session ID."""
        base_env = {
            "GITHUB_REPOSITORY": "org/repo",
        }

        ctx1 = json.dumps({
            "event_name": "issue_comment",
            "event": {
                "action": "created",
                "issue": {"number": 100},
                "comment": {"body": "first comment", "id": 111},
            },
        })
        ctx2 = json.dumps({
            "event_name": "issue_comment",
            "event": {
                "action": "created",
                "issue": {"number": 100},
                "comment": {"body": "second comment", "id": 222},
            },
        })

        with patch.dict(os.environ, {**base_env, "GITHUB_CONTEXT": ctx1}, clear=False):
            os.environ.pop("SESSION_ID", None)
            id1 = generate_stable_session_id()

        with patch.dict(os.environ, {**base_env, "GITHUB_CONTEXT": ctx2}, clear=False):
            os.environ.pop("SESSION_ID", None)
            id2 = generate_stable_session_id()

        assert id1 == id2 == "gh-org-repo-issue-100"

    def test_different_issues_produce_different_ids(self):
        base_env = {"GITHUB_REPOSITORY": "org/repo"}

        ctx1 = json.dumps({
            "event_name": "issues",
            "event": {"issue": {"number": 1}},
        })
        ctx2 = json.dumps({
            "event_name": "issues",
            "event": {"issue": {"number": 2}},
        })

        with patch.dict(os.environ, {**base_env, "GITHUB_CONTEXT": ctx1}, clear=False):
            os.environ.pop("SESSION_ID", None)
            id1 = generate_stable_session_id()

        with patch.dict(os.environ, {**base_env, "GITHUB_CONTEXT": ctx2}, clear=False):
            os.environ.pop("SESSION_ID", None)
            id2 = generate_stable_session_id()

        assert id1 != id2
        assert id1 == "gh-org-repo-issue-1"
        assert id2 == "gh-org-repo-issue-2"


class TestStableSessionIdPREvents:
    """PR events produce stable per-PR IDs."""

    def test_pull_request_opened(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "pull_request",
                "event": {"action": "opened", "pull_request": {"number": 55}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-pr-55"

    def test_pull_request_review(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "pull_request_review",
                "event": {"action": "submitted", "pull_request": {"number": 55}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-pr-55"

    def test_pull_request_review_comment(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "pull_request_review_comment",
                "event": {"action": "created", "pull_request": {"number": 55}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-pr-55"

    def test_multiple_reviews_on_same_pr_stable(self):
        """Review + review comment + PR event on same PR all share session."""
        base_env = {"GITHUB_REPOSITORY": "org/repo"}

        events = [
            ("pull_request", {"pull_request": {"number": 10}}),
            ("pull_request_review", {"pull_request": {"number": 10}}),
            ("pull_request_review_comment", {"pull_request": {"number": 10}}),
        ]

        ids = []
        for event_name, event_data in events:
            ctx = json.dumps({"event_name": event_name, "event": event_data})
            with patch.dict(os.environ, {**base_env, "GITHUB_CONTEXT": ctx}, clear=False):
                os.environ.pop("SESSION_ID", None)
                ids.append(generate_stable_session_id())

        assert all(sid == "gh-org-repo-pr-10" for sid in ids)


class TestStableSessionIdDiscussionEvents:
    """Discussion events produce stable per-discussion IDs."""

    def test_discussion_created(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "discussion",
                "event": {"action": "created", "discussion": {"number": 8}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-disc-8"

    def test_discussion_comment(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "discussion_comment",
                "event": {"action": "created", "discussion": {"number": 8}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-disc-8"


class TestStableSessionIdFallback:
    """Non-issue/PR/discussion events fall back to per-run IDs."""

    def test_workflow_dispatch_uses_run_id(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "12345678",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "workflow_dispatch",
                "event": {"inputs": {"prompt": "do something"}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-12345678"

    def test_schedule_event_uses_run_id(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "99999",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "schedule",
                "event": {},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-99999"

    def test_push_event_uses_run_id(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "77777",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "push",
                "event": {"ref": "refs/heads/main"},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-77777"

    def test_no_github_context_uses_run_id(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "55555",
            "GITHUB_CONTEXT": "{}",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-55555"

    def test_missing_github_context_env_uses_run_id(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "55555",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            os.environ.pop("GITHUB_CONTEXT", None)
            assert generate_stable_session_id() == "gh-org-repo-55555"

    def test_invalid_json_context_uses_run_id(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "44444",
            "GITHUB_CONTEXT": "not-valid-json{{{",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-44444"

    def test_no_run_id_defaults_to_local(self):
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": "{}",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            os.environ.pop("GITHUB_RUN_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-local"


class TestStableSessionIdEdgeCases:
    """Edge cases and robustness."""

    def test_issue_number_zero(self):
        """Issue #0 should still produce a stable ID (edge case)."""
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issues",
                "event": {"issue": {"number": 0}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-issue-0"

    def test_missing_issue_in_event_falls_back(self):
        """issue_comment event without issue object falls back to run ID."""
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "33333",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issue_comment",
                "event": {"comment": {"body": "orphan comment"}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-33333"

    def test_missing_pr_in_event_falls_back(self):
        """pull_request event without pull_request object falls back."""
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "22222",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "pull_request",
                "event": {},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-22222"

    def test_missing_number_in_issue_falls_back(self):
        """Issue object without number field falls back to run ID."""
        env = {
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "11111",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issues",
                "event": {"issue": {"title": "no number"}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-org-repo-11111"

    def test_repo_slug_handles_nested_orgs(self):
        """Repo names with slashes get properly slugified."""
        env = {
            "GITHUB_REPOSITORY": "my-org/my-repo",
            "GITHUB_CONTEXT": json.dumps({
                "event_name": "issues",
                "event": {"issue": {"number": 1}},
            }),
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SESSION_ID", None)
            assert generate_stable_session_id() == "gh-my-org-my-repo-issue-1"

    def test_cross_repo_isolation(self):
        """Same issue number in different repos gets different session IDs."""
        ctx = json.dumps({
            "event_name": "issues",
            "event": {"issue": {"number": 1}},
        })

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "org/repo-a", "GITHUB_CONTEXT": ctx}, clear=False):
            os.environ.pop("SESSION_ID", None)
            id_a = generate_stable_session_id()

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "org/repo-b", "GITHUB_CONTEXT": ctx}, clear=False):
            os.environ.pop("SESSION_ID", None)
            id_b = generate_stable_session_id()

        assert id_a == "gh-org-repo-a-issue-1"
        assert id_b == "gh-org-repo-b-issue-1"
        assert id_a != id_b
