#!/bin/bash

# Setup AWS OIDC for GitHub Actions
# This script creates the OIDC identity provider and IAM role for GitHub Actions
#
# Usage:
#   ./setup-aws-oidc.sh [OPTIONS]
#
# Options:
#   --repository REPO    GitHub repository in format 'owner/repo' (REQUIRED)
#   --role-name NAME     IAM role name to create (default: StrandsActionRole)
#   --region REGION      AWS region to use (default: us-west-2)
#   --policy-name NAME   IAM policy name to create (default: StrandsActionPolicy)
#   --enable-observability  Enable AgentCore observability permissions (X-Ray, CloudWatch, AgentCore)
#   --agent-id NAME      Agent ID for observability log group naming (default: strands-coder)
#   --help               Show this help message
#
# Examples:
#   ./setup-aws-oidc.sh --repository myorg/myrepo                              # Minimal setup
#   ./setup-aws-oidc.sh --repository myorg/myrepo --enable-observability       # With AgentCore observability
#   ./setup-aws-oidc.sh --repository myorg/myrepo --enable-observability --agent-id my-agent
#   ./setup-aws-oidc.sh --repository myorg/myrepo --role-name MyRole           # Custom role name
#   ./setup-aws-oidc.sh --repository myorg/myrepo --region us-east-1           # Custom region
#
# Prerequisites:
#   - AWS CLI installed and configured with appropriate permissions
#   - IAM permissions to create roles, policies, and OIDC providers
#
# What this script does:
#   1. Creates GitHub OIDC Identity Provider (if not exists)
#   2. Creates IAM role with repository-specific trust policy
#   3. Creates IAM policy with Bedrock, S3, and optionally observability permissions
#   4. Attaches policy to role
#   5. (Optional) Enables CloudWatch Transaction Search for X-Ray traces
#   6. (Optional) Creates CloudWatch log group with AgentCore naming convention
#   7. Outputs role ARN for GitHub repository configuration

set -e

# Default values
GITHUB_REPO=""  # Required - no default
ROLE_NAME="StrandsActionRole"
AWS_REGION="${AWS_REGION:-us-west-2}"
POLICY_NAME="StrandsActionPolicy"
ENABLE_OBSERVABILITY=false
AGENT_ID="strands-coder"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --repository)
            GITHUB_REPO="$2"
            shift 2
            ;;
        --role-name)
            ROLE_NAME="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --policy-name)
            POLICY_NAME="$2"
            shift 2
            ;;
        --enable-observability)
            ENABLE_OBSERVABILITY=true
            shift
            ;;
        --agent-id)
            AGENT_ID="$2"
            shift 2
            ;;
        --help)
            echo "Setup AWS OIDC for GitHub Actions"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --repository REPO          GitHub repository in format 'owner/repo' (REQUIRED)"
            echo "  --role-name NAME           IAM role name to create (default: $ROLE_NAME)"
            echo "  --region REGION            AWS region to use (default: $AWS_REGION)"
            echo "  --policy-name NAME         IAM policy name to create (default: $POLICY_NAME)"
            echo "  --enable-observability     Enable AgentCore observability (X-Ray, CloudWatch, AgentCore)"
            echo "  --agent-id NAME            Agent ID for log group naming (default: $AGENT_ID)"
            echo "  --help                     Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --repository myorg/myrepo                              # Minimal setup"
            echo "  $0 --repository myorg/myrepo --enable-observability       # With observability"
            echo "  $0 --repository myorg/myrepo --enable-observability --agent-id my-agent"
            echo "  $0 --repository myorg/myrepo --role-name MyRole           # Custom role"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$GITHUB_REPO" ]]; then
    echo "❌ Error: --repository is required"
    echo "Usage: $0 --repository owner/repo [OPTIONS]"
    echo "Use --help for more information"
    exit 1
fi

# Derive the log group name from agent-id using AgentCore naming convention
OTEL_LOG_GROUP="/aws/bedrock-agentcore/runtimes/${AGENT_ID}"

