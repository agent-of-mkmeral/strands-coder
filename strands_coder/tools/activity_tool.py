#!/usr/bin/env python3
"""
Activity tracking tool for Strands Coder agent.

Provides a tool interface for querying agent activity and checking throttle status.
Can be used by the agent itself and by dashboards.
"""

import os
from typing import Any

from strands.types.tools import ToolResult, ToolUse

from ..activity import get_agent_activity, get_activity_summary


def activity(
    action: str = "status",
    username: str | None = None,
    hours: int = 24,
) -> ToolResult:
    """
    Query agent activity and throttle status.

    This tool provides visibility into the agent's GitHub activity for:
    - Throttle checking before external actions
    - Dashboard integration for monitoring
    - Debugging and compliance tracking

    Actions:
        - "status": Get current activity status and throttle info
        - "summary": Get formatted markdown summary
        - "check": Simple throttle check (returns can_proceed boolean)

    Args:
        action: The action to perform ("status", "summary", "check")
        username: GitHub username to query (default: from environment)
        hours: Time window in hours (default: 24 for daily throttling)

    Returns:
        ToolResult with activity data

    Examples:
        # Check if throttled before making external action
        result = activity(action="check")
        
        # Get full activity status for dashboard
        result = activity(action="status")
        
        # Get formatted summary for display
        result = activity(action="summary")

    Environment Variables:
        STRANDS_THROTTLE_LIMIT: Max external actions per day (default: 30)
        GITHUB_REPOSITORY_OWNER: Agent's GitHub username
    """
    try:
        if action == "status":
            result = get_agent_activity(username=username, hours=hours)
            return ToolResult(
                status="success",
                content=[{"text": str(result)}],
            )

        elif action == "summary":
            summary = get_activity_summary()
            return ToolResult(
                status="success",
                content=[{"text": summary}],
            )

        elif action == "check":
            result = get_agent_activity(username=username, hours=hours)
            can_proceed = result.get("can_proceed", True)
            message = result.get("message", "")
            
            return ToolResult(
                status="success" if can_proceed else "error",
                content=[{
                    "text": f"can_proceed: {can_proceed}\nmessage: {message}\nremaining: {result.get('remaining_actions', '?')}"
                }],
            )

        else:
            return ToolResult(
                status="error",
                content=[{"text": f"Unknown action: {action}. Use 'status', 'summary', or 'check'"}],
            )

    except Exception as e:
        return ToolResult(
            status="error",
            content=[{"text": f"Activity check failed: {e}"}],
        )


# Tool metadata for registration
activity.name = "activity"
activity.description = """Query agent activity and throttle status.

Use this tool to:
- Check if the agent is throttled before making external actions
- Get activity summary for dashboards
- Monitor compliance with rate limits

Actions:
- "status": Full activity data (external/internal counts, events)
- "summary": Formatted markdown summary
- "check": Quick throttle check (can_proceed boolean)

The agent counts external actions (outside its own repos) toward a daily limit.
Default limit is 30 actions per day, configurable via STRANDS_THROTTLE_LIMIT.
"""
