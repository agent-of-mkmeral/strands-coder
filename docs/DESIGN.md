# Strands Coder Design Document

## Overview

Strands Coder is an autonomous GitHub agent built with [Strands Agents SDK](https://github.com/strands-agents/sdk-python). It responds to GitHub events (issues, PRs, comments), executes scheduled tasks, and proactively contributes to repositories.

This document outlines the safety guardrails, limitations, and design decisions that make autonomous agent operation safe and valuable.

---

## How It Works

```
GitHub Event → Context Injection → RAG Retrieval → Agent Reasoning → Tool Execution → Learning
```

1. **Event Trigger**: Issues, PRs, comments, schedules, or manual dispatch
2. **Context Building**: Full conversation thread via GraphQL (not just the latest message)
3. **Knowledge Retrieval**: RAG from Bedrock Knowledge Base for past context
4. **Reasoning**: Claude models with explicit system prompt guidance
5. **Action**: Scoped tool execution (GitHub API, shell commands, etc.)
6. **Learning**: Store insights back to knowledge base for future runs

---

## Safety Guardrails

### 1. Scoped Credentials (Principle: Minimum Privilege)

| Token | Scope | Can Do | Cannot Do |
|-------|-------|--------|-----------|
| `GITHUB_TOKEN` | Own repository | Comment, create PRs, read code | Merge, delete branches, modify settings |
| `PAT_TOKEN` | External repos | Comment, open PRs (as external contributor) | Admin actions, force push |

**Why**: If the agent misbehaves, the worst case is "excessive commenting"—not repository corruption. Maintainer tokens are **never** used.

> *Reference: "Never give agents maintainer tokens" - Agent Guidelines*

### 2. Fork-Based PR Workflow

The agent operates on **forks**, not the main repository:

```bash
# Agent's workflow
git clone upstream/repo
git remote add fork agent-fork/repo
git checkout -b fix/issue-123
# ... make changes ...
git push fork fix/issue-123
# Create PR from fork → upstream
```

**Why**: The agent cannot accidentally push to protected branches. All changes go through PR review.

### 3. Mandatory Local Checks Before Commit

```bash
# REQUIRED before every commit
hatch fmt --formatter
hatch fmt --linter  
hatch test
```

**Why**: Fail locally in 10 seconds, not on CI in 10 minutes. Prevents broken PRs from wasting reviewer time.

### 4. Activity Throttling

- **Default limit**: Natural throttling through GitHub Actions minutes
- **Per-execution**: Agent completes one coherent task per run
- **Scheduled runs**: Configurable via `AGENT_SCHEDULES` (default: every 4 hours)

**Why**: Prevents notification flooding. Maintainers can keep up with agent activity.

> *Reference: "Don't flood the repository. Maintainers need to keep up." - Agent Guidelines*

### 5. Command Timeouts

```python
shell(command="...", timeout=30)  # ALWAYS required
```

| Operation | Timeout |
|-----------|---------|
| Quick commands | 5-10s |
| Git operations | 30s |
| Network requests | 30s |
| Build/test | 120s |

**Why**: Prevents hung commands from consuming GitHub Actions minutes or blocking execution.

### 6. Explicit AI Disclosure

Every public comment ends with:

```markdown
---
🤖 *AI agent response. [Strands Agents](https://github.com/strands-agents). Feedback welcome!*
```

**Why**: Transparency. Users know they're interacting with an AI, not a human.

---

## Limitations

### What the Agent Cannot Do

| Action | Why Not |
|--------|---------|
| Merge PRs | No maintainer permissions |
| Delete branches | Scoped token limitation |
| Modify repo settings | No admin access |
| Force push | Protected branch rules |
| Access private repos (unless configured) | Token scope |
| Execute arbitrary binaries | Sandboxed GitHub Actions runner |

### What the Agent Should Not Do (System Prompt Guidance)

| Anti-Pattern | Enforcement |
|--------------|-------------|
| Summarize CI status | System prompt explicitly prohibits |
| Post approval recommendations | System prompt: "No approval recommendations from AI" |
| Multiple comments per PR | System prompt: "ONE comment max per PR/issue" |
| Create duplicate PRs | System prompt: "Search existing issues/PRs before creating" |
| Push untested code | System prompt: "MANDATORY checks before commit" |

---

## How We Avoid Common Agent Problems

### Problem: Agent commenting on wrong repositories

**Solution**: 
- Explicit repository scoping in workflow triggers
- `GITHUB_TOKEN` automatically scopes to the triggering repository
- PAT_TOKEN used only for configured upstream repos

### Problem: Excessive/noisy comments

**Solution**:
- System prompt: "If nothing NEW to add, don't comment"
- One comment maximum per PR/issue
- Progressive disclosure (collapsible details)
- Quality metrics: "Comment quality: Zero noise"

> *Reference: "Add Value or Stay Silent" - Agent Guidelines*

### Problem: Agent making destructive changes

**Solution**:
- Fork-based workflow (never direct push)
- No maintainer tokens
- All changes via PR (human review gate)
- Protected branch rules enforced

### Problem: Runaway costs/activity

**Solution**:
- Command timeouts on all operations
- Natural throttling via GitHub Actions minutes
- Scheduled runs with configurable frequency
- Token usage tracked in Langfuse

### Problem: Agent orphaned with no owner

**Solution**:
- Agent runs in repository owner's GitHub Actions
- Repository owner is implicit owner
- Disable by removing workflow file or disabling Actions
- All activity visible in Actions tab

> *Reference: "Every agent needs an owner" - Agent Guidelines*

### Problem: Can't see what agent did

**Solution**:
- Full observability via Langfuse integration
- All traces tagged with `issue:{number}` for filtering
- GitHub Actions logs retained for 90 days
- Knowledge base stores execution summaries

> *Reference: "You can't fix what you can't see" - Agent Guidelines*

### Problem: Agent can't be stopped quickly

**Solution**:
- Disable GitHub Actions workflow (immediate)
- Remove PAT_TOKEN secret (prevents external actions)
- Add `[skip-agent]` to issue/PR title (convention)
- Repository maintainer has full control

> *Reference: "Maintainers Can Pull the Cord" - Agent Guidelines*

---

## What the Agent Can Do

### Valuable Contributions

| Capability | Example |
|------------|---------|
| **PR Reviews** | Inline suggestions with `suggestion` blocks |
| **Issue Triage** | Reproduce bugs, request clarification |
| **Documentation** | Fix typos, improve examples |
| **Code Fixes** | Bug fixes with tests (after local verification) |
| **Project Tracking** | Update GitHub Projects board status |
| **Scheduled Tasks** | Daily code review, weekly reports |

### Self-Evolution

The agent learns from each interaction:

```python
# End of every execution
store_in_kb(content="Summary of work done")
system_prompt(action="add_context", context="Learning: ...")
```

---

## Architecture Decisions

### Why GitHub Actions?

- **Sandboxed**: Runs in isolated container
- **Auditable**: Full logs, 90-day retention
- **Controllable**: Disable via repo settings
- **Scoped**: GITHUB_TOKEN auto-scoped to repo
- **No infrastructure**: No servers to manage

### Why Fork-Based Workflow?

- Cannot accidentally push to main
- All changes require PR approval
- Works with protected branches
- Same workflow as external contributors

### Why Two Workflows?

| Workflow | Purpose |
|----------|---------|
| `agent.yml` | Main agent execution (events + dispatch) |
| `control.yml` | Hourly scheduler check (dispatches agent.yml) |

Separation prevents the agent from modifying its own scheduler.

---

## Quick Reference

### Safe by Default

✅ Scoped credentials (no maintainer tokens)  
✅ Fork-based PRs (no direct push)  
✅ Mandatory local tests  
✅ Command timeouts  
✅ AI disclosure on all comments  
✅ Full observability (Langfuse + Actions logs)  
✅ Easy disable (remove workflow or secret)

### Explicit Limitations

❌ Cannot merge PRs  
❌ Cannot delete branches  
❌ Cannot modify repo settings  
❌ Cannot bypass protected branches  
❌ System prompt prohibits approval recommendations  
❌ System prompt prohibits noise comments

---

## Links

- [Agent Guidelines](https://github.com/mkmeral/strands-docs/blob/main/designs/agent-guidelines.md) - Full rationale
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python) - Framework
- [Dashboard](https://dev.strands.my) - Web interface
- [README](../README.md) - Full documentation
