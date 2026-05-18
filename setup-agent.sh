#!/bin/bash
# =============================================================================
# setup-agent.sh — Create a personal autonomous GitHub agent
# =============================================================================
#
# This script creates a new GitHub agent account (like `agent-of-mkmeral`)
# for any user, sets up a private repository with all required workflows,
# secrets, variables, AWS infrastructure, and optional integrations.
#
# Usage:
#   ./setup-agent.sh --user <github-username> [OPTIONS]
#
# Examples:
#   # Minimal setup (Bedrock only)
#   ./setup-agent.sh --user johndoe
#
#   # Full setup with observability and Slack
#   ./setup-agent.sh --user johndoe --enable-observability --enable-slack
#
#   # Custom agent account name
#   ./setup-agent.sh --user johndoe --agent-account my-ai-agent
#
#   # Dry run (show what would happen without doing it)
#   ./setup-agent.sh --user johndoe --dry-run
#
# Prerequisites:
#   - GitHub CLI (`gh`) installed and authenticated
#   - AWS CLI installed and configured (for Bedrock/OIDC setup)
#   - jq installed
#   - The template repository (this repo) cloned locally
#
# What this script does:
#   1. Creates a new GitHub account (manual) or validates existing agent account
#   2. Creates a private repository under the agent account
#   3. Copies workflow files, code, skills from this template
#   4. Configures all required secrets and variables
#   5. Runs AWS OIDC setup for Bedrock access
#   6. Optionally sets up Knowledge Base, S3 sessions, Langfuse, Slack
#   7. Creates a GitHub Project for work tracking
#   8. Validates the setup with a test workflow dispatch
#
# =============================================================================

set -euo pipefail

# ===========================================================================
# Color output helpers
# ===========================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}ℹ️  $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
error()   { echo -e "${RED}❌ $*${NC}" >&2; }
step()    { echo -e "\n${CYAN}━━━ Step $1: $2 ━━━${NC}"; }
header()  { echo -e "\n${CYAN}╔══════════════════════════════════════════════════════╗${NC}"; echo -e "${CYAN}║  $*${NC}"; echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"; }

# ===========================================================================
# Defaults
# ===========================================================================
USER_NAME=""
AGENT_ACCOUNT=""
REPO_NAME="strands-coder-private"
AWS_REGION="${AWS_REGION:-us-west-2}"
IAM_ROLE_NAME="StrandsActionRole"
IAM_POLICY_NAME="StrandsActionPolicy"
ENABLE_OBSERVABILITY=false
ENABLE_SLACK=false
ENABLE_LANGFUSE=false
ENABLE_KB=false
ENABLE_S3_SESSIONS=false
S3_SESSION_BUCKET=""
S3_SESSION_PREFIX=""
KB_ID=""
DRY_RUN=false
SKIP_AWS=false
SKIP_REPO=false
PAT_TOKEN=""
AUTHORIZED_USERS=""
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"

# ===========================================================================
# Parse arguments
# ===========================================================================
usage() {
    cat << USAGE
Usage: $0 --user <github-username> [OPTIONS]

Required:
  --user <username>             Your GitHub username (the human operator)

Options:
  --agent-account <name>        Agent GitHub account name (default: agent-of-<user>)
  --repo-name <name>            Repository name (default: strands-coder-private)
  --pat-token <token>           GitHub PAT token for the agent account
  --authorized-users <list>     Comma-separated authorized usernames
  --aws-region <region>         AWS region (default: us-west-2)
  --iam-role-name <name>        IAM role name (default: StrandsActionRole)
  --enable-observability        Enable AWS AgentCore observability (X-Ray, CloudWatch)
  --enable-slack                Enable Slack integration
  --enable-langfuse             Enable Langfuse observability
  --enable-kb                   Enable Bedrock Knowledge Base (memory)
  --kb-id <id>                  Bedrock Knowledge Base ID
  --enable-s3-sessions          Enable S3 session persistence
  --s3-bucket <bucket>          S3 bucket for sessions
  --s3-prefix <prefix>          S3 prefix for sessions
  --skip-aws                    Skip AWS OIDC setup (if already done)
  --skip-repo                   Skip repository creation (if already exists)
  --dry-run                     Show what would happen without doing it
  --help                        Show this help message

Examples:
  # Minimal: just Bedrock + GitHub
  $0 --user johndoe

  # Full setup
  $0 --user johndoe --enable-observability --enable-kb --kb-id ABCDEF1234

  # Existing agent account with custom PAT
  $0 --user johndoe --agent-account my-agent-bot --pat-token ghp_xxx

USAGE
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --user)              USER_NAME="$2"; shift 2 ;;
        --agent-account)     AGENT_ACCOUNT="$2"; shift 2 ;;
        --repo-name)         REPO_NAME="$2"; shift 2 ;;
        --pat-token)         PAT_TOKEN="$2"; shift 2 ;;
        --authorized-users)  AUTHORIZED_USERS="$2"; shift 2 ;;
        --aws-region)        AWS_REGION="$2"; shift 2 ;;
        --iam-role-name)     IAM_ROLE_NAME="$2"; shift 2 ;;
        --enable-observability) ENABLE_OBSERVABILITY=true; shift ;;
        --enable-slack)      ENABLE_SLACK=true; shift ;;
        --enable-langfuse)   ENABLE_LANGFUSE=true; shift ;;
        --enable-kb)         ENABLE_KB=true; shift ;;
        --kb-id)             KB_ID="$2"; ENABLE_KB=true; shift 2 ;;
        --enable-s3-sessions) ENABLE_S3_SESSIONS=true; shift ;;
        --s3-bucket)         S3_SESSION_BUCKET="$2"; ENABLE_S3_SESSIONS=true; shift 2 ;;
        --s3-prefix)         S3_SESSION_PREFIX="$2"; shift 2 ;;
        --skip-aws)          SKIP_AWS=true; shift ;;
        --skip-repo)         SKIP_REPO=true; shift ;;
        --dry-run)           DRY_RUN=true; shift ;;
        --help)              usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
