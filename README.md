# Test Failure Analyzer (TFA)

AI-powered test failure analysis for RHOAI/ODH ReportPortal launches with intelligent classification, verification, and KServe-aware root cause analysis.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

## Overview

TFA automates the classification of test failures from ReportPortal using a hybrid approach:

- **Fast Path**: Rule-based pattern matching for known failure signatures (no LLM cost)
- **Deep Path**: LLM-powered Thinker-Critic-Refiner analysis with evidence gathering, must-gather parsing, and confidence calibration
- **Verification**: Re-runs tests via `uv run pytest` on a live cluster and uses results to confirm or adjust classifications

### Key Features

| Feature | Description |
|---------|-------------|
| **AI Classification** | Claude CLI, Anthropic, Groq, Ollama with Thinker-Critic-Refiner pattern |
| **KServe/RHOAI Awareness** | Deep knowledge of InferenceService, LLMInferenceService, ServingRuntime, LeaderWorkerSet resource chains |
| **Code Analysis** | AST-based test parsing extracts timeout values, wait patterns, retry decorators, parametrize args |
| **Code Fetcher** | GitHub or local repo (opendatahub-tests) for test source context |
| **ReportPortal Sync** | Fetches failures, nested step logs, defect types, linked JIRA tickets; posts results back |
| **Test Verification** | Re-runs failing tests via `uv run pytest` with `--collect-must-gather` on a live cluster |
| **Must-Gather Analysis** | Parses OpenShift must-gather artifacts — extracts CR status conditions, pod failures, events |
| **Confidence Calibration** | Weighted evidence scoring with context-aware verification adjustments |
| **Few-Shot Learning** | Stores past failure embeddings for similarity-based classification hints |
| **Failure Clustering** | Groups similar failures by error signature, detects systemic issues |
| **Timeout Analysis** | Context-dependent: generous timeout + healthy cluster = Product Bug, not Test Automation Issue |
| **Shared Caching** | Redis or in-memory cache for team collaboration |
| **Notifications** | Slack/Teams alerts for analysis results |

## Quick Start

### Installation

```bash
git clone https://github.com/opendatahub-io/TFAAnalyzer.git
cd TFAAnalyzer

# Install with uv (recommended)
uv sync

# Or with pip
pip install -r requirements.txt
```

### Configuration

```bash
# Required — ReportPortal credentials
export RP_URL="https://reportportal.example.com"
export RP_USERNAME="your-username"
export RP_PASSWORD="your-password"
export RP_PROJECT="your-project"

# Optional — LLM providers (only needed if not using claude-cli)
export ANTHROPIC_API_KEY="sk-..."
export GROQ_API_KEY="gsk_..."

# Optional — for private test repos
export GITHUB_TOKEN="ghp_..."
```

### Basic Usage

```bash
# Fast classification (rule-based, no LLM cost)
python main.py analyze -l 10748 -c "Model Server"

# Deep LLM investigation (Thinker-Critic-Refiner pattern)
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli

# Deep + verify (re-runs tests on live cluster) + push results to RP
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli --verify --push

# Deep + RP history analysis for flakiness patterns
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli --analyze-history

# Deep + pre-collected must-gather cluster diagnostics
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli \
  --must-gather-path /path/to/must-gather-collected
```

### ODH/RHOAI Verification Setup