echo "🚀 Setting up AWS OIDC for GitHub Actions..."
echo "Repository: $GITHUB_REPO"
echo "Region: $AWS_REGION"
echo "Observability: $ENABLE_OBSERVABILITY"
if [ "$ENABLE_OBSERVABILITY" = true ]; then
    echo "Agent ID: $AGENT_ID"
    echo "Log group: $OTEL_LOG_GROUP"
fi

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Step 1: Create OIDC Identity Provider
echo "📝 Step 1: Creating OIDC Identity Provider..."

# Check if OIDC provider already exists
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com" &>/dev/null; then
    echo "✅ OIDC Identity Provider already exists"
else
    echo "Creating OIDC Identity Provider..."
    aws iam create-open-id-connect-provider \
        --url https://token.actions.githubusercontent.com \
        --client-id-list sts.amazonaws.com \
        --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
        --thumbprint-list 1c58a3a8518e8759bf075b76b750d4f2df264fcd

    echo "✅ OIDC Identity Provider created successfully"
fi

# Step 2: Create Trust Policy for the Role
echo "📝 Step 2: Creating trust policy..."

cat > trust-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "GitHubOIDC",
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:${GITHUB_REPO}:*"
                },
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                }
            }
        },
        {
            "Sid": "SelfAssume",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"
            },
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {
                    "aws:RequestedRegion": "${AWS_REGION}"
                }
            }
        }
    ]
}
EOF

# Step 3: Create IAM Role
echo "📝 Step 3: Creating IAM Role..."

if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    echo "⚠️  Role $ROLE_NAME already exists, updating trust policy..."
    aws iam update-assume-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-document file://trust-policy.json
else
    echo "Creating IAM Role..."
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file://trust-policy.json \
        --description "Role for GitHub Actions OIDC authentication"
fi

# Step 4: Create and attach permissions policy
echo "📝 Step 4: Creating permissions policy..."

# Build the policy based on whether observability is enabled
if [ "$ENABLE_OBSERVABILITY" = true ]; then
    echo "  📊 Including AgentCore observability permissions..."
    cat > permissions-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock:*",
                "bedrock-runtime:*",
                "bedrock-agent:*",
                "bedrock-agent-runtime:*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "AgentCoreAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:*",
                "bedrock-agentcore-control:*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "XRayAccess",
            "Effect": "Allow",
            "Action": [
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
                "xray:GetSamplingRules",
                "xray:GetSamplingTargets",
                "xray:GetSamplingStatisticSummaries"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CloudWatchObservability",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams",
                "logs:StartQuery",
                "logs:GetQueryResults",
                "logs:StopQuery",
                "cloudwatch:PutMetricData"
            ],
            "Resource": "*"
        },
        {
            "Sid": "S3Access",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            "Resource": "*"
        },
        {
            "Sid": "STSAccess",
            "Effect": "Allow",
            "Action": [
                "sts:GetCallerIdentity",
                "sts:AssumeRole"
            ],
            "Resource": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"
        }
    ]
}
EOF
else
    cat > permissions-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:*",
                "bedrock-runtime:*",
                "bedrock-agent:*",
                "bedrock-agent-runtime:*",
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket",
                "sts:GetCallerIdentity"
            ],
            "Resource": "*"
        }
    ]
}
EOF
fi

# Create or update the policy
if aws iam get-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/$POLICY_NAME" &>/dev/null; then
    echo "⚠️  Policy $POLICY_NAME already exists, updating..."
    aws iam create-policy-version \
        --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/$POLICY_NAME" \
        --policy-document file://permissions-policy.json \
        --set-as-default
else
    echo "Creating permissions policy..."
    aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --policy-document file://permissions-policy.json \
        --description "Permissions for GitHub Actions to access AWS services"
fi

# Attach policy to role
echo "📝 Step 5: Attaching policy to role..."
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/$POLICY_NAME"

