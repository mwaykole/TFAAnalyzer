# Test Failure Analyzer (TFA)

AI-powered test failure analysis for ReportPortal with intelligent classification, verification, and team collaboration features.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-113%20passed-brightgreen.svg)](tests/)

## Overview

TFA automates the classification of test failures from ReportPortal using a hybrid approach:

- **Fast Path**: Rule-based pattern matching for known failure signatures (no LLM cost)
- **Smart Path**: LLM-powered Thinker-Critic analysis for complex failures
- **Verification**: Re-runs tests or analyzes history to confirm intermittent failures

### Key Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI Classification** | Claude, Groq, Ollama support with Thinker-Critic pattern |
| 🎯 **90%+ Accuracy** | Structured log parsing + few-shot examples |
| ⚡ **Auto Flakiness Detection** | AST-based test code analysis finds sleep/wait patterns |
| 🔗 **GitHub Integration** | Links to test source code in RCA comments |
| 📊 **ReportPortal Sync** | Posts analysis results and defect types to RP |
| 💾 **Shared Caching** | Redis-backed cache for team collaboration |
| 🔔 **Notifications** | Slack/Teams alerts for analysis results |
| 🔄 **Test Verification** | Re-runs tests to confirm intermittent failures |
| 📈 **Metrics & Analytics** | Track LLM costs, cache efficiency, accuracy |

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/rp-tfa-analysis.git
cd rp-tfa-analysis

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your ReportPortal credentials
```

### Configuration

```bash
# Required environment variables
export RP_URL="https://reportportal.example.com"
export RP_USERNAME="your-username"
export RP_PASSWORD="your-password"
export RP_PROJECT="your-project"

# Optional - for different LLM providers
export ANTHROPIC_API_KEY="sk-..."
export GROQ_API_KEY="gsk_..."
export GITHUB_TOKEN="ghp_..."  # For private test repos
export SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
```

### Basic Usage

```bash
# Analyze failures in a launch
python main.py analyze -l 9722 -c Model_server

# Deep investigation with LLM
python main.py investigate -l 9722 -c Model_server --provider claude-cli

# With verification (re-runs tests)
python main.py investigate -l 9722 -c Model_server --verify --push

# Push results to ReportPortal
python main.py investigate -l 9722 -c Model_server --push
```

## Architecture

TFA follows Clean Architecture with SOLID principles:

```
src/
├── domain/           # Core business logic
│   ├── entities/     # Failure, Classification, RCA, Evidence
│   ├── interfaces/   # Repository, LLM, Notifier abstractions
│   └── services/     # ClassificationService, InvestigationService
├── application/      # Use cases
│   └── use_cases/    # AnalyzeFailure, InvestigateRCA
├── infrastructure/   # External integrations
│   ├── llm/          # Claude, Groq, Ollama adapters
│   ├── cache/        # Redis, Memory cache
│   ├── code_fetcher/ # GitHub, Local code fetchers
│   ├── notifications/# Slack, Teams notifiers
│   └── repositories/ # ReportPortal repository
├── api/              # FastAPI server
│   ├── routes/       # /analyze, /investigate, /health
│   ├── schemas/      # Pydantic request/response models
│   └── middleware/   # Error handling, logging
└── utils/            # Config, logging, metrics
```

## Commands Reference

### `analyze` - Quick Classification

Fast rule-based analysis with optional LLM fallback.

```bash
python main.py analyze -l LAUNCH_ID -c COMPONENT [OPTIONS]

Options:
  --push           Post results to ReportPortal
  --dry-run        Preview without posting
  --json           Output as JSON
  --server URL     Use centralized TFA server
```

### `investigate` - Deep RCA

Full Thinker-Critic LLM analysis with verification.

```bash
python main.py investigate -l LAUNCH_ID -c COMPONENT [OPTIONS]

Options:
  --provider       LLM: claude-cli, anthropic, groq, ollama
  --verify         Re-run tests to verify failures
  --analyze-history  Analyze RP history for flakiness
  --push           Post results to ReportPortal
  --json           Output as JSON
```

### `serve` - API Server

Start centralized TFA server for team collaboration.

```bash
python main.py serve [OPTIONS]