done

# ===========================================================================
# Validate
# ===========================================================================
if [[ -z "$USER_NAME" ]]; then
    error "--user is required"
    usage
fi

[[ -z "$AGENT_ACCOUNT" ]] && AGENT_ACCOUNT="agent-of-${USER_NAME}"
[[ -z "$AUTHORIZED_USERS" ]] && AUTHORIZED_USERS="$USER_NAME"

FULL_REPO="${AGENT_ACCOUNT}/${REPO_NAME}"

# Check prerequisites
for cmd in gh jq; do
    if ! command -v "$cmd" &>/dev/null; then
        error "$cmd is required but not found. Install it first."
        exit 1
    fi
done

if [[ "$SKIP_AWS" == "false" ]]; then
    if ! command -v aws &>/dev/null; then
        error "AWS CLI required for OIDC setup. Install it or use --skip-aws."
        exit 1
    fi
fi

# ===========================================================================
# Summary
# ===========================================================================
header "🤖 Strands Agent Setup"
echo ""
info "Human operator:     ${USER_NAME}"
info "Agent account:      ${AGENT_ACCOUNT}"
info "Repository:         ${FULL_REPO}"
info "AWS region:         ${AWS_REGION}"
info "IAM role:           ${IAM_ROLE_NAME}"
info "Authorized users:   ${AUTHORIZED_USERS}"
info "Observability:      ${ENABLE_OBSERVABILITY}"
info "Slack:              ${ENABLE_SLACK}"
info "Langfuse:           ${ENABLE_LANGFUSE}"
info "Knowledge Base:     ${ENABLE_KB} ${KB_ID:+(ID: $KB_ID)}"
info "S3 Sessions:        ${ENABLE_S3_SESSIONS} ${S3_SESSION_BUCKET:+(Bucket: $S3_SESSION_BUCKET)}"
info "Dry run:            ${DRY_RUN}"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    warn "DRY RUN MODE — no changes will be made"
    echo ""
fi

# Helper: run or show command
run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "  ${YELLOW}[DRY RUN]${NC} $*"
    else
        eval "$@"
    fi
}

# ===========================================================================
# Step 0: Agent Account Setup (Manual)
# ===========================================================================
step "0" "Agent Account Verification"

echo ""
echo "🔑 The agent needs its own GitHub account."
echo ""
echo "If you haven't created one yet:"
echo "  1. Go to https://github.com/join"
echo "  2. Create account: ${AGENT_ACCOUNT}"
echo "  3. Use a separate email (e.g., ${USER_NAME}+agent@gmail.com)"
echo "  4. Create a PAT (Classic) at https://github.com/settings/tokens"
echo "     Required scopes: repo, workflow, read:org, read:user, notifications"
echo "  5. Run this script again with --pat-token <your-pat>"
echo ""

