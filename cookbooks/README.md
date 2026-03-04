# 📚 Strands Agents Cookbooks

Welcome to the Strands Agents educational cookbooks! These Jupyter notebooks will teach you how to build AI agents from basics to production-ready systems.

## 🎯 Learning Path

| # | Cookbook | Topics | Time | Level |
|---|----------|--------|------|-------|
| 1 | [Getting Started](01_getting_started.ipynb) | Installation, first agent, tools, **model providers** (Bedrock, OpenAI, Anthropic, Ollama), streaming | 30 min | Beginner |
| 2 | [Custom Tools](02_custom_tools.ipynb) | `@tool` decorator, **ToolContext**, invocation state, class-based tools, async tools, streaming from tools | 45 min | Intermediate |
| 3 | [Conversations & Multi-Agent](03_conversations_and_multiagent.ipynb) | Multi-turn chat, conversation managers, agent state, **agents as tools**, **Swarm**, **Graph**, debate patterns | 60 min | Intermediate |
| 4 | [Production Patterns](04_production_patterns.ipynb) | Session management, **AgentCore Memory**, **Hooks**, **Structured Output** (Pydantic), **AWS Lambda** deployment | 60 min | Advanced |

## 🚀 Quick Start

### Option 1: Run in Google Colab
Click the links above and open in Colab - no setup required!

### Option 2: Run Locally

```bash
# Clone the repo
git clone https://github.com/agent-of-mkmeral/strands-coder.git
cd strands-coder

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install jupyter strands-agents strands-agents-tools

# Launch Jupyter
jupyter notebook cookbooks/
```

## 📋 Prerequisites

- **Python 3.10+**
- **AWS Account** (for Amazon Bedrock - default model provider)
- OR **OpenAI/Anthropic API key** (alternative providers)
- OR **Ollama** (for local models)

### AWS Setup (for Bedrock)
```bash
# Configure AWS credentials
aws configure
# OR set environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-west-2"
```

## 📖 Key Concepts by Cookbook

### Cookbook 1: Getting Started
- Basic agent creation
- Using built-in tools (calculator, current_time)
- **Model providers**: Bedrock, Anthropic, OpenAI, Ollama
- Streaming responses

### Cookbook 2: Custom Tools ⭐
- `@tool` decorator with type hints and docstrings
- **ToolContext** - accessing agent state and session info
- **Invocation state** - passing user IDs, auth tokens without prompts
- Class-based tools for shared resources
- Async tools and streaming progress

### Cookbook 3: Conversations & Multi-Agent
- Multi-turn conversation context
- Conversation managers (sliding window, summarizing)
- Agent state management
- **Agents as tools** pattern
- **Swarm** - agents that hand off to each other
- **Graph** - explicit workflows with routing
- Debate pattern - multiple perspectives

### Cookbook 4: Production Patterns ⭐
- **Session Management** - FileSessionManager, S3SessionManager
- **AgentCore Memory** - AWS-based long-term memory with semantic retrieval
- **Hooks** - logging, rate limiting, argument override
- **Structured Output** - type-safe Pydantic responses
- **AWS Lambda deployment** - official layers, CDK patterns

## 🔗 Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/latest/)
- [SDK Repository](https://github.com/strands-agents/sdk-python)
- [Tools Package](https://github.com/strands-agents/tools)
- [Examples](https://github.com/strands-agents/docs/tree/main/docs/examples)

## 💡 Tips

1. **Start with Cookbook 1** if you're new to Strands
2. **Focus on ToolContext** in Cookbook 2 - it's essential for production tools
3. **Production apps** should use Cookbook 4 patterns (hooks, structured output)
4. **Multi-agent systems** are covered in Cookbook 3 - try the debate pattern!

Happy building! 🚀
