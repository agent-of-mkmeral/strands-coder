"""GitHub guardrails for restricting agent access to allowed organizations/users.

This module provides application-level constraints on which GitHub repositories
the agent tools can interact with, regardless of the token's actual permissions.

Guardrail layers:
1. Owner validation — extracts owner from explicit GraphQL variables (owner, repositoryOwner, etc.)
2. Node ID resolution — detects opaque GitHub node IDs in mutation variables and resolves
   them via the GitHub API to determine the target repository owner (Fix 1 & Fix 2 from #57)
3. Strict mutation mode — blocks mutations when the target owner cannot be determined,
   instead of silently allowing them (Fix 3 from #57)
"""

import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Organizations and users the agent is allowed to interact with.
# Includes the agent's own account, the user's account, and trusted orgs.
ALLOWED_OWNERS = {
    "agent-of-mkmeral",
    "strands-agents",
    "strands-labs",
    "mkmeral",
    "opieter-aws",
}

# ---------------------------------------------------------------------------
# Fix 2: Detect GitHub node IDs in variables
# ---------------------------------------------------------------------------
# GitHub node IDs follow a pattern: TYPE_prefix + base64 payload
# Common prefixes: PR_ (PullRequest), I_ (Issue), R_ (Repository),
# MDQ6 (legacy), IC_ (IssueComment), PVTI_ (ProjectV2Item), etc.
# Pattern: 1+ uppercase letters, underscore, 1+ base64 chars (at least 8 chars total)
# Includes - for URL-safe base64 encoding used in some GitHub node IDs
NODE_ID_PATTERN = re.compile(r"^[A-Z][A-Za-z]*_[a-zA-Z0-9+/=\-]{4,}$")

# Node ID prefixes that represent repository-scoped resources
# (i.e., resources that belong to a specific repository)
REPO_SCOPED_PREFIXES = {
    "PR_",  # PullRequest
    "I_",  # Issue
    "IC_",  # IssueComment
    "R_",  # Repository
    "RE_",  # Release
    "RC_",  # ReviewComment
    "CC_",  # CommitComment
    "DI_",  # Discussion
    "DC_",  # DiscussionComment
    "LA_",  # Label
    "MI_",  # Milestone
}


def _get_allowed_owners() -> set[str]:
    """Get the set of allowed owners, including any from environment.

    Merges the hardcoded ALLOWED_OWNERS with any additional owners
    specified in the STRANDS_ALLOWED_OWNERS environment variable
    (comma-separated).
    """
    owners = set(ALLOWED_OWNERS)

    # Allow extending via environment variable
    env_owners = os.environ.get("STRANDS_ALLOWED_OWNERS", "")
    if env_owners:
        for owner in env_owners.split(","):
            owner = owner.strip()
            if owner:
                owners.add(owner)

    return owners


def validate_repo_owner(repo: str) -> str | None:
    """Validate that a repository belongs to an allowed owner.

    Args:
        repo: Repository in "owner/repo" format

    Returns:
        None if valid, error message string if blocked
    """
    if "/" not in repo:
        return f"Error: Invalid repo format '{repo}', expected 'owner/repo'"

    allowed = _get_allowed_owners()
    owner = repo.split("/")[0].lower()
    if owner not in {o.lower() for o in allowed}:
        logger.warning(f"Blocked request to repo '{repo}' - owner '{owner}' not in ALLOWED_OWNERS")
        return (
            f"Error: Repository owner '{owner}' is not in the allowed list. "
            f"Allowed owners: {', '.join(sorted(allowed))}"
        )
    return None


def extract_owner_from_graphql_variables(variables: dict) -> str | None:
    """Try to extract a repo owner from GraphQL variables.

    Checks common variable patterns like 'owner', 'repositoryOwner',
    or parses 'owner/name' from a 'repository' variable.

    Args:
        variables: GraphQL query variables dict

    Returns:
        Owner string if found, None otherwise
    """
    for key in ("owner", "repositoryOwner", "organizationLogin", "login"):
        if key in variables:
            return variables[key]

    if "repository" in variables and "/" in str(variables["repository"]):
        return str(variables["repository"]).split("/")[0]

    return None