if [[ -z "$PAT_TOKEN" ]]; then
    echo ""
    read -rp "Enter PAT token for ${AGENT_ACCOUNT} (or press Enter to skip): " PAT_TOKEN
    if [[ -z "$PAT_TOKEN" ]]; then
        warn "No PAT token provided. You'll need to set the PAT_TOKEN secret manually."
    fi
fi

# Verify the PAT works
if [[ -n "$PAT_TOKEN" ]]; then
    VERIFIED_USER=$(curl -s -H "Authorization: Bearer ${PAT_TOKEN}" \
        "https://api.github.com/user" | jq -r '.login // empty')
    if [[ -n "$VERIFIED_USER" ]]; then
        success "PAT verified — authenticated as @${VERIFIED_USER}"
        if [[ "${VERIFIED_USER}" != "${AGENT_ACCOUNT}" ]]; then
            warn "PAT belongs to @${VERIFIED_USER}, not @${AGENT_ACCOUNT}"
            warn "This is OK if ${VERIFIED_USER} has access to create repos under ${AGENT_ACCOUNT}"
        fi
    else
        error "PAT verification failed. Check the token and try again."
        [[ "$DRY_RUN" == "false" ]] && exit 1
    fi
fi

# ===========================================================================
# Step 1: Create Repository
# ===========================================================================
step "1" "Create Repository"

if [[ "$SKIP_REPO" == "true" ]]; then
    info "Skipping repository creation (--skip-repo)"
else
    # Check if repo exists
    REPO_EXISTS=$(gh repo view "${FULL_REPO}" --json name 2>/dev/null && echo "yes" || echo "no")
    
    if [[ "$REPO_EXISTS" == "yes" ]]; then
        info "Repository ${FULL_REPO} already exists"
    else
        info "Creating private repository ${FULL_REPO}..."
        run "gh repo create '${FULL_REPO}' --private --description 'Autonomous GitHub Agent powered by Strands Agents' --license apache-2.0"
        success "Repository created"
    fi
fi

# ===========================================================================
# Step 2: Push Template Code
# ===========================================================================
step "2" "Push Template Code"

WORK_DIR=$(mktemp -d)
info "Working directory: ${WORK_DIR}"

if [[ "$DRY_RUN" == "false" ]]; then
    # Clone the new repo (or the existing one)
    if [[ -n "$PAT_TOKEN" ]]; then
        git clone "https://${AGENT_ACCOUNT}:${PAT_TOKEN}@github.com/${FULL_REPO}.git" "${WORK_DIR}/repo" 2>/dev/null || \
        git clone "https://x-access-token:${PAT_TOKEN}@github.com/${FULL_REPO}.git" "${WORK_DIR}/repo" 2>/dev/null || \
        git clone "https://github.com/${FULL_REPO}.git" "${WORK_DIR}/repo"
    else
        git clone "https://github.com/${FULL_REPO}.git" "${WORK_DIR}/repo" 2>/dev/null || true
    fi
    
    if [[ -d "${WORK_DIR}/repo" ]]; then
        cd "${WORK_DIR}/repo"
    else
        mkdir -p "${WORK_DIR}/repo"
        cd "${WORK_DIR}/repo"
        git init
        git remote add origin "https://github.com/${FULL_REPO}.git"
    fi
    
    # Copy template files
    TEMPLATE_FILES=(
        ".github/workflows/agent.yml"
        ".github/workflows/control.yml"
        ".github/workflows/mentions.yml"
        ".github/workflows/auto-release.yml"
        ".github/workflows/creds.yml"
        "strands_coder/"
        "skills/"
        "action.yml"
        "pyproject.toml"
        "setup-aws-oidc.sh"
        "setup-agent.sh"
        "SETUP_GUIDE.md"
        "SYSTEM_PROMPT.md"
        "LICENSE"
        ".gitignore"
    )
    
    for item in "${TEMPLATE_FILES[@]}"; do
        src="${TEMPLATE_DIR}/${item}"
        if [[ -e "$src" ]]; then
            # Create parent directory
            mkdir -p "$(dirname "$item")"
            cp -r "$src" "$item"
        fi
    done
    
    # Customize files for the new user
    # Update SYSTEM_PROMPT.md
    if [[ -f "SYSTEM_PROMPT.md" ]]; then
        # Replace agent account references
        sed -i "s/agent-of-mkmeral/${AGENT_ACCOUNT}/g" SYSTEM_PROMPT.md
        sed -i "s/mkmeral/${USER_NAME}/g" SYSTEM_PROMPT.md
    fi
    
    # Update github_guardrails.py
    if [[ -f "strands_coder/tools/github_guardrails.py" ]]; then
        sed -i "s/\"agent-of-mkmeral\"/\"${AGENT_ACCOUNT}\"/g" strands_coder/tools/github_guardrails.py
        sed -i "s/\"mkmeral\"/\"${USER_NAME}\"/g" strands_coder/tools/github_guardrails.py
    fi
    
    # Update activity.py
    if [[ -f "strands_coder/activity.py" ]]; then
        sed -i "s/\"mkmeral\"/\"${USER_NAME}\"/g" strands_coder/activity.py
    fi
    
    # Update agent.yml
    if [[ -f ".github/workflows/agent.yml" ]]; then
        sed -i "s/agent-of-mkmeral/${AGENT_ACCOUNT}/g" .github/workflows/agent.yml
    fi
    
    # Update mentions.yml
    if [[ -f ".github/workflows/mentions.yml" ]]; then
        sed -i "s/agent-of-mkmeral/${AGENT_ACCOUNT}/g" .github/workflows/mentions.yml
    fi
    
    # Commit and push
    git add -A
    git commit -m "feat: initial agent setup for @${USER_NAME}" --allow-empty || true
    git push origin main 2>/dev/null || git push -u origin main 2>/dev/null || \
        warn "Could not push. You may need to push manually."
    
    success "Template code pushed to ${FULL_REPO}"