Options:
  --host           Host to bind (default: 0.0.0.0)
  --port           Port (default: 8000)
  --workers        Worker processes (default: 1)
  --reload         Enable auto-reload

# Access API docs at http://localhost:8000/docs
```

### Other Commands

```bash
# List recent launches
python main.py list-launches -n 20

# View component failures
python main.py component-logs -l 9722 -c Model_server

# Test history analysis
python main.py test-history -l 9722 -c Model_server

# Analytics dashboard
python main.py dashboard -d 30

# Weekly digest
python main.py digest --days 7
```

## Classification Categories

| Category | Icon | Description | RP Defect Type |
|----------|------|-------------|----------------|
| Product Bug | 🐛 | Defect in product code | PB |
| Test Automation Issue | 🔧 | Problem in test code | AB |
| Infrastructure Issue | 🏗️ | Environment/cluster problems | SI |
| Intermittent Failure | ⚡ | Flaky/timing-related | SI |
| To Investigate | ❓ | Needs manual review | TI |

## Configuration

### config.yaml

```yaml
reportportal:
  url: ""  # Or set RP_URL env var
  project: ""  # Or set RP_PROJECT env var
  verify_ssl: false

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  temperature: 0.1

# Test code fetching for better analysis
test_repo:
  enabled: true
  repo: "opendatahub-io/opendatahub-tests"
  branch: "main"
  local_path: "/path/to/local/clone"  # Optional, faster than GitHub API

# Verification settings
verification:
  timeout_per_test: 120
  skip_on_low_confidence: true

# Notifications
notifications:
  enabled: false
  slack_webhook: ""  # Or set SLACK_WEBHOOK_URL env var
  teams_webhook: ""  # Or set TEAMS_WEBHOOK_URL env var

# Caching
cache:
  enabled: true
  backend: memory  # or 'redis'
  redis_url: redis://localhost:6379
  ttl_seconds: 86400
```

## LLM Providers

| Provider | Setup | Cost | Speed |
|----------|-------|------|-------|
| `claude-cli` | Install Claude CLI | Free | Fast |
| `anthropic` | `ANTHROPIC_API_KEY` | ~$0.003/analysis | Fast |
| `groq` | `GROQ_API_KEY` | Free (rate limited) | Fastest |
| `ollama` | Run Ollama locally | Free | Depends on GPU |

### Cost Optimization

```bash
# Use cheaper Haiku model
python main.py investigate -l 9722 -c Model_server --cost-optimize

# Skip LLM for high-confidence pattern matches (default)
python main.py investigate -l 9722 -c Model_server --skip-obvious
```

## Team Deployment

### Docker Compose (Recommended)

```bash
# Start TFA API + Redis
docker-compose up -d

# Use from CLI
python main.py analyze -l 9722 -c Model_server --server http://localhost:8000
```

### Shared Benefits

- **95% Cache Hit Rate**: Avoid duplicate LLM calls across team
- **Consistent Classifications**: Same rules for everyone
- **Centralized Metrics**: Track team-wide accuracy
- **API Access**: Integration with CI/CD pipelines

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/analyze` | POST | Quick classification |
| `/api/v1/investigate` | POST | Deep RCA investigation |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc documentation |

### Example API Request

```bash
curl -X POST http://localhost:8000/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "launch_id": "9722",
    "component": "Model_server",
    "push_to_rp": true,
    "verify_mode": "analyze-history"
  }'
```

## Development

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for detailed development guide.

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Type checking
mypy src/

# Linting
ruff check src/
```

## Documentation

- [Developer Guide](docs/DEVELOPER_GUIDE.md) - Architecture, code structure, contributing
- [Team Presentation](notes/TEAM_PRESENTATION.md) - HLD/LLD diagrams, SOLID principles
- [Quick Reference](notes/QUICK_REFERENCE.md) - Command cheatsheet
- [Knowledge Base](knowledge_base.yaml) - Domain-specific rules and patterns

## Project Status

- ✅ Core classification engine
- ✅ Multiple LLM providers
- ✅ ReportPortal integration
- ✅ Clean architecture refactor
- ✅ Test verification (--verify)
- ✅ Code fetcher for test analysis
- ✅ Slack/Teams notifications
- ✅ FastAPI server mode
- ✅ 113 unit tests passing

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Support

For issues or questions, open an issue in the repository.
