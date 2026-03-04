# 📚 Strands Agents Cookbooks for Students

Welcome to the Strands Agents SDK educational cookbooks! These Jupyter notebooks are designed to help students learn how to build AI agents from scratch.

## 🎯 Learning Path

The cookbooks are designed to be completed in order:

| Cookbook | Topics | Time |
|----------|--------|------|
| [01. Getting Started](01_getting_started.ipynb) | Installation, first agent, tools basics | 30 min |
| [02. Custom Tools](02_custom_tools.ipynb) | `@tool` decorator, type hints, docstrings | 45 min |
| [03. Model Providers](03_model_providers.ipynb) | Bedrock, OpenAI, Anthropic, Ollama | 30 min |
| [04. Conversations & Memory](04_conversations_and_memory.ipynb) | Multi-turn chat, session management | 45 min |
| [05. Multi-Agent Systems](05_multi_agent_systems.ipynb) | Agent coordination, pipelines, debates | 60 min |

## 🚀 Quick Start

### Option 1: Local Setup

```bash
# Clone the repository
git clone https://github.com/agent-of-mkmeral/strands-coder.git
cd strands-coder/cookbooks

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install strands-agents strands-agents-tools jupyter

# Start Jupyter
jupyter notebook
```

### Option 2: Google Colab

Open any notebook directly in Google Colab by:
1. Going to [colab.research.google.com](https://colab.research.google.com)
2. File → Open notebook → GitHub tab
3. Enter the repository URL and select a notebook

## 📋 Prerequisites

- **Python 3.10+**
- **Basic Python knowledge** (variables, functions, classes)
- **API Key** (one of the following):
  - AWS credentials for Amazon Bedrock (default)
  - OpenAI API key
  - Anthropic API key
  - Or use Ollama for free local models

## 🔧 Model Provider Setup

### Amazon Bedrock (Default)
```bash
# Configure AWS CLI
aws configure
# Or set environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-west-2"
```

### OpenAI
```bash
export OPENAI_API_KEY="sk-..."
```

### Anthropic
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Ollama (Free, Local)
```bash
# Install Ollama from https://ollama.ai
# Pull a model
ollama pull llama3.2
```

## 📖 What You'll Learn

By completing all cookbooks, you'll be able to:

✅ Create AI agents with the Strands SDK  
✅ Build custom tools using Python decorators  
✅ Use different AI model providers  
✅ Manage conversations and memory  
✅ Build multi-agent systems  
✅ Apply common agent design patterns

## 🎓 For Instructors

These notebooks are designed for:
- **Classroom instruction**: Each notebook is ~30-60 min
- **Self-paced learning**: Students can work through independently
- **Workshops**: Can be combined for half-day or full-day workshops

Each notebook includes:
- Clear explanations with emojis for visual appeal
- Code examples that run out-of-the-box
- Exercises for hands-on practice
- Summary sections for review
- Links to official documentation

## 📚 Additional Resources

- [Strands Documentation](https://strandsagents.com/)
- [SDK Python GitHub](https://github.com/strands-agents/sdk-python)
- [Tools GitHub](https://github.com/strands-agents/tools)
- [Strands Samples](https://github.com/strands-agents/samples)

## 🤝 Contributing

Found an issue or want to improve a cookbook? Feel free to:
1. Open an issue describing the problem
2. Submit a pull request with improvements

## 📄 License

Apache 2.0 - See LICENSE file for details.