else
    info "[DRY RUN] Would copy template files and push to ${FULL_REPO}"
fi

# ===========================================================================
# Step 3: AWS OIDC Setup
# ===========================================================================
step "3" "AWS OIDC Setup"

if [[ "$SKIP_AWS" == "true" ]]; then
    info "Skipping AWS setup (--skip-aws)"
else
    info "Running AWS OIDC setup for ${FULL_REPO}..."
    
    OIDC_ARGS="--repository ${FULL_REPO} --role-name ${IAM_ROLE_NAME} --region ${AWS_REGION}"
    
    if [[ "$ENABLE_OBSERVABILITY" == "true" ]]; then
        OIDC_ARGS="${OIDC_ARGS} --enable-observability --agent-id strands-coder"
    fi
    
    if [[ "$DRY_RUN" == "false" ]]; then
        bash "${TEMPLATE_DIR}/setup-aws-oidc.sh" ${OIDC_ARGS}
        AWS_ROLE_ARN=$(aws iam get-role --role-name "${IAM_ROLE_NAME}" --query Role.Arn --output text 2>/dev/null || echo "")
        if [[ -n "$AWS_ROLE_ARN" ]]; then
            success "AWS OIDC role: ${AWS_ROLE_ARN}"
        fi
    else
        info "[DRY RUN] Would run: setup-aws-oidc.sh ${OIDC_ARGS}"
        AWS_ROLE_ARN="arn:aws:iam::123456789012:role/${IAM_ROLE_NAME}"
    fi
fi

# ===========================================================================
# Step 4: Configure Repository Secrets
# ===========================================================================
step "4" "Configure Repository Secrets"

info "Setting secrets for ${FULL_REPO}..."

set_secret() {
    local name="$1"
    local value="$2"
    local description="$3"
    
    if [[ -z "$value" ]]; then
        warn "Skipping ${name} — no value provided (${description})"
        return
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "  ${YELLOW}[DRY RUN]${NC} gh secret set ${name} -R ${FULL_REPO} (${description})"
    else
        echo "$value" | gh secret set "$name" -R "${FULL_REPO}" --body -
        success "Secret ${name} set (${description})"
    fi
}

set_variable() {
    local name="$1"
    local value="$2"
    local description="$3"
    
    if [[ -z "$value" ]]; then
        warn "Skipping ${name} — no value provided (${description})"
        return
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "  ${YELLOW}[DRY RUN]${NC} gh variable set ${name} -R ${FULL_REPO} (${description})"
    else
        echo "$value" | gh variable set "$name" -R "${FULL_REPO}" --body -
        success "Variable ${name} set (${description})"
    fi
}

# Required secrets
set_secret "PAT_TOKEN" "${PAT_TOKEN}" "Agent's GitHub PAT (repo + workflow + notifications)"
set_secret "AUTHORIZED_USERS" "${AUTHORIZED_USERS}" "Comma-separated authorized usernames"