# Step 6: Enable CloudWatch Transaction Search and create log group (observability only)
if [ "$ENABLE_OBSERVABILITY" = true ]; then
    echo "📝 Step 6: Enabling CloudWatch Transaction Search..."
    
    # Create resource policy for X-Ray → CloudWatch Logs
    echo "  Creating CloudWatch Logs resource policy for X-Ray..."
    aws logs put-resource-policy \
        --policy-name "TransactionSearchXRayAccess" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Sid\": \"TransactionSearchXRayAccess\",
                \"Effect\": \"Allow\",
                \"Principal\": { \"Service\": \"xray.amazonaws.com\" },
                \"Action\": \"logs:PutLogEvents\",
                \"Resource\": [
                    \"arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:aws/spans:*\",
                    \"arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/application-signals/data:*\"
                ],
                \"Condition\": {
                    \"ArnLike\": { \"aws:SourceArn\": \"arn:aws:xray:${AWS_REGION}:${AWS_ACCOUNT_ID}:*\" },
                    \"StringEquals\": { \"aws:SourceAccount\": \"${AWS_ACCOUNT_ID}\" }
                }
            }]
        }" 2>/dev/null && echo "  ✅ Resource policy created" || echo "  ⚠️  Resource policy may already exist (non-fatal)"
    
    # Update X-Ray trace segment destination to CloudWatch Logs
    echo "  Setting X-Ray trace destination to CloudWatch Logs..."
    aws xray update-trace-segment-destination \
        --destination CloudWatchLogs \
        --region "$AWS_REGION" 2>/dev/null && echo "  ✅ Trace destination set" || echo "  ⚠️  Could not set trace destination (you may need to enable via console)"
    
    # Create the log group for agent traces using AgentCore naming convention
    echo "  Creating CloudWatch log group ${OTEL_LOG_GROUP}..."
    aws logs create-log-group \
        --log-group-name "${OTEL_LOG_GROUP}" \
        --region "$AWS_REGION" 2>/dev/null && echo "  ✅ Log group created" || echo "  ⚠️  Log group may already exist (non-fatal)"
fi

# Cleanup temporary files
rm -f trust-policy.json permissions-policy.json

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Add this role ARN to your GitHub repository secrets:"
echo "   Secret name: AWS_ROLE_ARN"
echo "   Secret value: $ROLE_ARN"
echo ""
echo "2. Remove the following secrets from your GitHub repository:"
echo "   - AWS_ACCESS_KEY_ID"
echo "   - AWS_SECRET_ACCESS_KEY"
echo "   - AWS_SESSION_TOKEN"
echo ""

if [ "$ENABLE_OBSERVABILITY" = true ]; then
    echo "📊 AgentCore Observability Setup:"
    echo ""
    echo "3. Set the following repository variable:"
    echo "   Variable name: STRANDS_OTEL_ENABLED"
    echo "   Variable value: true"
    echo ""
    echo "4. Add 'enable_otel' input to your agent.yml workflow:"
    echo "   enable_otel: \${{ vars.STRANDS_OTEL_ENABLED || 'false' }}"
    echo ""
    echo "   How it works:"
    echo "   - The aws-opentelemetry-distro (>=0.10.1) auto-instruments your agent"
    echo "   - Traces are sent directly via OTLP (no ADOT Collector sidecar needed)"
    echo "   - Log group: ${OTEL_LOG_GROUP}"
    echo "   - Metric namespace: bedrock-agentcore"
    echo "   - View traces: CloudWatch → GenAI Observability (region: $AWS_REGION)"
    echo ""
    echo "   Environment variables set by action.yml:"
    echo "   AGENT_OBSERVABILITY_ENABLED=true"
    echo "   OTEL_PYTHON_DISTRO=aws_distro"
    echo "   OTEL_PYTHON_CONFIGURATOR=aws_configurator"
    echo "   OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf"
    echo "   OTEL_TRACES_EXPORTER=otlp"
    echo "   OTEL_RESOURCE_ATTRIBUTES=service.name=${AGENT_ID},aws.log.group.names=${OTEL_LOG_GROUP}"
    echo "   OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-log-group=${OTEL_LOG_GROUP},x-aws-log-stream=runtime-logs,x-aws-metric-namespace=bedrock-agentcore"
    echo ""
    echo "5. (Optional) Enable Transaction Search in the CloudWatch console:"
    echo "   - CloudWatch → Settings → X-Ray traces → Transaction Search → Enable"
    echo "   - Select 'For X-Ray users' and set the sampling percentage"
    echo ""
fi

echo "Role ARN: $ROLE_ARN"
