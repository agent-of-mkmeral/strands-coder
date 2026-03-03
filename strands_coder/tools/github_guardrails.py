"""GitHub guardrails for restricting agent access to allowed organizations/users.

This module provides application-level constraints on which GitHub repositories
the agent tools can interact with, regardless of the token's actual permissions.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Organizations and users the agent is allowed to interact with
ALLOWED_OWNERS = {
    "strands-agents",
    "mkmeral",
}


def validate_repo_owner(repo: str) -> str | None:
    """Validate that a repository belongs to an allowed owner.

    Args:
        repo: Repository in "owner/repo" format

    Returns:
        None if valid, error message string if blocked
    """
    if "/" not in repo:
        return f"Error: Invalid repo format '{repo}', expected 'owner/repo'"

    owner = repo.split("/")[0].lower()
    if owner not in {o.lower() for o in ALLOWED_OWNERS}:
        logger.warning(f"Blocked request to repo '{repo}' - owner '{owner}' not in ALLOWED_OWNERS")
        return (
            f"Error: Repository owner '{owner}' is not in the allowed list. "
            f"Allowed owners: {', '.join(sorted(ALLOWED_OWNERS))}"
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


def validate_graphql_owner(variables: dict) -> str | None:
    """Validate that a GraphQL query targets an allowed owner.

    Args:
        variables: GraphQL query variables dict

    Returns:
        None if valid or owner can't be determined, error message if blocked
    """
    owner = extract_owner_from_graphql_variables(variables)
    if owner is None:
        # Can't determine owner from variables — allow (could be a user query, etc.)
        return None

    if owner.lower() not in {o.lower() for o in ALLOWED_OWNERS}:
        logger.warning(f"Blocked GraphQL request targeting owner '{owner}' - not in ALLOWED_OWNERS")
        return (
            f"Error: Target owner '{owner}' is not in the allowed list. "
            f"Allowed owners: {', '.join(sorted(ALLOWED_OWNERS))}"
        )
    return None