if [[ -n "$AWS_ROLE_ARN" ]]; then
    set_secret "AWS_ROLE_ARN" "${AWS_ROLE_ARN}" "AWS IAM role for OIDC (Bedrock access)"
fi
set_secret "AWS_REGION" "${AWS_REGION}" "AWS region for Bedrock"

# Required variables
set_variable "STRANDS_PROVIDER" "bedrock" "Model provider"
set_variable "STRANDS_MODEL_ID" "us.anthropic.claude-sonnet-4-5-20250929-v1:0" "Model ID"
set_variable "STRANDS_MAX_TOKENS" "16384" "Max output tokens"
set_variable "AGENT_ACCOUNT" "${AGENT_ACCOUNT}" "Agent's GitHub account name"
set_variable "AGENT_SCHEDULES" '{"jobs":{}}' "Scheduled jobs (empty initially)"

# Optional: Knowledge Base
if [[ "$ENABLE_KB" == "true" ]] && [[ -n "$KB_ID" ]]; then
    set_variable "STRANDS_KNOWLEDGE_BASE_ID" "${KB_ID}" "Bedrock Knowledge Base ID"
fi

# Optional: S3 Sessions
if [[ "$ENABLE_S3_SESSIONS" == "true" ]]; then
    [[ -n "$S3_SESSION_BUCKET" ]] && set_variable "S3_SESSION_BUCKET" "${S3_SESSION_BUCKET}" "S3 bucket for sessions"
    [[ -n "$S3_SESSION_PREFIX" ]] && set_variable "S3_SESSION_PREFIX" "${S3_SESSION_PREFIX}" "S3 prefix for sessions"
fi

# Optional: Observability
if [[ "$ENABLE_OBSERVABILITY" == "true" ]]; then
    set_variable "STRANDS_OTEL_ENABLED" "true" "Enable AgentCore observability"
fi

# Optional: Langfuse (prompt for keys)
if [[ "$ENABLE_LANGFUSE" == "true" ]]; then
    echo ""
    read -rp "Langfuse base URL (e.g., https://cloud.langfuse.com): " LANGFUSE_URL
    read -rp "Langfuse public key: " LANGFUSE_PK
    read -rsp "Langfuse secret key: " LANGFUSE_SK
    echo ""
    
    set_secret "LANGFUSE_BASE_URL" "${LANGFUSE_URL}" "Langfuse endpoint"
    set_secret "LANGFUSE_PUBLIC_KEY" "${LANGFUSE_PK}" "Langfuse public key"
    set_secret "LANGFUSE_SECRET_KEY" "${LANGFUSE_SK}" "Langfuse secret key"
fi

# Optional: Slack (prompt for tokens)
if [[ "$ENABLE_SLACK" == "true" ]]; then
    echo ""
    read -rsp "Slack Bot Token (xoxb-...): " SLACK_BOT
    echo ""
    read -rsp "Slack App Token (xapp-...): " SLACK_APP
    echo ""
    
    set_secret "SLACK_BOT_TOKEN" "${SLACK_BOT}" "Slack bot token"
    set_secret "SLACK_APP_TOKEN" "${SLACK_APP}" "Slack app token"
fi

# ===========================================================================
# Step 5: Customize Guardrails
# ===========================================================================
step "5" "Configure Guardrails"

info "The agent will be restricted to repos owned by:"
info "  - ${AGENT_ACCOUNT} (agent's own repos)"
info "  - ${USER_NAME} (your repos)"
echo ""
read -rp "Additional allowed GitHub orgs/users (comma-separated, or Enter to skip): " EXTRA_OWNERS

if [[ -n "$EXTRA_OWNERS" ]]; then
    set_variable "STRANDS_ALLOWED_OWNERS" "${EXTRA_OWNERS}" "Additional allowed repo owners"
    info "Added to allowed owners: ${EXTRA_OWNERS}"
fi

# ===========================================================================
# Step 6: Create GitHub Project (optional)
# ===========================================================================
step "6" "Create GitHub Project"

echo ""
read -rp "Create a GitHub Project for work tracking? (y/N): " CREATE_PROJECT

