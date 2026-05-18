#!/usr/bin/env python3
"""
Activity tracking for Strands Coder agent.

Provides throttling based on GitHub API queries (no local storage needed).
Counts external actions (outside agent's own repos) for rate limiting.

Guidelines compliance:
- Default limit: 50 actions per day (configurable via STRANDS_THROTTLE_LIMIT)
- Only counts actions OUTSIDE internal repos (agent's own + user's own)
- Uses GitHub Events API for real-time tracking
- Enforcement is automatic on all mutations via enforce_throttle()
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Throttle cache — avoids hitting the GitHub Events API on every mutation.
# The cache is per-process (i.e. per agent run in GitHub Actions).
# ---------------------------------------------------------------------------
_throttle_cache: dict[str, Any] = {"result": None, "timestamp": 0.0}
_CACHE_TTL_SECONDS = 60  # Re-check at most once per minute

# ---------------------------------------------------------------------------
# Internal owners — repos owned by these are never counted as external.
# This includes the agent's own account AND the human user's account.
# Configurable via STRANDS_INTERNAL_OWNERS env var (comma-separated).
# ---------------------------------------------------------------------------
_INTERNAL_OWNERS: set[str] = {
    "mkmeral",
    "opieter-aws",
}


def _get_internal_owners(agent_owner: str = "") -> set[str]:
    """
    Get the set of owners whose repos are considered *internal*.

    Internal repos are never counted toward the daily external action
    throttle. This includes:
    - The agent's own account (``GITHUB_REPOSITORY_OWNER``)
    - The human user's account (``mkmeral``)
    - Any additional owners from ``STRANDS_INTERNAL_OWNERS`` env var

    Args:
        agent_owner: The agent's GitHub username. If empty, reads from
                     ``GITHUB_REPOSITORY_OWNER`` env var.

    Returns:
        Set of lowercase owner names that are internal.
    """
    owners = {o.lower() for o in _INTERNAL_OWNERS}

    # Add agent's own owner
    if not agent_owner:
        agent_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    if agent_owner:
        owners.add(agent_owner.lower())

    # Allow extending via environment variable
    env_owners = os.environ.get("STRANDS_INTERNAL_OWNERS", "")
    if env_owners:
        for owner in env_owners.split(","):
            owner = owner.strip()
            if owner:
                owners.add(owner.lower())

    return owners


def get_agent_activity(
    username: str | None = None,
    hours: int = 24,
    token: str | None = None,
) -> dict[str, Any]:
    """
    Query GitHub for agent activity in the specified time window.

    Args:
        username: GitHub username to query (default: from GITHUB_REPOSITORY_OWNER)
        hours: Time window in hours (default: 24 for daily throttling)
        token: GitHub token (default: from PAT_TOKEN or GITHUB_TOKEN)

    Returns:
        Dictionary with activity counts and throttle status
    """
    # Get username from environment if not provided
    if not username:
        # Try to extract from GITHUB_REPOSITORY_OWNER first
        username = os.environ.get("GITHUB_REPOSITORY_OWNER")
        if not username:
            # Fallback: extract from GITHUB_REPOSITORY (owner/repo format)
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            if "/" in repo:
                username = repo.split("/")[0]

    if not username:
        return {
            "error": "Could not determine agent username",
            "can_proceed": True,  # Fail open
        }

    # Get token
    if not token:
        token = os.environ.get("PAT_TOKEN", os.environ.get("GITHUB_TOKEN", ""))

    if not token:
        return {
            "error": "No GitHub token available",
            "can_proceed": True,  # Fail open
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        # Fetch user events (last 100 - API limit)
        response = requests.get(
            f"https://api.github.com/users/{username}/events?per_page=100",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        events = response.json()

        # Calculate time threshold
        threshold = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Get internal owners set (agent's own + user's own + env var)
        internal_owners = _get_internal_owners(username)

        # Filter events in time window and outside own repos
        external_actions: list[dict[str, Any]] = []
        internal_actions: list[dict[str, Any]] = []

        # Action types that count toward throttling
        # These are "write" actions that affect external repos
        throttled_event_types = {
            "IssueCommentEvent",  # Comments on issues
            "PullRequestReviewEvent",  # PR reviews
            "PullRequestReviewCommentEvent",  # PR review comments
            "IssuesEvent",  # Opening/closing issues
            "PullRequestEvent",  # Opening/closing PRs
            "CommitCommentEvent",  # Commit comments
            "CreateEvent",  # Creating branches/tags
            "DeleteEvent",  # Deleting branches/tags
            "PushEvent",  # Pushing code
        }

        for event in events:
            # Parse event timestamp
            created_at_str = event.get("created_at", "")
            try:
                # GitHub format: 2024-01-15T10:30:00Z
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                continue

            # Skip if outside time window
            if created_at < threshold:
                continue

            # Check if this is an external action
            repo_name = event.get("repo", {}).get("name", "")
            event_type = event.get("type", "")

            # Only count throttled event types
            if event_type not in throttled_event_types:
                continue

            # Check if internal — repo owner is in the internal owners set
            repo_owner = repo_name.split("/")[0].lower() if "/" in repo_name else ""
            is_internal = repo_owner in internal_owners

            event_summary = {
                "type": event_type,
                "repo": repo_name,
                "created_at": created_at_str,
                "action": event.get("payload", {}).get("action", ""),
            }

            if is_internal:
                internal_actions.append(event_summary)
            else:
                external_actions.append(event_summary)

        # Get throttle limit from environment (default: 30/day)
        throttle_limit = int(os.environ.get("STRANDS_THROTTLE_LIMIT", "50"))

        external_count = len(external_actions)
        can_proceed = external_count < throttle_limit
        remaining = max(0, throttle_limit - external_count)

        return {
            "username": username,
            "time_window_hours": hours,
            "external_actions": external_count,
            "internal_actions": len(internal_actions),
            "throttle_limit": throttle_limit,
            "remaining_actions": remaining,
            "can_proceed": can_proceed,
            "external_events": external_actions[:10],  # Last 10 for debugging
            "message": (
                f"✅ {remaining} actions remaining ({external_count}/{throttle_limit} used)"
                if can_proceed
                else f"🛑 Daily throttle limit reached ({external_count}/{throttle_limit}). "
                f"Wait for the 24-hour window to reset or increase STRANDS_THROTTLE_LIMIT."
            ),
        }

    except requests.exceptions.RequestException as e:
        return {
            "error": f"GitHub API request failed: {e}",
            "can_proceed": True,  # Fail open to avoid blocking on API errors
        }
    except Exception as e:
        return {
            "error": f"Activity check failed: {e}",
            "can_proceed": True,  # Fail open
        }


def check_throttle() -> tuple[bool, str]:
    """
    Simple throttle check for use before external mutations.

    Returns:
        Tuple of (can_proceed: bool, message: str)

    Example:
        can_proceed, message = check_throttle()
        if not can_proceed:
            print(message)
            return  # Don't perform the action
    """
    result = get_agent_activity()
    return result.get("can_proceed", True), result.get("message", "")


def check_throttle_cached() -> tuple[bool, str]:
    """
    Cached throttle check — at most one GitHub API call per minute.

    This avoids hammering the Events API when the agent makes multiple
    mutations in a short burst. The cache lives for the process lifetime
    (i.e. a single GitHub Actions run).

    Returns:
        Tuple of (can_proceed: bool, message: str)
    """
    now = time.time()
    if (
        _throttle_cache["result"] is not None
        and (now - _throttle_cache["timestamp"]) < _CACHE_TTL_SECONDS
    ):
        return _throttle_cache["result"]

    result = check_throttle()
    _throttle_cache["result"] = result
    _throttle_cache["timestamp"] = now
    return result


def invalidate_throttle_cache() -> None:
    """Force the next throttle check to hit the API. Useful after tests."""
    _throttle_cache["result"] = None
    _throttle_cache["timestamp"] = 0.0


def is_external_repo(repo_or_owner: str | None) -> bool:
    """
    Check whether a repo / owner is *external* to the agent.

    "External" means the repo is **not** owned by any internal owner.
    Internal owners include the agent's own account
    (``GITHUB_REPOSITORY_OWNER``, typically ``agent-of-mkmeral``) and the
    human user's account (``mkmeral``), plus any owners specified in the
    ``STRANDS_INTERNAL_OWNERS`` environment variable.

    Internal repos are never throttled.

    Args:
        repo_or_owner: Either ``"owner/repo"`` or just ``"owner"``.
                        ``None`` is treated as external (precautionary).

    Returns:
        ``True`` if external, ``False`` if internal.
    """
    if not repo_or_owner:
        return True  # Unknown target → treat as external (safe default)

    agent_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    if not agent_owner:
        # Can't determine agent owner → fail open (treat as internal)
        return False

    owner = repo_or_owner.split("/")[0] if "/" in repo_or_owner else repo_or_owner
    internal_owners = _get_internal_owners(agent_owner)
    return owner.lower() not in internal_owners


def enforce_throttle(repo_or_owner: str | None = None) -> tuple[bool, str]:
    """
    Gate-check for mutations. Call this **before** any write operation.

    Rules:
    - If ``STRANDS_THROTTLE_ENABLED`` is ``"false"``, always allows.
    - Internal mutations (targeting agent's own or user's repos) are always allowed.
    - External mutations are blocked once the daily limit is reached.

    Args:
        repo_or_owner: Target repository (``"owner/repo"``) or owner string.
                        Pass ``None`` if the target can't be determined — the
                        action will be treated as external.

    Returns:
        Tuple of ``(allowed: bool, message: str)``.
        When ``allowed`` is ``False``, the caller **must** abort the mutation
        and return the message to the user.
    """
    # Kill-switch: disable throttling entirely
    if os.environ.get("STRANDS_THROTTLE_ENABLED", "true").lower() != "true":
        return True, "Throttling disabled via STRANDS_THROTTLE_ENABLED"

    # Internal actions are never throttled
    if repo_or_owner and not is_external_repo(repo_or_owner):
        return True, "Internal action — not throttled"

    # External action → check the cached throttle
    can_proceed, message = check_throttle_cached()
    if not can_proceed:
        logger.warning(
            "Throttle enforcement blocked mutation to %s: %s",
            repo_or_owner or "(unknown)",
            message,
        )
    return can_proceed, message


def get_activity_summary() -> str:
    """
    Get a formatted activity summary for display/logging.

    Returns:
        Formatted string with activity stats
    """
    result = get_agent_activity()

    if "error" in result:
        return f"⚠️ Activity check failed: {result['error']}"

    lines = [
        f"## 📊 Agent Activity Summary (@{result['username']})",
        f"",
        f"**Time Window:** Last {result['time_window_hours']} hours",
        f"**External Actions:** {result['external_actions']} / {result['throttle_limit']} limit",
        f"**Internal Actions:** {result['internal_actions']} (not counted)",
        f"**Remaining:** {result['remaining_actions']}",
        f"**Status:** {'✅ Can proceed' if result['can_proceed'] else '🛑 Throttled'}",
    ]

    if result.get("external_events"):
        lines.append(f"\n### Recent External Actions")
        for evt in result["external_events"][:5]:
            lines.append(
                f"- {evt['type']} on `{evt['repo']}` ({evt['created_at'][:10]})"
            )

    return "\n".join(lines)


# For direct testing
if __name__ == "__main__":
    import json

    result = get_agent_activity()
    print(json.dumps(result, indent=2, default=str))