def extract_node_ids_from_variables(variables: dict[str, Any]) -> list[str]:
    """Detect GitHub node IDs in GraphQL variable values, including nested structures.

    Recursively scans all values in the variables dict — including nested dicts
    and lists — for patterns matching GitHub's opaque node ID format
    (e.g., PR_kwDOLMoxBs6cEfv5, I_kwDO...).

    This is Fix 2 from issue #57 (flat variables) and Fix 4 from issue #189
    (nested input objects). The LLM can use either flat or nested GraphQL
    variable patterns for the same mutation:
      - Flat:   {"subjectId": "PR_...", "body": "..."}
      - Nested: {"input": {"subjectId": "PR_...", "body": "..."}}

    Both patterns must be scanned to prevent guardrail bypasses.

    Args:
        variables: GraphQL query variables dict

    Returns:
        List of detected node ID strings
    """
    node_ids: list[str] = []

    def _scan(value: Any) -> None:
        """Recursively scan a value for GitHub node IDs."""
        if isinstance(value, str):
            if NODE_ID_PATTERN.match(value):
                # Additional check: must start with a known prefix or look like a node ID
                # This filters out false positives like simple strings that match the pattern
                if any(value.startswith(prefix) for prefix in REPO_SCOPED_PREFIXES) or len(value) >= 16:
                    node_ids.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                _scan(v)
        elif isinstance(value, list):
            for item in value:
                _scan(item)

    for value in variables.values():
        _scan(value)

    return node_ids