if [[ "$CREATE_PROJECT" =~ ^[Yy]$ ]]; then
    if [[ "$DRY_RUN" == "false" ]]; then
        # Create project via GraphQL
        PROJECT_RESULT=$(gh api graphql -f query='
          mutation($ownerId: ID!, $title: String!) {
            createProjectV2(input: {ownerId: $ownerId, title: $title}) {
              projectV2 { id number url }
            }
          }
        ' -f ownerId="$(gh api "users/${AGENT_ACCOUNT}" --jq '.node_id')" \
          -f title="Strands Agent Tracker" 2>/dev/null || echo "{}")
        
        PROJECT_ID=$(echo "$PROJECT_RESULT" | jq -r '.data.createProjectV2.projectV2.id // empty')
        PROJECT_URL=$(echo "$PROJECT_RESULT" | jq -r '.data.createProjectV2.projectV2.url // empty')
        
        if [[ -n "$PROJECT_ID" ]]; then
            set_variable "STRANDS_CODER_PROJECT_ID" "${PROJECT_ID}" "GitHub Project V2 ID"
            success "Project created: ${PROJECT_URL}"
        else
            warn "Could not create project. You can create one manually and set STRANDS_CODER_PROJECT_ID."
        fi
    else
        info "[DRY RUN] Would create GitHub Project V2 'Strands Agent Tracker'"
    fi
else
    info "Skipping project creation"
fi

# ===========================================================================
# Step 7: Validation
# ===========================================================================
step "7" "Validation"

echo ""
info "Running validation checks..."
CHECKS_PASSED=0
CHECKS_TOTAL=0

check() {
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    if eval "$1" 2>/dev/null; then
        success "$2"
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    else
        warn "$2 — FAILED"
    fi
}

if [[ "$DRY_RUN" == "false" ]]; then
    check "gh repo view '${FULL_REPO}' --json name &>/dev/null" "Repository exists"
    check "gh secret list -R '${FULL_REPO}' 2>/dev/null | grep -q PAT_TOKEN" "PAT_TOKEN secret set"
    check "gh secret list -R '${FULL_REPO}' 2>/dev/null | grep -q AUTHORIZED_USERS" "AUTHORIZED_USERS secret set"
    check "gh secret list -R '${FULL_REPO}' 2>/dev/null | grep -q AWS_ROLE_ARN" "AWS_ROLE_ARN secret set"
    check "gh variable list -R '${FULL_REPO}' 2>/dev/null | grep -q STRANDS_PROVIDER" "STRANDS_PROVIDER variable set"
    check "gh variable list -R '${FULL_REPO}' 2>/dev/null | grep -q STRANDS_MODEL_ID" "STRANDS_MODEL_ID variable set"
    
    echo ""
    info "Validation: ${CHECKS_PASSED}/${CHECKS_TOTAL} checks passed"
fi

# ===========================================================================
# Step 8: Test Run (optional)
# ===========================================================================
step "8" "Test Run"

echo ""
read -rp "Trigger a test workflow dispatch? (y/N): " DO_TEST

if [[ "$DO_TEST" =~ ^[Yy]$ ]]; then
    info "Triggering test workflow..."
    run "gh workflow run agent.yml -R '${FULL_REPO}' -f prompt='Hello! I am a new agent. Run a self-diagnostic: check my tools, verify GitHub access, and confirm AWS/Bedrock connectivity.'"
    success "Test workflow dispatched! Check: https://github.com/${FULL_REPO}/actions"
fi

# ===========================================================================
# Summary
# ===========================================================================
header "🎉 Setup Complete!"
echo ""
echo -e "${GREEN}Your autonomous GitHub agent is ready!${NC}"
echo ""
echo "  🤖 Agent account:    @${AGENT_ACCOUNT}"
echo "  📦 Repository:       https://github.com/${FULL_REPO}"
echo "  👤 Authorized users: ${AUTHORIZED_USERS}"
echo "  ☁️  AWS Region:       ${AWS_REGION}"
echo "  🔧 Model:            bedrock / Claude Sonnet"
echo ""
echo "━━━ Next Steps ━━━"
echo ""
echo "  1. Mention @${AGENT_ACCOUNT} in any authorized repo issue/PR"
echo "  2. Or trigger manually: Actions → Agent → Run workflow"
echo "  3. Monitor: https://github.com/${FULL_REPO}/actions"
echo ""
echo "━━━ Optional Enhancements ━━━"
echo ""
echo "  • Set up a dashboard: fork agent-of-mkmeral/strands-dashboard"
echo "  • Create a Bedrock Knowledge Base for agent memory"
echo "  • Add Langfuse for detailed trace observability"
echo "  • Enable Slack integration for chat-based interaction"
echo "  • Add STRANDS_ALLOWED_OWNERS variable for cross-org access"
echo ""

# Cleanup
[[ -d "$WORK_DIR" ]] && rm -rf "$WORK_DIR"

