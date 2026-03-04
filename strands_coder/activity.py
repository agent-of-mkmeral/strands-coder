#!/usr/bin/env python3
"""
Activity tracking for Strands Coder agent.

Provides throttling based on GitHub API queries (no local storage needed).
Counts external actions (outside agent's own repos) for rate limiting.

Guidelines compliance:
- Default limit: 30 actions per day (configurable)
- Only counts actions OUTSIDE agent-of-{owner} repos
- Uses GitHub Events API for real-time tracking
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


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
        
        # Filter events in time window and outside own repos
        external_actions = []
        internal_actions = []
        
        # Action types that count toward throttling
        # These are "write" actions that affect external repos
        throttled_event_types = {
            "IssueCommentEvent",      # Comments on issues
            "PullRequestReviewEvent", # PR reviews
            "PullRequestReviewCommentEvent",  # PR review comments
            "IssuesEvent",            # Opening/closing issues
            "PullRequestEvent",       # Opening/closing PRs
            "CommitCommentEvent",     # Commit comments
            "CreateEvent",            # Creating branches/tags
            "DeleteEvent",            # Deleting branches/tags
            "PushEvent",              # Pushing code
        }
        
        for event in events:
            # Parse event timestamp
            created_at_str = event.get("created_at", "")
            try:
                # GitHub format: 2024-01-15T10:30:00Z
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
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
            
            # Check if external (not agent-of-{something}/*)
            # The agent's own repos are under the agent's username
            is_external = not repo_name.startswith(f"{username}/")
            
            event_summary = {
                "type": event_type,
                "repo": repo_name,
                "created_at": created_at_str,
                "action": event.get("payload", {}).get("action", ""),
            }
            
            if is_external:
                external_actions.append(event_summary)
            else:
                internal_actions.append(event_summary)
        
        # Get throttle limit from environment (default: 30/day)
        throttle_limit = int(os.environ.get("STRANDS_THROTTLE_LIMIT", "30"))
        
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
                else f"🛑 Daily throttle limit reached ({external_count}/{throttle_limit}). Try again later."
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
            lines.append(f"- {evt['type']} on `{evt['repo']}` ({evt['created_at'][:10]})")
    
    return "\n".join(lines)


# For direct testing
if __name__ == "__main__":
    import json
    
    result = get_agent_activity()
    print(json.dumps(result, indent=2, default=str))
