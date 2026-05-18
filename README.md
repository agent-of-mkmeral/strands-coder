<div align="center">
  <div>
    <a href="https://strandsagents.com">
      <img src="https://strandsagents.com/latest/assets/logo-github.svg" alt="Strands Agents" width="55px" height="105px">
    </a>
  </div>

  <h1>Strands Coder</h1>

  <p><b>Autonomous GitHub Agent for Strands Agents — Maintainer Operations</b></p>
  
  <p>
    <a href="https://github.com/marketplace/actions/strands-coder">Marketplace</a>
    · <a href="https://strandsagents.com/">Strands Docs</a>
    · <a href="https://github.com/strands-agents/sdk-python">Strands SDK</a>
  </p>
  
  <h3>
    📊 <a href="https://agent-of-mkmeral.github.io/strands-dashboard/">Dashboard</a>
    &nbsp;·&nbsp;
    🌍 <a href="https://agent-of-mkmeral.github.io/strands-dashboard/activity.html">Activity</a>
  </h3>
</div>

---

> **🔴 Want to disable the agent?** Go to **Settings → Actions → General → Disable Actions** on this repo. That turns off everything — no events, no mentions, no scheduled jobs. To re-enable, flip it back on.

---

This is **Strands Coder** — an autonomous GitHub agent built on [Strands Agents SDK](https://github.com/strands-agents/sdk-python). The reference deployment (`@agent-of-mkmeral`) reviews PRs, triages issues, writes code, and manages project boards across `strands-agents/*` repositories. This repo contains the code, prompts, skills, and workflows so you can see how it works, fork it, or run your own.

**All Strands Agents maintainers are authorized** — you can mention `@agent-of-mkmeral` in any `strands-agents/*` repo and it will respond.

## 🚀 Quick Reference

| What | How |
|------|-----|
| **Mention the agent** | `@agent-of-mkmeral` in any issue, PR, or discussion comment |
| **Response time** | ~15 minutes (mention polling interval) |
| **Trigger manually** | Actions → Agent → Run workflow → enter prompt |
| **See live logs** | Actions tab → click running workflow |
| **Dashboard** | [agent-of-mkmeral.github.io/strands-dashboard](https://agent-of-mkmeral.github.io/strands-dashboard/) |

---

## 📖 How to Use

### Mentioning the Agent

Mention `@agent-of-mkmeral` anywhere in a `strands-agents/*` repository:

```
@agent-of-mkmeral please review this PR and suggest improvements
```

```
@agent-of-mkmeral can you write tests for the new streaming module?
```

```
@agent-of-mkmeral investigate the memory leak reported in #42
```

The agent picks up mentions **every 15 minutes** via `mentions.yml`. It checks that the mentioning user is in `AUTHORIZED_USERS`, then dispatches the main `agent.yml` workflow with the full issue/PR context.

### What It Can Do

- **Review PRs** — inline code suggestions with `suggestion` blocks
- **Implement features** — writes code, runs tests, creates PRs
- **Triage issues** — asks clarifying questions, proposes solutions
- **Write docs** — follows the Strands style guide
- **Manage project boards** — tracks work in GitHub Projects V2
- **Schedule tasks** — cron-based recurring jobs

<details>
<summary><b>Manual Dispatch (workflow_dispatch)</b></summary>

Go to **Actions → Agent → Run workflow** and enter a freeform prompt:

```
Review all open PRs in strands-agents/sdk-python and summarize status
```

You can optionally override `system_prompt` and `tools` for the run.

</details>

---

## 🏗️ Design

The agent is built with [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and runs entirely in GitHub Actions. No persistent infrastructure — each invocation spins up a fresh runner, does its work, and shuts down.

```
┌─────────────────────────────────────────────────┐
│  GitHub Events (issues, PRs, comments, etc.)    │
│  @mentions (polled every 15 min)                │
│  Scheduled jobs (hourly control loop)           │
│  Manual dispatch (workflow_dispatch)            │
└────────────────────┬────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────┐
│  agent.yml                                      │
│  ┌───────────┐  ┌───────────┐  ┌─────────────┐ │
│  │ Auth Check ├──┤ Checkout  ├──┤ Agent Runner │ │
│  │ (secret)   │  │           │  │ (Python)    │ │
│  └───────────┘  └───────────┘  └──────┬──────┘ │
└────────────────────────────────────────┼────────┘
                                         ▼
          ┌──────────────────────────────────────┐
          │  Strands Agent                       │
          │  ├─ Context injection (GraphQL)      │
          │  ├─ KB retrieval (Bedrock RAG)       │
          │  ├─ LLM reasoning (Claude)           │
          │  ├─ Tool execution                   │
          │  │   ├─ use_github (GraphQL API)     │
          │  │   ├─ shell (code, tests, git)     │
          │  │   ├─ projects (GitHub Projects)   │
          │  │   ├─ scheduler (cron jobs)        │
          │  │   ├─ create_subagent (parallel)   │
          │  │   └─ store_in_kb (memory)         │
          │  └─ KB storage (learnings)           │
          └──────────────────────────────────────┘
```

<details>
<summary><b>Workflow Files</b></summary>

| File | Purpose | Trigger |
|------|---------|---------|
| `agent.yml` | Main agent — handles all events, dispatches, scheduled runs | Issues, PRs, comments, discussions, workflow_dispatch |
| `mentions.yml` | Polls GitHub notifications for `@agent-of-mkmeral` mentions across all repos | Every 15 minutes (cron) |
| `control.yml` | Checks `AGENT_SCHEDULES` variable and dispatches due jobs to `agent.yml` | Hourly (cron) or manual |
| `auto-release.yml` | Builds and publishes to PyPI on version tags | Push `v*.*.*` tag |

</details>

<details>
<summary><b>Code Structure</b></summary>

```
strands-coder/
├── strands_coder/
│   ├── agent_runner.py          # Entry point — loads tools, model, runs agent
│   ├── context.py               # System prompt assembly, GitHub event context
│   ├── activity.py              # Activity tracking & throttle enforcement
│   └── tools/
│       ├── use_github.py        # GitHub GraphQL with guardrails
│       ├── github_guardrails.py # Owner allowlist enforcement
│       ├── projects.py          # GitHub Projects V2 management
│       ├── scheduler.py         # Cron job management
│       ├── create_subagent.py   # Parallel agent spawning
│       ├── store_in_kb.py       # Bedrock KB storage (async)
│       └── system_prompt.py     # Runtime prompt modification
├── skills/                      # Task-specific SOPs (loaded on demand)
│   ├── task-implementer/        # TDD implementation workflow
│   ├── task-reviewer/           # Code review workflow
│   ├── task-doc-writer/         # Documentation writing
│   ├── task-adversarial-tester/ # Break things on purpose
│   ├── task-refiner/            # Issue refinement
│   └── task-release-notes/      # Release note generation
├── action.yml                   # GitHub Action composite definition
├── SYSTEM_PROMPT.md             # Agent's full system prompt (SOPs, rules)
└── .github/workflows/           # CI/CD workflows
```

</details>

<details>
<summary><b>Context Injection</b></summary>

Every agent run gets **full conversation context** injected into the system prompt — not just the latest message:

1. **Raw `GITHUB_CONTEXT`** — the complete event payload
2. **GraphQL enrichment** — fetches all comments, reviews, linked items, timeline events
3. **Project context** — current project board state (if configured)
4. **Knowledge Base retrieval** — semantically similar past interactions
5. **Self-awareness** — the agent's own source code (for debugging itself)

This means when you mention the agent in comment #15 of an issue, it sees the entire thread — all 14 prior comments, linked PRs, and project status.

</details>

---

## 🔒 Security & Guardrails

Multiple layers prevent misuse and contain blast radius:

| Layer | What | How |
|-------|------|-----|
| **User authorization** | Only approved users can trigger the agent | `AUTHORIZED_USERS` secret checked in `agent.yml` |
| **Mention authorization** | Only approved users' @mentions are processed | `mentions.yml` verifies author before dispatch |
| **Self-trigger protection** | Agent can't trigger itself via comments | `agent.yml` blocks agent account except for `workflow_dispatch` |
| **Owner allowlist** | Agent can only access repos owned by `agent-of-mkmeral`, `strands-agents`, `strands-labs`, `mkmeral` | `github_guardrails.py` — enforced at tool level |
| **Activity throttling** | Max 30 external actions per 24h, auto-enforced on all mutations | `activity.py` → `enforce_throttle()` called by `use_github.py` and `github_tools.py` |
| **Token separation** | `GITHUB_TOKEN` for own repos, `PAT_TOKEN` for upstream | Prevents recursive workflow triggers |
| **Mutation consent** | Mutations require confirmation (bypassed in CI) | `BYPASS_TOOL_CONSENT=true` in Actions |
| **Dashboard warnings** | Real-time alerts for unauthorized repos, throttle breaches, failures | Dashboard tab — auto-computed from live data |


<details>
<summary><b>AUTHORIZED_USERS</b></summary>

Stored as a **repository secret** (`Settings → Secrets → AUTHORIZED_USERS`). Comma-separated list of GitHub usernames:

```
mkmeral,ryanycoleman,zastrowm,yonib05,Unshure,chaynabors,afarntrog,notowen333,...
```

Both `agent.yml` (direct triggers) and `mentions.yml` (cross-repo mentions) check this list. Unauthorized users are silently ignored — no error response, no notification.

To **add a maintainer**: Update the `AUTHORIZED_USERS` secret with their GitHub username.

</details>

<details>
<summary><b>Owner Allowlist (github_guardrails.py)</b></summary>

Every `use_github` GraphQL call passes through `validate_graphql_owner()` which checks that the target repository owner is in `ALLOWED_OWNERS`:

```python
ALLOWED_OWNERS = {
    "agent-of-mkmeral",
    "strands-agents",
    "strands-labs",
    "mkmeral",
}
```

If the agent tries to interact with a repo outside this list, the request is **blocked at the application level** — even if the PAT token has broader permissions.

The list can be extended at runtime via the `STRANDS_ALLOWED_OWNERS` environment variable (comma-separated). The `_get_allowed_owners()` helper merges both sources.

To modify: Edit `strands_coder/tools/github_guardrails.py` or set the `STRANDS_ALLOWED_OWNERS` env var.

</details>

<details>
<summary><b>Self-Trigger Protection</b></summary>

The agent account (`agent-of-mkmeral`) **cannot** trigger itself through normal GitHub events:

```yaml
# From agent.yml
if [ "${{ github.actor }}" = "$AGENT_ACCOUNT" ]; then
  if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
    # ✅ Allowed — explicit sub-agent handoff
  else
    # ❌ Blocked — prevents infinite comment→trigger loops
  fi
fi
```

This means if the agent posts a comment on a PR, that comment won't re-trigger the agent. The only way the agent can invoke itself is through explicit `workflow_dispatch` (used by sub-agents).

</details>

---

## 📊 Observability

### Traces

Two observability backends are supported:

| Backend | Setup | What You See |
|---------|-------|--------------|
| **AWS Bedrock GenAI Console** | Set `enable_otel: true` in `agent.yml` | Traces in the Bedrock Observability dashboard |
| **Langfuse** | Set `LANGFUSE_*` secrets | Full trace trees, token costs, conversation replay |

All traces are tagged with `issue:{number}` so you can filter by the GitHub issue/PR that triggered the run.

<details>
<summary><b>AgentCore Observability Setup</b></summary>

The `action.yml` sets the correct env vars for the [AWS docs for non-runtime agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html#observability-configure-3p):

```yaml
# In agent.yml
enable_otel: ${{ vars.STRANDS_OTEL_ENABLED || 'false' }}
```

This installs `aws-opentelemetry-distro>=0.10.1`, sets `OTEL_PYTHON_DISTRO=aws_distro`, and runs the agent through `opentelemetry-instrument`. Traces appear in the Bedrock GenAI observability console under service name `strands-coder`.

</details>

<details>
<summary><b>Langfuse Setup</b></summary>

Add these **secrets**:

```
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
```

The agent auto-configures OTEL to export to Langfuse. Traces include:
- Full LLM reasoning chains
- Tool call inputs/outputs
- Token usage and costs
- Session continuity across runs

</details>

### Knowledge Base (Memory)

The agent uses an **Amazon Bedrock Knowledge Base** for persistent memory:

- **Before each run:** `retrieve()` — fetches semantically similar past interactions
- **After each run:** `store_in_kb()` — stores the execution summary

This gives the agent context from previous runs. Configure via `STRANDS_KNOWLEDGE_BASE_ID` repo variable.

### Session Persistence

Conversation history is stored in **S3** for multi-turn sessions:

```
S3_SESSION_BUCKET=my-bucket
S3_SESSION_PREFIX=strands-coder/sessions/
```

### Dashboard

The dashboard is hosted publicly at [**agent-of-mkmeral/strands-dashboard**](https://github.com/agent-of-mkmeral/strands-dashboard):

| Page | URL | What |
|------|-----|------|
| 📊 **Dashboard** | [strands-dashboard](https://agent-of-mkmeral.github.io/strands-dashboard/) | Project board, issues, actions, traces, agent config, schedule, **warnings** |
| 🌍 **Wild** | [strands-dashboard/#wild](https://agent-of-mkmeral.github.io/strands-dashboard/#wild) | Open PRs & issues the agent created in external public repos |
| 📈 **Activity** | [activity.html](https://agent-of-mkmeral.github.io/strands-dashboard/activity.html) | Agent activity overview across all public repos |

<details>
<summary><b>Dashboard Warnings</b></summary>

The Dashboard tab includes a **warnings system** that surfaces issues in real time. Warnings appear at the top of the page, above the project stats grid:

| Severity | Warning | Trigger |
|----------|---------|---------|
| 🔴 **Critical** | Unauthorized Repo Interaction | Activity detected in repos outside allowed owners |
| 🔴 **Critical** | Throttle Limit Exceeded | ≥30 external actions in 24h |
| 🟡 **Warning** | Approaching Throttle | ≥80% of daily limit used (≥24/30) |
| 🟡 **Warning** | Consecutive Failures | 3+ failed actions in a row |
| 🟡 **Warning** | Long-Running Action | Action running >45 minutes |
| 🟡 **Warning** | High Failure Rate | >50% of last 10 runs failed |
| 🔵 **Info** | Stale External Items | Open PRs/issues with no updates for 7+ days |

Warnings are severity-colored (red/amber/blue) with icons and detail text. A badge on the Dashboard nav tab shows the count (red dot for critical, amber for warnings). If there are no warnings, the dashboard is clean — no noise.

</details>

---

## ⚙️ Configuration

All configuration lives in **repository variables and secrets** — no code changes needed.

### Secrets (Settings → Secrets → Actions)

| Secret | Required | Description |
|--------|----------|-------------|
| `AWS_ROLE_ARN` | ✅ | IAM role for Bedrock access (OIDC) |
| `PAT_TOKEN` | ✅ | GitHub PAT with repo + workflow permissions |
| `AUTHORIZED_USERS` | ✅ | Comma-separated authorized usernames |
| `LANGFUSE_BASE_URL` | ❌ | Langfuse host (e.g., `https://cloud.langfuse.com`) |
| `LANGFUSE_PUBLIC_KEY` | ❌ | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | ❌ | Langfuse secret key |

### Variables (Settings → Variables → Actions)

| Variable | Default | Description |
|----------|---------|-------------|
| `STRANDS_PROVIDER` | `bedrock` | Model provider |
| `STRANDS_MODEL_ID` | (SDK default) | Model ID (e.g., `us.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| `STRANDS_MAX_TOKENS` | (SDK default) | Max output tokens |
| `STRANDS_TOOLS` | (see agent.yml) | Tool configuration string |
| `STRANDS_KNOWLEDGE_BASE_ID` | — | Bedrock Knowledge Base ID for RAG |
| `STRANDS_CODER_PROJECT_ID` | — | GitHub Project V2 node ID |
| `S3_SESSION_BUCKET` | — | S3 bucket for session persistence |
| `AGENT_SCHEDULES` | `{}` | JSON schedule configuration |
| `MCP_SERVERS` | — | MCP server configuration JSON |
| `SYSTEM_PROMPT` | (from SYSTEM_PROMPT.md) | System prompt override |
| `STRANDS_ALLOWED_OWNERS` | — | Additional allowed repo owners (comma-separated, merged with built-in list) |
| `STRANDS_OTEL_ENABLED` | `false` | Enable AgentCore observability |

<details>
<summary><b>AGENT_SCHEDULES Format</b></summary>

```json
{
  "jobs": {
    "daily_review": {
      "cron": "0 9 * * *",
      "enabled": true,
      "prompt": "Review open PRs and provide feedback",
      "tools": "strands_tools:shell;strands_coder:use_github"
    },
    "weekly_report": {
      "cron": "0 10 * * 1",
      "enabled": true,
      "prompt": "Generate weekly status report"
    }
  }
}
```

Cron format: `minute hour day month weekday`

</details>

<details>
<summary><b>MCP_SERVERS Format</b></summary>

```json
{
  "mcpServers": {
    "strands-docs": {
      "command": "uvx",
      "args": ["strands-agents-mcp-server"],
      "disabled": false,
      "disabledTools": []
    }
  }
}
```

</details>

<details>
<summary><b>Tools Configuration String</b></summary>

Format: `package:tool1,tool2;package2:tool3,tool4`

Default tools:
```
strands_tools:shell,retrieve,slack;strands_coder:use_github,create_subagent,system_prompt,store_in_kb,projects,scheduler
```

</details>

---

## 🔴 How to Disable

### Disable everything

**Easiest:** Go to **Settings → Actions → General → Disable Actions**. This stops all workflows — no events, no mentions, no scheduled jobs.

Alternatively:
1. **Remove or empty `AUTHORIZED_USERS` secret** — blocks all event-triggered runs
2. **Delete `AWS_ROLE_ARN` secret** — agent can't authenticate to Bedrock

### Disable specific triggers

| What | How |
|------|-----|
| **Stop all event reactions** | Comment out the `on:` triggers in `agent.yml` (keep `workflow_dispatch` for manual use) |
| **Stop cross-repo mentions** | Comment out the `schedule:` in `mentions.yml` |
| **Stop scheduled jobs** | Comment out the `schedule:` in `control.yml` |
| **Stop a specific scheduled job** | `scheduler(action="disable", job_id="job_name")` or edit `AGENT_SCHEDULES` variable |
| **Pause temporarily** | Disable the workflow in GitHub Actions UI (Actions → workflow → ⋯ → Disable workflow) |

### Disable for a specific user

Remove their username from the `AUTHORIZED_USERS` secret.

---

## 🧬 Skills System

The agent loads task-specific SOPs (Standard Operating Procedures) on demand via the **AgentSkills plugin**:

| Skill | When Used |
|-------|-----------|
| `task-implementer` | Writing code with TDD, creating PRs |
| `task-reviewer` | Reviewing PRs with inline suggestions |
| `task-doc-writer` | Writing documentation following Strands style |
| `task-adversarial-tester` | Finding bugs, edge cases, security holes |
| `task-refiner` | Refining issues, asking clarifying questions |
| `task-release-notes` | Generating release notes from merged PRs |

Skills live in `skills/` — each has a `SKILL.md` with detailed instructions. The agent calls `skills(skill_name="task-reviewer")` before starting a review, which loads the full SOP into context.

**Want to add a new skill?** Just [create an issue](../../issues/new) describing the skill you need and the agent will build it.

---

## 🤖 Agent Behavior Rules

Key rules from `SYSTEM_PROMPT.md` that maintainers should know:

| Rule | Details |
|------|---------|
| **Add value or stay silent** | The agent won't post "LGTM" or status updates. If it has nothing concrete to add, it stays quiet |
| **One comment max** | Per PR/issue — no spam |
| **Collapsible format** | Every comment uses TL;DR + `<details>` for progressive disclosure |
| **AI disclosure** | Every public comment ends with `🤖 AI agent response. Strands Agents.` |
| **Never push to upstream** | Only pushes to `agent-of-mkmeral/*` forks, creates PRs to upstream |
| **Mentions policy** | Only tags `@mkmeral` — uses backtick formatting for all other usernames |
| **Test before commit** | Runs `hatch fmt` + `hatch test` before every commit |

<details>
<summary><b>Full System Prompt</b></summary>

See [`SYSTEM_PROMPT.md`](SYSTEM_PROMPT.md) for the complete agent instructions including:
- Push policies and repository map
- Comment format requirements
- PR review format with suggestion blocks
- Memory protocol (retrieve → act → store)
- Sub-agent delegation strategy

</details>

---

## 🔧 Common Operations

<details>
<summary><b>Change the model</b></summary>

Update the `STRANDS_MODEL_ID` repository variable:

```
Settings → Variables → Actions → STRANDS_MODEL_ID
```

Available models (Bedrock):
- `us.anthropic.claude-sonnet-4-5-20250929-v1:0` — balanced (recommended)
- `us.anthropic.claude-opus-4-20250514-v1:0` — most capable
- `us.anthropic.claude-sonnet-4-20250514-v1:0` — fast

</details>

<details>
<summary><b>Add a new authorized user</b></summary>

1. Go to `Settings → Secrets → Actions → AUTHORIZED_USERS`
2. Add the GitHub username to the comma-separated list
3. They can now mention `@agent-of-mkmeral` and it will respond

</details>

<details>
<summary><b>Schedule a recurring task</b></summary>

Either ask the agent:
```
@agent-of-mkmeral schedule a job called "weekly_review" to run every Monday at 9 AM UTC 
with prompt "Review all open PRs across strands-agents repos"
```

Or edit the `AGENT_SCHEDULES` variable directly in `Settings → Variables → Actions`.

</details>

<details>
<summary><b>Debug a failed run</b></summary>

1. Go to **Actions → Agent** and find the failed run
2. Check the **Agent** step logs for the full execution trace
3. Look at **GitHub Actions Summary** for the prompt, result, and session ID
4. If Langfuse is configured, search traces by the `issue:{number}` tag
5. If AgentCore is enabled, check the Bedrock GenAI observability console

</details>

<details>
<summary><b>Update the system prompt</b></summary>

Two options:
1. **Edit `SYSTEM_PROMPT.md`** — the source of truth, loaded on every run
2. **Set `SYSTEM_PROMPT` variable** — overrides `SYSTEM_PROMPT.md` if set

The agent can also update its own prompt at runtime via `system_prompt(action="add_context")`.

</details>

---

## 📄 License

Apache-2.0 — see [LICENSE](LICENSE).