def resolve_node_owner(node_id: str, token: str) -> str | None:
    """Resolve a GitHub node ID to its repository owner.

    Uses the GitHub GraphQL API's `node` interface to look up the resource
    and extract its repository's nameWithOwner, then returns the owner.

    This is Fix 1 from issue #57: pre-flight resolution of opaque node IDs
    to verify the target repository before executing mutations.

    Args:
        node_id: GitHub opaque node ID (e.g., PR_kwDOLMoxBs6cEfv5)
        token: GitHub authentication token

    Returns:
        Owner string (e.g., "strands-agents") if resolved, None if resolution fails
    """
    query = """
    query($id: ID!) {
      node(id: $id) {
        ... on PullRequest { repository { nameWithOwner } }
        ... on Issue { repository { nameWithOwner } }
        ... on IssueComment { repository { nameWithOwner } }
        ... on PullRequestReview { repository { nameWithOwner } }
        ... on PullRequestReviewComment { pullRequest { repository { nameWithOwner } } }
        ... on CommitComment { repository { nameWithOwner } }
        ... on Discussion { repository { nameWithOwner } }
        ... on DiscussionComment { discussion { repository { nameWithOwner } } }
        ... on Release { repository { nameWithOwner } }
        ... on Repository { nameWithOwner }
      }
    }
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v4+json",
        "User-Agent": "Strands-Agent-GitHub-Tool/1.0",
    }

    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query, "variables": {"id": node_id}},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            logger.warning(f"Node ID resolution errors for {node_id}: {data['errors']}")
            return None

        node = data.get("data", {}).get("node")
        if not node:
            logger.warning(f"Node ID {node_id} resolved to null (deleted or inaccessible)")
            return None

        # Extract nameWithOwner from various possible locations
        name_with_owner = None

        # Direct repository field (PullRequest, Issue, IssueComment, etc.)
        repo = node.get("repository")
        if repo and isinstance(repo, dict):
            name_with_owner = repo.get("nameWithOwner")

        # Nested: PullRequestReviewComment → pullRequest → repository
        if not name_with_owner:
            pr = node.get("pullRequest")
            if pr and isinstance(pr, dict):
                repo = pr.get("repository")
                if repo and isinstance(repo, dict):
                    name_with_owner = repo.get("nameWithOwner")

        # Nested: DiscussionComment → discussion → repository
        if not name_with_owner:
            disc = node.get("discussion")
            if disc and isinstance(disc, dict):
                repo = disc.get("repository")
                if repo and isinstance(repo, dict):
                    name_with_owner = repo.get("nameWithOwner")

        # Direct Repository node
        if not name_with_owner:
            name_with_owner = node.get("nameWithOwner")

        if name_with_owner and "/" in name_with_owner:
            owner = name_with_owner.split("/")[0]
            logger.info(f"Resolved node ID {node_id} → {name_with_owner} (owner: {owner})")
            return owner

        logger.warning(f"Could not extract owner from resolved node {node_id}: {node}")
        return None

    except requests.exceptions.RequestException as e:
        logger.warning(f"Node ID resolution request failed for {node_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Node ID resolution failed for {node_id}: {e}")
        return None


def validate_graphql_owner(
    variables: dict,
    is_mutative: bool = False,
    token: str | None = None,
) -> tuple[str | None, str | None]:
    """Validate that a GraphQL query targets an allowed owner.

    For mutations, this function implements three layers of defense:
    1. Check explicit owner variables (owner, repositoryOwner, etc.)
    2. Detect and resolve opaque node IDs to determine the target owner
    3. Block mutations when the target owner cannot be determined (strict mode)

    Args:
        variables: GraphQL query variables dict
        is_mutative: Whether the operation is a mutation (enables strict mode)
        token: GitHub token for node ID resolution (required for mutations with node IDs)

    Returns:
        Tuple of (error_message, resolved_owner).
        - (None, owner) if valid — owner is the resolved target owner (may be None)
        - (error_msg, None) if blocked
    """
    allowed = _get_allowed_owners()
    allowed_lower = {o.lower() for o in allowed}

    # --- Layer 1: Check explicit owner variables ---
    owner = extract_owner_from_graphql_variables(variables)
    if owner is not None:
        if owner.lower() not in allowed_lower:
            logger.warning(f"Blocked GraphQL request targeting owner '{owner}' - not in ALLOWED_OWNERS")
            return (
                f"Error: Target owner '{owner}' is not in the allowed list. "
                f"Allowed owners: {', '.join(sorted(allowed))}"
            ), None
        return None, owner  # Explicitly allowed

    # --- Layer 2: Detect and resolve node IDs (Fix 1 + Fix 2) ---
    if is_mutative and variables:
        node_ids = extract_node_ids_from_variables(variables)
        if node_ids:
            # Get token for resolution
            if not token:
                token = os.environ.get("GITHUB_TOKEN", os.environ.get("PAT_TOKEN", ""))

            if token:
                for node_id in node_ids:
                    resolved_owner = resolve_node_owner(node_id, token)
                    if resolved_owner is not None:
                        if resolved_owner.lower() not in allowed_lower:
                            logger.warning(
                                f"Blocked mutation: node ID {node_id} resolved to owner "
                                f"'{resolved_owner}' which is not in ALLOWED_OWNERS"
                            )
                            return (
                                f"Error: Node ID '{node_id}' belongs to owner '{resolved_owner}' "
                                f"which is not in the allowed list. "
                                f"Allowed owners: {', '.join(sorted(allowed))}. "
                                f"The agent attempted to use an opaque node ID that points to "
                                f"a repository outside the allowed scope."
                            ), None
                        else:
                            # Node ID resolved to an allowed owner — permit
                            logger.info(f"Node ID {node_id} resolved to allowed owner '{resolved_owner}'")
                            return None, resolved_owner
            else:
                logger.warning("No token available for node ID resolution — cannot verify mutation target")

    # --- Layer 3: Strict mode for mutations (Fix 3) ---
    if is_mutative and variables:
        # For mutations, if we have variables but couldn't determine the target owner
        # through any method, block the operation rather than silently allowing it.
        # This prevents hallucinated node IDs from reaching external repos.
        node_ids = extract_node_ids_from_variables(variables) if variables else []
        if node_ids:
            # We found node IDs but couldn't resolve them — BLOCK
            logger.warning(
                f"Blocked mutation with unresolvable node IDs: {node_ids}. Cannot verify target repository owner."
            )
            return (
                f"Error: Cannot verify the target repository for this mutation. "
                f"The variables contain node ID(s) ({', '.join(node_ids)}) that could not "
                f"be resolved to a repository owner. For safety, mutations with unverified "
                f"node IDs are blocked. Please use explicit owner/repo variables instead, "
                f"or ensure the node IDs are correct and accessible."
            ), None

    # For queries (non-mutative): allow when owner unknown (backward compatible)
    if not is_mutative:
        return None, None

    # For mutations without any identifiable variables: allow
    # (These are typically schema introspection or user-scoped mutations)
    if not variables:
        return None, None

    # For mutations with variables but no node IDs and no owner: allow
    # (e.g., addStar with starrableId which is a generic pattern)
    return None, None
