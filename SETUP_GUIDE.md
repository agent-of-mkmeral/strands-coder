# 🤖 Setting Up Your Own Autonomous GitHub Agent

This guide walks you through creating your own autonomous GitHub agent (like `agent-of-mkmeral`) from scratch. The agent runs entirely on GitHub Actions — no persistent servers needed.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start (Automated)](#quick-start-automated)
- [Manual Setup](#manual-setup)
  - [Step 1: Create the Agent GitHub Account](#step-1-create-the-agent-github-account)
  - [Step 2: Create the Private Repository](#step-2-create-the-private-repository)
  - [Step 3: AWS Setup (Bedrock Access)](#step-3-aws-setup-bedrock-access)
  - [Step 4: Configure Repository Secrets](#step-4-configure-repository-secrets)
  - [Step 5: Configure Repository Variables](#step-5-configure-repository-variables)
  - [Step 6: Customize the Agent](#step-6-customize-the-agent)
  - [Step 7: Test the Agent](#step-7-test-the-agent)
- [Optional Integrations](#optional-integrations)
- [Security Model](#security-model)
- [Infrastructure Reference](#infrastructure-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

The agent is a Python application that:
1. **Listens** for GitHub events (issues, PRs, comments, discussions, mentions)
2. **Reasons** using an LLM (Claude via AWS Bedrock) to decide what to do
3. **Acts** using tools (GitHub GraphQL, shell, knowledge base, etc.)
4. **Remembers** via Bedrock Knowledge Base and S3 session persistence

Each invocation is a fresh GitHub Actions runner — stateless compute with persistent memory.

### What You Need

| Requirement | Purpose | Cost |
|-------------|---------|------|
| **GitHub account** (for agent) | The agent's identity — posts comments, creates PRs | Free |
| **GitHub PAT** (Classic) | Authentication for cross-repo access | Free |
| **AWS account** | Bedrock (Claude), optional: KB, S3, CloudWatch | Pay-per-use |
| **This repo** (template) | All the code, workflows, skills | Free |

### Time Estimate

| Setup Level | Time | What You Get |
|-------------|------|--------------|
| **Minimal** | ~15 min | Agent responds to issues/PRs in its own repo |
| **Standard** | ~30 min | + Cross-repo mentions, project tracking |
| **Full** | ~1 hour | + Knowledge Base memory, observability, Slack |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  GitHub Events (issues, PRs, comments, etc.)    │
│  @mentions (polled hourly by mentions.yml)       │
│  Scheduled jobs (control.yml → agent.yml)       │
│  Manual dispatch (workflow_dispatch)            │
└────────────────────┬────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────┐
│  agent.yml  (main workflow)                     │
│  ┌───────────┐  ┌───────────┐  ┌─────────────┐ │
│  │ Auth Check │──│ Checkout  │──│ Agent Runner │ │
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

### Workflow Files

| File | Purpose | Trigger |
|------|---------|---------|
| `agent.yml` | Main agent — handles all events | Issues, PRs, comments, dispatch |
| `mentions.yml` | Polls for @agent mentions across repos | Hourly cron (8am-10pm UTC) |
| `control.yml` | Checks scheduled jobs and dispatches them | Hourly cron |
| `auto-release.yml` | PyPI publish on version tags | Push `v*.*.*` tag |
| `creds.yml` | Dashboard credential vending (CloudWatch) | Manual dispatch |

---

## Quick Start (Automated)

The `setup-agent.sh` script automates the entire setup:

```bash
# Clone this repo
git clone https://github.com/agent-of-mkmeral/strands-coder-private.git
cd strands-coder-private

# Minimal setup
./setup-agent.sh --user YOUR_GITHUB_USERNAME

# Full setup with observability
./setup-agent.sh --user YOUR_GITHUB_USERNAME \
  --enable-observability \
  --enable-kb --kb-id YOUR_KB_ID \
  --enable-s3-sessions --s3-bucket your-bucket

# Dry run (see what would happen)
./setup-agent.sh --user YOUR_GITHUB_USERNAME --dry-run
```

The script will:
1. Guide you through creating the agent GitHub account
2. Create the private repository
3. Set up AWS OIDC (Bedrock access)
4. Configure all secrets and variables
5. Push the template code
6. Optionally create a GitHub Project
7. Run a validation test

**Prerequisites:** `gh` (GitHub CLI), `aws` (AWS CLI), `jq`

---

## Manual Setup

### Step 1: Create the Agent GitHub Account

The agent needs its own GitHub identity to post comments, create PRs, etc.

1. **Create a new GitHub account**
   - Go to https://github.com/join
   - Suggested naming: `agent-of-<your-username>` (e.g., `agent-of-johndoe`)
   - Use a separate email: `youremail+agent@gmail.com`

2. **Create a Personal Access Token (Classic)**
   - Log into the agent account
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - **Required scopes:**
     - `repo` — Full repository access
     - `workflow` — Update GitHub Action workflows
     - `read:org` — Read org membership
     - `read:user` — Read user profile
     - `notifications` — Access notifications (for @mentions)
   - Set expiration to 90 days or "No expiration"
   - **Save the token** — you'll need it in Step 4

3. **Add the agent as a collaborator** to any repos it should access
   - Your private repo: Settings → Collaborators → Add `agent-of-<you>`
   - For org repos: Add to the org or specific repos

### Step 2: Create the Private Repository

The agent's "brain" lives in a private repository. This contains the code, workflows, system prompt, and configuration.

```bash
# Option A: Use GitHub CLI
gh repo create agent-of-<you>/strands-coder-private --private

# Option B: Use GitHub UI
# Go to https://github.com/new and create under the agent account
```

Then clone this template and push:

```bash
# Clone the template
git clone https://github.com/agent-of-mkmeral/strands-coder-private.git template
cd template

# Push to your new repo
git remote set-url origin https://github.com/agent-of-<you>/strands-coder-private.git
git push -u origin main
```

**Files to customize after cloning:**

| File | What to Change |
|------|----------------|
| `SYSTEM_PROMPT.md` | Replace `mkmeral` with your username, `agent-of-mkmeral` with your agent |
| `strands_coder/tools/github_guardrails.py` | Update `ALLOWED_OWNERS` set |
| `strands_coder/activity.py` | Update `_INTERNAL_OWNERS` set |
| `.github/workflows/agent.yml` | Update `git_user_name` and `git_user_email` |
| `.github/workflows/mentions.yml` | Update the `@agent-of-mkmeral` mention string |

### Step 3: AWS Setup (Bedrock Access)

The agent uses AWS Bedrock (Claude) for LLM reasoning. Authentication is via OIDC (no static AWS keys).

```bash
# Run the provided setup script
./setup-aws-oidc.sh --repository agent-of-<you>/strands-coder-private

# With observability
./setup-aws-oidc.sh \
  --repository agent-of-<you>/strands-coder-private \
  --enable-observability \
  --agent-id my-agent
```

This script:
1. Creates a GitHub OIDC Identity Provider in your AWS account
2. Creates an IAM role (`StrandsActionRole`) trusted by your repo
3. Attaches Bedrock permissions
4. (Optional) Sets up CloudWatch observability

**Save the role ARN** from the output — you need it in Step 4.

> **Note:** You need Bedrock model access enabled in your AWS account. Go to Bedrock Console → Model Access → Request access to Anthropic Claude models.

### Step 4: Configure Repository Secrets

Go to your repo: **Settings → Secrets and variables → Actions → Secrets**

| Secret | Required | Value | Description |
|--------|----------|-------|-------------|
| `PAT_TOKEN` | ✅ | `ghp_xxx...` | Agent's GitHub PAT from Step 1 |
| `AUTHORIZED_USERS` | ✅ | `yourname,teammate1,teammate2` | Comma-separated list of users who can trigger the agent |
| `AWS_ROLE_ARN` | ✅ | `arn:aws:iam::123:role/StrandsActionRole` | IAM role from Step 3 |
| `AWS_REGION` | ✅ | `us-west-2` | AWS region where Bedrock is available |
| `LANGFUSE_BASE_URL` | ❌ | `https://cloud.langfuse.com` | Langfuse observability host |
| `LANGFUSE_PUBLIC_KEY` | ❌ | `pk-lf-xxx` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | ❌ | `sk-lf-xxx` | Langfuse secret key |
| `SLACK_BOT_TOKEN` | ❌ | `xoxb-xxx` | Slack bot token |
| `SLACK_APP_TOKEN` | ❌ | `xapp-xxx` | Slack app-level token |
| `ANTHROPIC_API_KEY` | ❌ | `sk-ant-xxx` | Only if using Anthropic directly (not Bedrock) |
| `PERPLEXITY_API_KEY` | ❌ | `pplx-xxx` | For web search via Perplexity |

### Step 5: Configure Repository Variables

Go to your repo: **Settings → Secrets and variables → Actions → Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `STRANDS_PROVIDER` | `bedrock` | Model provider (`bedrock`, `anthropic`, `openai`) |
| `STRANDS_MODEL_ID` | SDK default | e.g., `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `STRANDS_MAX_TOKENS` | SDK default | e.g., `16384` |
| `STRANDS_TOOLS` | (from agent.yml) | Tool config string |
| `STRANDS_KNOWLEDGE_BASE_ID` | — | Bedrock KB ID for RAG memory |
| `STRANDS_CODER_PROJECT_ID` | — | GitHub Project V2 node ID (`PVT_xxx`) |
| `S3_SESSION_BUCKET` | — | S3 bucket for conversation persistence |
| `S3_SESSION_PREFIX` | — | S3 key prefix (e.g., `agent/sessions/`) |
| `AGENT_SCHEDULES` | `{}` | JSON scheduled jobs config |
| `MCP_SERVERS` | — | MCP server configuration JSON |
| `AGENT_ACCOUNT` | — | Agent's GitHub username |
| `STRANDS_OTEL_ENABLED` | `false` | Enable AWS AgentCore observability |
| `STRANDS_ALLOWED_OWNERS` | — | Additional allowed repo owners (comma-separated) |
| `STRANDS_ADDITIONAL_REQUEST_FIELDS` | — | Extra model params (e.g., `{"thinking":{"type":"enabled"}}`) |

### Step 6: Customize the Agent

#### System Prompt (`SYSTEM_PROMPT.md`)

This is the agent's personality, rules, and operating procedures. Key sections to customize:

```markdown
# Update these sections:

## 👤 Personal Context
- Your name, role, projects
- Repository map (upstream, forks, agent forks)

## ⚠️ Push Policy
- Which repos the agent can push to
- Which repos require PRs

## 📚 Standard Operating Procedures
- Skills are loaded on-demand from the skills/ directory
```

#### Guardrails (`strands_coder/tools/github_guardrails.py`)

Update the `ALLOWED_OWNERS` set:

```python
ALLOWED_OWNERS = {
    "agent-of-yourname",    # Agent's own account
    "yourname",             # Your personal account
    "your-org",             # Your org (if applicable)
}
```

Or set via environment variable: `STRANDS_ALLOWED_OWNERS=org1,org2`

#### Activity Throttling (`strands_coder/activity.py`)

Update `_INTERNAL_OWNERS` — repos owned by these users are NOT counted toward the daily limit:

```python
_INTERNAL_OWNERS: set[str] = {
    "yourname",
}
```

### Step 7: Test the Agent

1. **Manual dispatch:** Go to Actions → Agent → Run workflow
   ```
   Prompt: Hello! Run a self-diagnostic and verify all tools work.
   ```

2. **Create an issue:** Open an issue in the repo — the agent should respond

3. **Check logs:** Actions tab → click the running workflow → "Agent" step

---

## Optional Integrations

### Bedrock Knowledge Base (Memory)

The agent can remember past interactions using Amazon Bedrock Knowledge Bases.

1. **Create a Knowledge Base** in the Bedrock console
   - Type: Vector store (Amazon OpenSearch Serverless or Pinecone)
   - Embedding model: Amazon Titan Embeddings
   
2. **Set the variable:**
   ```
   STRANDS_KNOWLEDGE_BASE_ID = <your-kb-id>
   ```

3. **How it works:**
   - Before each run: `retrieve()` fetches semantically similar past interactions
   - After each run: `store_in_kb()` stores the execution summary
   - The IAM role from `setup-aws-oidc.sh` already has Bedrock KB permissions

### S3 Session Persistence

Multi-turn conversations across workflow runs:

1. **Create an S3 bucket** (or use existing)
2. **Set variables:**
   ```
   S3_SESSION_BUCKET = my-agent-bucket
   S3_SESSION_PREFIX = strands-coder/sessions/
   ```
3. Session IDs are deterministic: `gh-{org}-{repo}-issue-{number}`

### GitHub Project Tracking

Track agent work items on a Kanban board:

1. **Create a Project V2** under the agent account
2. **Get the project node ID:**
   ```bash
   gh api graphql -f query='{ user(login: "agent-of-you") { projectsV2(first: 5) { nodes { id title } } } }'
   ```
3. **Set the variable:** `STRANDS_CODER_PROJECT_ID = PVT_xxx`

### Cross-repo Mentions

Let people mention the agent in other repos:

1. **Enable the mentions workflow** — uncomment the `schedule:` in `mentions.yml`
2. **Add the agent as a collaborator** to target repos
3. **Add authorized users** to `AUTHORIZED_USERS` secret
4. Users can now `@agent-of-you please review this PR`

### Langfuse Observability

Full trace trees with token costs:

1. Sign up at https://cloud.langfuse.com
2. Create a project and get API keys
3. Set secrets: `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

### Slack Integration

Agent responds in Slack channels:

1. Create a Slack App at https://api.slack.com/apps
2. Enable Socket Mode, add bot scopes: `chat:write`, `channels:read`, `app_mentions:read`
3. Set secrets: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`

### Dashboard

Fork `agent-of-mkmeral/strands-dashboard` and customize:

1. Fork the repo to your agent account
2. Enable GitHub Pages (Settings → Pages → Deploy from `docs/`)
3. Visit `https://agent-of-you.github.io/strands-dashboard/`
4. Enter your agent repo and PAT in settings

---

## Security Model

The agent has multiple layers of security:

```
Layer 1: User Authorization
  └─ AUTHORIZED_USERS secret — only listed users can trigger
  
Layer 2: Self-Trigger Protection
  └─ Agent account blocked from triggering itself (except workflow_dispatch)
  
Layer 3: Owner Allowlist (Application-level)
  └─ github_guardrails.py — blocks all repos outside ALLOWED_OWNERS
  
Layer 4: Node ID Resolution
  └─ Opaque GitHub node IDs are resolved to verify target repos
  
Layer 5: Activity Throttling
  └─ Max 50 external mutations per 24h (configurable via STRANDS_THROTTLE_LIMIT)
  
Layer 6: Token Separation
  └─ GITHUB_TOKEN for own repos, PAT_TOKEN for upstream (prevents recursive triggers)
```

### Key Security Decisions

| Decision | Rationale |
|----------|-----------|
| Private repo | System prompt, secrets, and agent strategies are not public |
| PAT (Classic) over Fine-grained | Needs `notifications` scope for cross-repo mentions |
| OIDC over static keys | Short-lived credentials, no secrets to rotate |
| Application-level guardrails | Even if PAT has broad access, agent is constrained at code level |
| Strict mutation mode | Mutations with unresolvable node IDs are blocked, not allowed |

---

## Infrastructure Reference

### Complete Environment Variables at Runtime

These are all the environment variables available during an agent run:

```
# Core (set by agent.yml workflow)
GITHUB_TOKEN          → PAT_TOKEN (set in env block)
PAT_TOKEN             → Agent's GitHub PAT
GITHUB_CONTEXT        → Full GitHub event JSON (set by action.yml)
STRANDS_PROMPT        → The task prompt

# Model Configuration (from repo variables)
STRANDS_PROVIDER      → bedrock | anthropic | openai
STRANDS_MODEL_ID      → Model identifier
STRANDS_MAX_TOKENS    → Max output tokens
STRANDS_ADDITIONAL_REQUEST_FIELDS → Extra model params JSON

# Tools
STRANDS_TOOLS         → Tool config string (pkg:tool1,tool2;pkg2:tool3)
STRANDS_TOOLS_DIRECTORY → Load tools from directory (true/false)

# AWS (set by OIDC step in action.yml)
AWS_ACCESS_KEY_ID     → Temporary (from OIDC)
AWS_SECRET_ACCESS_KEY → Temporary (from OIDC)
AWS_SESSION_TOKEN     → Temporary (from OIDC)
AWS_REGION            → e.g., us-west-2
AWS_DEFAULT_REGION    → Same as AWS_REGION

# Memory & Sessions
STRANDS_KNOWLEDGE_BASE_ID → Bedrock KB ID
S3_SESSION_BUCKET         → S3 bucket for sessions
S3_SESSION_PREFIX         → S3 key prefix

# Project Tracking
STRANDS_CODER_PROJECT_ID → GitHub Project V2 node ID

# MCP Servers
MCP_SERVERS           → JSON config for MCP servers

# Observability
LANGFUSE_BASE_URL     → Langfuse endpoint
LANGFUSE_PUBLIC_KEY   → Langfuse public key
LANGFUSE_SECRET_KEY   → Langfuse secret key
OTEL_*                → OpenTelemetry config (when enable_otel=true)

# Slack
SLACK_BOT_TOKEN       → Slack bot token
SLACK_APP_TOKEN       → Slack app-level token

# Other API Keys (optional, for non-Bedrock providers)
ANTHROPIC_API_KEY     → Direct Anthropic API
OPENAI_API_KEY        → OpenAI API
PERPLEXITY_API_KEY    → Perplexity search
```

### Files That Need User Customization

| File | What to Change | Why |
|------|----------------|-----|
| `SYSTEM_PROMPT.md` | Username, repos, push policy | Agent identity |
| `strands_coder/tools/github_guardrails.py` | `ALLOWED_OWNERS` | Security boundary |
| `strands_coder/activity.py` | `_INTERNAL_OWNERS` | Throttle scoping |
| `.github/workflows/agent.yml` | `git_user_name`, `git_user_email`, `AGENT_ACCOUNT` | Git identity |
| `.github/workflows/mentions.yml` | `@agent-of-mkmeral` string | Mention detection |

### Cost Estimates

| Component | Approximate Cost | Notes |
|-----------|-----------------|-------|
| GitHub Actions | Free (2,000 min/month private) | Each agent run ~2-10 min |
| AWS Bedrock (Claude Sonnet) | ~$3/1M input, ~$15/1M output | ~$0.05-0.50 per agent run |
| Bedrock KB | ~$0.35/1000 queries | For memory retrieval |
| S3 | Negligible | Session files are small |
| Langfuse | Free tier available | Observability |

---

## Troubleshooting

### Agent doesn't respond to issues

1. Check `AUTHORIZED_USERS` secret includes the issue author
2. Verify `PAT_TOKEN` is valid and not expired
3. Check Actions tab for failed/skipped runs
4. Ensure workflows are enabled (Settings → Actions → General)

### Agent can't access Bedrock

1. Verify `AWS_ROLE_ARN` secret is correct
2. Check Bedrock model access in AWS Console
3. Ensure OIDC provider exists: `aws iam list-open-id-connect-providers`
4. Verify IAM role trust policy includes the repo

### Agent is blocked from a repo

1. Check `ALLOWED_OWNERS` in `github_guardrails.py`
2. Or set `STRANDS_ALLOWED_OWNERS` variable
3. Ensure the PAT has access to the target repo

### Mentions don't work

1. Uncomment the `schedule:` in `mentions.yml`
2. Ensure the PAT has `notifications` scope
3. Check the agent is @mentioned (not backtick formatted)
4. Verify the mentioning user is in `AUTHORIZED_USERS`

### Knowledge Base errors

1. Verify `STRANDS_KNOWLEDGE_BASE_ID` is correct
2. Ensure IAM role has `bedrock-agent:*` and `bedrock-agent-runtime:*`
3. Check KB exists in the same region as the agent

---

## Support

- **Issues:** Open an issue in your agent's repo
- **Template updates:** Pull from `agent-of-mkmeral/strands-coder-private`
- **Strands SDK docs:** https://strandsagents.com
- **Strands SDK repo:** https://github.com/strands-agents/sdk-python
