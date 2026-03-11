# TFA Architecture

## Overview

TFA (Test Failure Analyzer) classifies RHOAI/ODH test failures from ReportPortal using a hybrid approach: fast rule-based pattern matching for known signatures and deep LLM-powered Thinker-Critic-Refiner analysis with must-gather cluster diagnostics.

**Key Features:**
- 90%+ classification accuracy (92-97% with Thinker-Critic)
- Multi-LLM support (Claude CLI, Anthropic, Groq, Ollama)
- Must-gather analysis (CR status conditions, pod failures, events)
- Test verification (re-run on live cluster with must-gather collection)
- Code analysis (AST-based test parsing for flakiness signals)
- Centralized server mode with shared Redis cache

---

## Architecture Diagram

### Local Mode

```
CLI (main.py)
    → Fetch failures from ReportPortal (nested step logs, defect types)
    → Rule-based pattern matching (DEFINITIVE_PATTERNS + knowledge_base.yaml)
    → [--deep] Evidence gathering → LLM Thinker-Critic-Refiner → Post-LLM heuristics
    → [--verify] Re-run test on cluster → collect must-gather → analyze
    → Calibrate confidence → Post results to ReportPortal
```

### Server Mode

```
Engineers → FastAPI Server (:8000)
                 ↓
           Redis Cache (95% hits)
                 ↓
           Domain Services
                 ↓
           LLM Adapters → Claude CLI / Anthropic / Groq / Ollama
                 ↓
           ReportPortal + Notifications (Slack/Teams)
```

---

## Clean Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                         │
│   CLI (Typer + Rich)              REST API (FastAPI)            │
│   python main.py analyze ...      POST /api/v1/analyze          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                           │
│   AnalyzeFailureUseCase          InvestigateRCAUseCase          │
│   (fast path)                    (deep path + verify)           │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        DOMAIN LAYER                              │
│   ClassificationService    InvestigationService                 │
│   VerificationService      EnhancedAnalysis (timeout, cluster)  │
│   Entities: Failure, RCA, Evidence, Classification              │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                           │
│   LLM Providers      Cache            ReportPortal Client       │
│   (Claude CLI/        (Redis/          (fetch logs, nested       │
│    Anthropic/          Memory)          steps, defect types)     │
│    Groq/Ollama)                                                  │
│   Code Fetcher       Must-Gather       Embeddings               │
│   (GitHub/Local       (Parser +         (Few-shot learning       │
│    + AST parser)       Analyzer)         failure store)          │
│   Notifications                                                  │
│   (Slack/Teams)                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
TFAAnalyzer/
├── main.py                          # CLI entry point (Typer + Rich)
├── config.example.yaml              # Configuration template
├── knowledge_base.yaml              # Domain rules, component context, quick rules
├── .env.example                     # General env var template
├── .env.ods.example                 # ODH/RHOAI-specific env vars for --verify
│
├── src/
│   ├── api/                         # FastAPI server
│   │   ├── server.py                # App setup and lifespan
│   │   ├── routes/                  # /analyze, /investigate, /health, /feedback, /logs
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── middleware/              # Error handling
│   │   ├── dependencies.py          # Dependency injection
│   │   └── client.py               # API client for CLI --server mode
│   │
│   ├── application/                 # Use cases (orchestration)
│   │   └── use_cases/
│   │       ├── analyze_failure.py   # Fast-path rule-based classification
│   │       └── investigate_rca.py   # Deep-path: evidence + LLM + verify + must-gather
│   │
│   ├── domain/                      # Core business logic (no external dependencies)
│   │   ├── entities/
│   │   │   ├── failure.py           # Failure entity
│   │   │   ├── classification.py    # Classification, FailureCategory, Severity
│   │   │   ├── evidence.py          # Evidence collected from logs, code, cluster state
│   │   │   └── rca.py              # Root Cause Analysis result
│   │   ├── interfaces/
│   │   │   ├── repositories.py      # FailureRepository, CacheRepository, HistoryRepository
│   │   │   ├── llm_provider.py      # LLMProvider interface
│   │   │   ├── code_fetcher.py      # CodeFetcher interface
│   │   │   ├── notifier.py          # Notifier interface
│   │   │   └── log_parser.py        # LogParser interface
│   │   └── services/
│   │       ├── classification_service.py  # Rule-based patterns + knowledge base matching
│   │       ├── investigation_service.py   # Thinker-Critic-Refiner LLM pattern
│   │       ├── verification_service.py    # Test re-run + history analysis
│   │       └── enhanced_analysis.py       # Timeout analysis, failure clustering, calibration
│   │
│   ├── infrastructure/              # External integrations (adapters)
│   │   ├── llm/                     # LLM provider adapters
│   │   │   ├── llm_factory.py       # Factory pattern for provider selection
│   │   │   ├── claude_adapter.py    # Claude CLI adapter
│   │   │   ├── anthropic_adapter.py # Anthropic API adapter
│   │   │   ├── groq_adapter.py      # Groq API adapter
│   │   │   └── ollama_adapter.py    # Ollama adapter
│   │   ├── cache/                   # Caching
│   │   │   ├── redis_cache.py       # Redis implementation
│   │   │   └── memory_cache.py      # In-memory implementation
│   │   ├── code_fetcher/            # Test code fetching + analysis
│   │   │   ├── github_adapter.py    # GitHub API fetcher
│   │   │   ├── local_adapter.py     # Local filesystem fetcher
│   │   │   └── test_parser.py       # AST-based test parser (timeout, sleep, retry detection)
│   │   ├── reportportal/            # ReportPortal client
│   │   │   ├── client.py            # RP API client (retries, nested step logs)
│   │   │   ├── component_fetcher.py # Fetch component failures from launch
│   │   │   └── models.py            # RP data models
│   │   ├── repositories/
│   │   │   └── rp_repository.py     # FailureRepository + HistoryRepository + launch scan
│   │   ├── k8s/                     # Kubernetes / OpenShift diagnostics
│   │   │   ├── must_gather_parser.py   # Low-level must-gather dir/zip parser
│   │   │   └── must_gather_analyzer.py # High-level analyzer (CR conditions, pod health)
│   │   ├── embeddings/              # Few-shot learning
│   │   │   ├── text_embedder.py     # Text embedding
│   │   │   └── failure_store.py     # Past failure storage for similarity hints
│   │   └── notifications/           # Team notifications
│   │       ├── slack_notifier.py    # Slack webhook
│   │       └── teams_notifier.py    # Teams webhook
│   │
│   ├── prompts/                     # LLM prompt templates (Markdown)
│   │   ├── investigation/           # Thinker, Critic, Refiner, Evidence prompts
│   │   ├── system/                  # System prompts
│   │   └── context/                 # RHOAI/KServe knowledge base prompt
│   │
│   └── utils/                       # Utilities
│       ├── config.py                # Configuration management (pydantic-settings)
│       ├── logging.py               # Structured logging (structlog)
│       ├── metrics.py               # Analysis metrics tracking
│       ├── knowledge_base.py        # Domain knowledge loader + quick rule matcher
│       ├── retry.py                 # Retry logic
│       └── ui.py                    # Rich console output helpers
│
├── tests/
│   ├── test_classification_fixes.py # Classification, deep-mode, hint section tests
│   └── test_must_gather.py          # Must-gather parser + analyzer tests
│
├── docs/
│   ├── API.md                       # REST API reference
│   ├── CONTRIBUTING.md              # Contribution guidelines
│   └── DEVELOPER_GUIDE.md           # Architecture, extending, testing guide
│
└── notes/
    ├── PROJECT_ARCHITECTURE.md      # This file
    ├── QUICK_REFERENCE.md           # Command cheatsheet
    └── TFA_DEMO_PRESENTATION.md     # Team demo slides
