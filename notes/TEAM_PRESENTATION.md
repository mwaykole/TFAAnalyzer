# TFA System Overview

## What is TFA?

TFA (Test Failure Analyzer) is an AI-powered tool that:

1. Fetches test failures from ReportPortal
2. Analyzes logs using AI (Claude, Groq, Ollama)
3. Fetches test source code for deeper analysis
4. Classifies failures into categories
5. Verifies intermittent failures by re-running tests
6. Posts results back to ReportPortal
7. Sends notifications to Slack/Teams
8. Tracks trends and component health

---

## System Architecture

### Centralized Server Mode

```
30 QE Engineers → TFA API Server (:8000) → Redis Cache (95% hit rate)
                        ↓
              Classification Service
                        ↓
              LLM Providers (Claude/Groq/Ollama)
                        ↓
              ReportPortal (results posted)
```

### Component Flow

```
CLI/API Request
    → Check Redis Cache
    → If miss: Fetch from ReportPortal
    → Parse logs + match patterns
    → If confidence < 90%: Call LLM
    → Store result in cache
    → Post to ReportPortal
```

---

## Classification Categories

| Category | When Used | RP Defect Type |
|----------|-----------|----------------|
| **Product Bug** | Real defect in RHOAI/ODH | PB (pb001) |
| **Test Automation Issue** | Problem in test code | AB (ab001) |
| **Infrastructure Issue** | Cluster/env problem | SI (si001) |
| **Flaky Test** | Intermittent failure | AB (ab_1kbn5su3gqpdt) |

---

## Thinker-Critic Pattern

For complex failures, TFA uses a 3-step LLM analysis:

```
1. THINKER: Propose initial RCA
2. CRITIC: Challenge the analysis
3. REFINER: Synthesize final result
```

This achieves 92-97% accuracy on complex failures.

---

## Commands

### Local Mode

```bash
python main.py analyze -l 9657 -c Model_server --push
python main.py investigate -l 9657 -c Model_server --push
```

### Server Mode

```bash
# Start server
python main.py serve --port 8000

# Use from any machine
python main.py analyze -l 9657 -c Model_server --server http://tfa:8000 --push
```

### API Usage

```bash
curl -X POST http://tfa:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"launch_id": "9657", "component": "Model_server", "push_to_rp": true}'
```

---

## Performance

| Metric | Value |
|--------|-------|
| Cache Hit Rate | 95% |
| Classification Accuracy | 90%+ |
| Response Time (cached) | <1s |
| Response Time (LLM) | 3-10s |
| Cost per Analysis | ~$0.005 |

---

## New Features (v2.1)

### Test Code Analysis

TFA can fetch test source code and detect flakiness patterns:

```
Test Code → AST Parser → Detects:
  - time.sleep() calls
  - Timeout decorators
  - Wait patterns
  - Retry decorators
  - Fixtures used
```

Results include GitHub links to test source:

```markdown
**Test Source:** [tests/test_model.py#L45](https://github.com/...)
```

### Verification Mode

Verify intermittent failures by re-running tests:

```bash
# Re-run tests to verify
python main.py investigate -l 9657 -c Model_server --verify

# Or analyze RP history
python main.py investigate -l 9657 -c Model_server --analyze-history
```

### Notifications

Get Slack/Teams alerts for analysis results:

```bash
# Set webhook in .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# Results automatically notify team
python main.py investigate -l 9657 -c Model_server --push
```

---

## Project Structure

```
src/
├── api/              # FastAPI REST API
├── application/      # Use cases (Analyze, Investigate)
├── domain/           # Business logic, entities, interfaces
│   ├── entities/     # Failure, Classification, RCA, Evidence
│   ├── interfaces/   # LLM, Cache, CodeFetcher, Notifier
│   └── services/     # Classification, Investigation, Verification
├── infrastructure/   # External integrations
│   ├── llm/          # Claude, Groq, Ollama adapters
│   ├── cache/        # Redis, Memory cache
│   ├── code_fetcher/ # GitHub, Local fetchers + TestParser
│   └── notifications/# Slack, Teams notifiers
├── rp/               # ReportPortal client
└── utils/            # Config, logging, metrics
```

---

## Quick Start

```bash
# Set environment
export RP_URL="https://reportportal.example.com"
export RP_USERNAME="your-username"
export RP_PASSWORD="your-password"
export RP_PROJECT="your-project"

# Test connection
python main.py list-launches -n 5

# Analyze failures
python main.py analyze -l <LAUNCH_ID> -c <COMPONENT> --dry-run
python main.py analyze -l <LAUNCH_ID> -c <COMPONENT> --push
```

---

**Version**: 2.1 | **Last Updated**: January 2026
