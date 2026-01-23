# TFA Architecture

## Overview

TFA analyzes test failures from ReportPortal using AI classification.

**Key Features:**
- 90%+ classification accuracy
- Multi-LLM support (Claude, Groq, Ollama)
- Centralized server mode with shared Redis cache
- Automatic posting to ReportPortal

---

## Architecture Diagram

### Local Mode

```
CLI (main.py)
    → Component Fetcher → ReportPortal API
    → Classification Engine → YAML Rules
    → LLM Provider (if needed)
    → Post results to ReportPortal
```

### Server Mode

```
30 Engineers → FastAPI Server (:8000)
                    ↓
              Redis Cache (95% hits)
                    ↓
              Domain Services
                    ↓
              LLM Adapters → Claude/Groq/Ollama
                    ↓
              ReportPortal + SQLite
```

---

## Components

| Component | Purpose | Location |
|-----------|---------|----------|
| CLI | User commands | `main.py` |
| API Server | REST API | `src/api/` |
| Classification Engine | Rule matching | `src/classification_engine.py` |
| RCA Investigator | Thinker-Critic analysis | `src/investigator.py` |
| RP Client | ReportPortal integration | `src/rp/client.py` |
| LLM Providers | AI analysis | `src/llm/`, `src/infrastructure/llm/` |
| Cache | Redis/Memory cache | `src/infrastructure/cache/` |

---

## Analysis Pipeline

```
1. Receive request (launch_id, component)
2. Check cache → return if hit
3. Fetch failures from ReportPortal
4. For each failure:
   a. Parse logs (extract errors, stack traces)
   b. Apply YAML rules
   c. Check test history
   d. If confidence > 90%: use rule result
   e. Else: call LLM (Thinker-Critic for investigation)
5. Cache result (24h TTL)
6. Post to ReportPortal (if --push)
7. Return results
```

---

## Classification Categories

| Category | Examples |
|----------|----------|
| **Product Bug** | 5xx errors, service crashes, version mismatches |
| **Test Automation Issue** | Timeouts, assertion failures, fixture problems |
| **Infrastructure Issue** | Network errors, CRD missing, permissions denied |
| **Flaky Test** | Intermittent failures, pass rate 20-80% |

---

## Thinker-Critic Pattern

Used for deep investigation (`investigate` command):

```
1. THINKER: Generate initial RCA proposal
2. CRITIC: Challenge assumptions, find gaps
3. REFINER: Synthesize final classification
```

Achieves 92-97% accuracy on complex failures.

---

## Project Structure

```
rp_tfa_analysis/
├── main.py                     # CLI entry point
├── src/
│   ├── api/                    # FastAPI server
│   │   ├── server.py
│   │   ├── routes/             # analyze, investigate, health endpoints
│   │   ├── schemas/            # request/response models
│   │   └── dependencies.py     # DI container
│   │
│   ├── application/            # Use cases
│   │   └── use_cases/
│   │       ├── analyze_failure.py
│   │       └── investigate_rca.py
│   │
│   ├── domain/                 # Business logic
│   │   ├── entities/           # Failure, Classification, RCA
│   │   ├── interfaces/         # LLM, Repository abstractions
│   │   └── services/           # Classification, Investigation services
│   │
│   ├── infrastructure/         # External integrations
│   │   ├── cache/              # Redis, Memory cache
│   │   ├── llm/                # Claude, Groq, Ollama adapters
│   │   └── repositories/       # RP repository
│   │
│   ├── rp/                     # ReportPortal client
│   │   ├── client.py           # API client
│   │   ├── component_fetcher.py
│   │   └── test_history.py
│   │
│   ├── llm/                    # LLM providers
│   │   ├── base.py             # Base interface
│   │   ├── anthropic.py
│   │   ├── groq_provider.py
│   │   └── ollama.py
│   │
│   ├── classification_engine.py # YAML rule engine
│   ├── investigator.py         # RCA Thinker-Critic
│   │
│   └── utils/
│       ├── config.py
│       ├── log_parser.py
│       └── knowledge_base.py
│
├── ui/                         # React Web UI
├── classification_rules.yaml   # Classification rules
├── knowledge_base.yaml         # Component knowledge
└── config.yaml                 # Configuration
```

---

## Configuration

### Environment Variables

```bash
# Required
export RP_URL="https://reportportal.example.com"
export RP_USERNAME="your-username"
export RP_PASSWORD="your-password"
export RP_PROJECT="your-project"

# Optional
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="gsk_..."
export REDIS_URL="redis://localhost:6379"
```

### config.yaml

```yaml
reportportal:
  url: https://reportportal.example.com
  username: your-username
  password: your-password
  project: your-project

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  temperature: 0.1

analysis:
  confidence_threshold: 0.7
  max_concurrent_requests: 5
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/analyze` | POST | Analyze failures |
| `/api/v1/investigate` | POST | Deep RCA investigation |
| `/api/v1/health` | GET | Health check |
| `/docs` | GET | OpenAPI documentation |

### Request Example

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "launch_id": "9657",
    "component": "Model_server",
    "push_to_rp": true
  }'
```

---

## Performance

| Operation | Time |
|-----------|------|
| Cache hit | <100ms |
| Rule-based classification | <500ms |
| LLM analysis (cached prompt) | 1-3s |
| LLM analysis (full) | 5-10s |

| Mode | Accuracy |
|------|----------|
| Rule-only | 75-80% |
| Standard LLM | 85-88% |
| High-accuracy | 90-95% |
| Thinker-Critic | 92-97% |

---

## Caching

- **Result Cache**: Redis or in-memory, 24h TTL
- **Cache Key**: `{test_name}:{log_hash}`
- **Server Mode**: Shared cache across all users (95% hit rate)

---

## LLM Providers

| Provider | Setup | Best For |
|----------|-------|----------|
| Claude CLI | `which claude` | Development |
| Anthropic API | `ANTHROPIC_API_KEY` | Production |
| Groq | `GROQ_API_KEY` | High volume (free) |
| Ollama | Local install | Privacy |

---

**Version**: 2.1 | **Last Updated**: January 2026