```

---

## Analysis Pipeline

### Fast Path (rule-based, no LLM cost)

```
1. Receive request (launch_id, component)
2. Check cache → return if hit
3. Fetch failures from ReportPortal (nested step logs, defect types)
4. For each failure:
   a. Parse logs (extract error type, stack trace, patterns)
   b. Match against DEFINITIVE_PATTERNS (classification_service.py)
   c. Match against knowledge_base.yaml quick_rules
   d. Assign classification + confidence
5. Cache result (24h TTL)
6. Post to ReportPortal (if --push)
```

### Deep Path (LLM-powered, --deep)

```
1. Fetch failures from ReportPortal
2. Launch-wide failure scan (cross-component pattern detection)
3. Group failures by error signature (cluster analysis)
4. For each unique error group (in parallel):
   a. Evidence gathering:
      ├── Test source code (GitHub/local + AST parse)
      ├── Must-gather artifacts (CR conditions, pod failures, events)
      ├── ReportPortal history (pass/fail patterns)
      ├── Rule-based classification (as hints, not gates)
      └── Few-shot similar failures (embedding similarity)
   b. [--verify] Re-run test on cluster
      ├── Collect must-gather on failure
      └── Feed must-gather back into analysis
   c. LLM Thinker-Critic-Refiner chain:
      ├── THINKER: proposes root cause with full evidence
      ├── CRITIC: challenges analysis, checks CR conditions
      └── REFINER: synthesizes final classification
   d. Post-LLM heuristics: timeout reclassification, KServe detection
   e. Confidence calibration: weighted evidence scoring
5. Post to ReportPortal (if --push)
6. Send Slack/Teams notification
```

---

## Classification Categories

| Category | RP Code | When |
|----------|---------|------|
| **Product Bug** | PB | RHOAI/KServe component defect: CR reconciliation, missing CRD, service crash |
| **Test Automation Issue** | AB | Test code problem: short timeout, bad assertion, fixture issue |
| **Infrastructure Issue** | SI | Cluster/env: pod failure, auth, GPU, OOM, storage-initializer |
| **Intermittent Failure** | SI | Flaky: passes on retry, race condition, inconsistent history |

---

## Timeout Classification Logic

TimeoutExpiredError is a SYMPTOM. TFA traces the cause:

| Condition | Classification |
|-----------|---------------|
| Short timeout (< 120s) | Test Automation Issue |
| Generous timeout (>= 300s) + healthy cluster + consistent failure | Product Bug |
| Generous timeout + high pass rate (usually passes) | Infrastructure Issue |
| Generous timeout + degraded cluster (must-gather/launch scan) | Infrastructure Issue |
| Setup-phase timeout + wait_for_condition | Infrastructure Issue |
| Flaky pass rate (20-80%) | Intermittent Failure |

---

## Performance

| Operation | Time |
|-----------|------|
| Cache hit | <100ms |
| Rule-based classification | <500ms |
| LLM Thinker-Critic-Refiner | 5-15s |
| With verification (per test) | 1-30 minutes |

---

*Last Updated: March 2026*