For `--verify` to re-run tests against a live cluster via [opendatahub-tests](https://github.com/opendatahub-io/opendatahub-tests):

1. Clone the test repo and point `config.yaml` to it:

```yaml
# config.yaml
test_repo:
  enabled: true
  repo: "opendatahub-io/opendatahub-tests"
  branch: "main"
  test_dir: "tests"
  local_path: "/path/to/your/opendatahub-tests"

verification:
  timeout_per_test: 0          # 0 = let the test's own timeout handle it
  collect_must_gather: true    # pass --collect-must-gather to pytest
```

2. Log in to the cluster with a **cluster-admin** token (required for session fixtures that read DataScienceCluster CRs):

```bash
oc login --token=sha256~YOUR_TOKEN --server=https://api.your-cluster.com:6443
```

3. Export CI/S3/Jira environment variables (see [.env.ods.example](.env.ods.example)):

```bash
source .env.ods   # or export manually
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli --verify
```

### Must-Gather Analysis

TFA parses [OpenShift must-gather](https://github.com/red-hat-data-services/must-gather) artifacts to extract CR status conditions, pod failures, and events. This helps distinguish product bugs from infrastructure issues.

The must-gather analyzer checks status conditions on KServe/RHOAI CRs including: `InferenceService`, `LLMInferenceService`, `ServingRuntime`, `ClusterServingRuntime`, `LeaderWorkerSet`, `Revision`, `DataSciencePipelinesApplication`, `RayCluster`, and more.

**Option 1: Pass must-gather path directly**

```bash
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli \
  --must-gather-path /path/to/must-gather-collected
```

**Option 2: Enable in config for automatic per-test mapping**

```yaml
# config.yaml
must_gather:
  enabled: true
  base_path: "/path/to/opendatahub-tests/must-gather-collected"
  max_log_lines: 50
  auto_detect: true
```

When `auto_detect` is enabled, TFA maps each failing test name to its per-test must-gather directory. Both raw directories and zip archives (`mg-*.zip`) are supported.

**Option 3: Automatic collection during verification (recommended)**

When `--verify` is used with `collect_must_gather: true` in config, pytest runs with `--collect-must-gather`. TFA then:

1. Extracts the must-gather path from the pytest output
2. Creates an ad-hoc `MustGatherAnalyzer` for the live cluster state
3. Parses CR conditions, pod failures, operator status, and events
4. Feeds the specific findings into the LLM evidence prompt for causal tracing

This means the root cause will cite the actual pods, CRs, and operator conditions that caused the failure — not just "degraded cluster."

## Architecture

TFA follows Clean Architecture with SOLID principles:

```
src/
├── domain/              # Core business logic
│   ├── entities/        # Failure, Classification, RCA, Evidence
│   ├── interfaces/      # Repository, LLM, Notifier, CodeFetcher
│   └── services/        # Classification, Investigation, Verification, EnhancedAnalysis
├── application/         # Use cases
│   └── use_cases/       # AnalyzeFailure, InvestigateRCA
├── infrastructure/      # External integrations
│   ├── llm/             # Claude CLI, Anthropic, Groq, Ollama adapters
│   ├── cache/           # Redis, Memory cache
│   ├── code_fetcher/    # GitHub, Local code fetchers + AST test parser
│   ├── reportportal/    # RP client, component fetcher, test history
│   ├── k8s/             # Must-gather parser + analyzer
│   ├── embeddings/      # Text embedder, failure embedding store
│   ├── notifications/   # Slack, Teams notifiers
│   └── repositories/    # ReportPortal repository
├── api/                 # FastAPI server
│   ├── routes/          # /analyze, /investigate, /health, /feedback, /logs
│   ├── schemas/         # Pydantic request/response models
│   └── middleware/      # Error handling
├── prompts/             # LLM prompt templates
│   ├── investigation/   # Thinker, Critic, Refiner, Evidence prompts
│   ├── system/          # Compact system prompt
│   └── context/         # RHOAI knowledge base prompt
└── utils/               # Config, logging, metrics, knowledge base loader
```

## Commands Reference

### `analyze` — Failure Analysis

Single command for both fast and deep analysis.

```bash
python main.py analyze -l LAUNCH_ID -c COMPONENT [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-l, --launch-id` | ReportPortal launch ID or full URL **(required)** |
| `-c, --component` | Component name to analyze **(required)** |
| `-d, --deep` | Enable deep LLM analysis (Thinker-Critic-Refiner pattern) |
| `--provider` | LLM provider: `claude-cli` (default), `anthropic`, `groq`, `ollama` |
| `--push` | Post results to ReportPortal |
| `--dry-run` | Preview without pushing to RP |
| `-j, --json` | Output as JSON |
| `-s, --server URL` | Use centralized TFA server |
| `--no-cache` | Skip cache and force fresh analysis |
| `--no-llm` | Use only rule-based classification (fast path only) |
| `--verify` | Re-run tests via `uv run pytest` to verify failures (requires `--deep`) |
| `--analyze-history` | Analyze RP history for flakiness patterns (requires `--deep`) |
| `--must-gather-path` | Path to pre-collected must-gather artifacts (requires `--deep`) |
| `-p, --project` | ReportPortal project (or set `RP_PROJECT` env var) |
| `--config` | Path to config file |

**Examples:**

```bash
# Fast classification — rule-based, no LLM cost
python main.py analyze -l 10748 -c "Model Server"

# Deep analysis with Claude CLI
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli

# Deep + verify + push results to RP
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli --verify --push

# Deep + must-gather + history analysis
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli \
  --analyze-history --must-gather-path /path/to/must-gather-collected

# Use centralized TFA server
python main.py analyze -l 10748 -c "Model Server" --server http://tfa:8000 --push
```

### `investigate` — Alias for `analyze --deep`

Kept for backward compatibility. All `analyze --deep` options are available.

```bash
python main.py investigate -l 10748 -c "Model Server" --provider claude-cli --verify
```

### `serve` — API Server

Start centralized TFA server for team collaboration.

```bash
python main.py serve [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-h, --host` | Host to bind (default: `0.0.0.0`) |
| `-p, --port` | Port (default: `8000`) |
| `-w, --workers` | Worker processes (default: `1`) |
| `--reload` | Enable auto-reload for development |

```bash
python main.py serve --port 8000
# Access API docs at http://localhost:8000/docs
```

### Information & Analytics

```bash
# List recent launches from ReportPortal
python main.py list-launches -n 20

# View component failure logs
python main.py component-logs -l 10748 -c "Model Server"

# Test pass/fail history
python main.py test-history -l 10748 -c "Model Server"

# Analytics
python main.py stats --days 30
python main.py dashboard -d 30
python main.py health --days 7
python main.py digest --days 7
python main.py trends
python main.py accuracy-report
```

### Utilities

```bash
# Parse logs (standalone)
python main.py parse-logs --file failure.log

# Manage custom classification patterns
python main.py learn --add

# Record feedback for accuracy tuning
python main.py record-feedback --id <RP_ITEM_ID> --correct "Product Bug"
python main.py feedback
```

## Classification Categories

| Category | Icon | Description | When to Use |
|----------|------|-------------|-------------|
| Product Bug | `PB` | Defect in RHOAI/ODH/KServe component | CR reconciliation failure, missing CRD, service consistently fails despite healthy cluster |
| Test Automation Issue | `AB` | Problem in test code | Short timeout, bad assertion, fixture issue |
| Infrastructure Issue | `SI` | Environment/cluster problems | CrashLoopBackOff, OOMKilled, S3 credentials, Knative/Istio misconfiguration |
| Intermittent Failure | `SI` | Flaky/timing-related | Passes on retry, race condition, inconsistent history |
| To Investigate | `TI` | Needs manual review | Insufficient evidence for definitive classification |

## Configuration

### config.yaml

Copy from `config.example.yaml`:

```yaml
reportportal:
  verify_ssl: false
  # url, project, username, password set via env vars

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  max_tokens: 4096
  temperature: 0.1

analysis:
  max_concurrent_requests: 5
  chunk_size: 150000
  confidence_threshold: 0.7
  include_recommendation: true

test_repo:
  enabled: true
  repo: "opendatahub-io/opendatahub-tests"
  branch: "main"
  test_dir: "tests"
  local_path: "/path/to/opendatahub-tests"

verification:
  timeout_per_test: 0              # 0 = let the test's own timeout handle it (up to 1800s)
  collect_must_gather: true        # pass --collect-must-gather to pytest
  skip_on_low_confidence: true
  confidence_threshold: 0.9

must_gather:
  enabled: true
  base_path: "/path/to/opendatahub-tests/must-gather-collected"
  max_log_lines: 50
  auto_detect: true

notifications:
  enabled: false
  # slack_webhook: ""    # or set SLACK_WEBHOOK_URL env var
  # teams_webhook: ""    # or set TEAMS_WEBHOOK_URL env var

cache:
  enabled: true
  backend: memory        # or 'redis'
  # redis_url: redis://localhost:6379
  ttl_seconds: 86400

logging:
  level: INFO
  format: console
```

## LLM Providers

| Provider | Setup | Cost | Speed |
|----------|-------|------|-------|
| `claude-cli` | Install [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) | Free (uses your Claude plan) | Fast |
| `anthropic` | `export ANTHROPIC_API_KEY=sk-...` | ~$0.003/analysis | Fast |
| `groq` | `export GROQ_API_KEY=gsk_...` | Free (rate limited) | Fastest |
| `ollama` | Run [Ollama](https://ollama.ai) locally | Free | Depends on GPU |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /health` | GET | Health check |
| `GET /` | GET | API info |
| `POST /api/v1/analyze` | POST | Quick classification |
| `POST /api/v1/investigate` | POST | Deep RCA investigation (supports `must_gather_path`) |
| `POST /api/v1/feedback` | POST | Record feedback |
| `GET /api/v1/feedback/metrics` | GET | Accuracy metrics |
| `GET /api/v1/logs/stream` | GET | Stream logs (SSE) |
| `GET /api/v1/logs/recent` | GET | Recent logs |
| `GET /docs` | GET | Swagger UI |

## Team Deployment

### Docker Compose

```bash
docker-compose up -d
# TFA API on port 8000, Redis on 6379
python main.py analyze -l 10748 -c "Model Server" --server http://localhost:8000 --push
```

### Makefile

```bash
make install      # Install dependencies
make test         # Run tests
make run-api      # Start API server
make lint         # Ruff + mypy
make format       # Black + isort
```

## Development

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=html
ruff check src/
mypy src/
```

## Documentation

- [Quick Reference](notes/QUICK_REFERENCE.md) — Command cheatsheet
- [Architecture](notes/PROJECT_ARCHITECTURE.md) — Clean architecture overview and analysis pipeline
- [Developer Guide](docs/DEVELOPER_GUIDE.md) — Project structure, extending, and testing guide
- [API Reference](docs/API.md) — REST API endpoints and examples
- [Contributing](docs/CONTRIBUTING.md) — Contribution guidelines
- [knowledge_base.yaml](knowledge_base.yaml) — Domain-specific classification rules and RHOAI component context
- [.env.ods.example](.env.ods.example) — ODH/RHOAI environment variable template for `--verify`

## License

Apache 2.0 — See [LICENSE](LICENSE) for details.
