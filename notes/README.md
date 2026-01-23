# TFA Notes & Documentation

Internal documentation for the Test Failure Analyzer.

## Documentation Index

| Document | Purpose |
|----------|---------|
| [PROJECT_ARCHITECTURE.md](PROJECT_ARCHITECTURE.md) | Legacy architecture overview |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Commands cheatsheet |
| [TEAM_PRESENTATION.md](TEAM_PRESENTATION.md) | System overview for presentations |

## Additional Docs

See the `/docs` folder for comprehensive documentation:

| Document | Purpose |
|----------|---------|
| [DEVELOPER_GUIDE.md](../docs/DEVELOPER_GUIDE.md) | Architecture, code structure, how to contribute |
| [CONTRIBUTING.md](../docs/CONTRIBUTING.md) | Contribution guidelines |
| [API.md](../docs/API.md) | REST API reference |

---

## Quick Start

```bash
# 1. Configure environment
export RP_URL="https://reportportal.example.com"
export RP_USERNAME="your-username"
export RP_PASSWORD="your-password"
export RP_PROJECT="your-project"

# 2. Test connection
python main.py list-launches -n 5

# 3. Analyze failures (preview)
python main.py analyze -l <LAUNCH_ID> -c <COMPONENT> --dry-run

# 4. Analyze and push to RP
python main.py analyze -l <LAUNCH_ID> -c <COMPONENT> --push

# 5. Deep investigation with verification
python main.py investigate -l <LAUNCH_ID> -c <COMPONENT> --verify --push
```

---

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point |
| `config.yaml` | Application configuration |
| `knowledge_base.yaml` | Component-specific rules and patterns |
| `.env` | Environment variables (credentials) |
| `ui/` | React web UI (optional) |

---

## Architecture Summary

```
┌──────────────────────────────────────────────────────────────┐
│                      CLI / API / UI                          │
├──────────────────────────────────────────────────────────────┤
│                      Use Cases                               │
│           (AnalyzeFailure, InvestigateRCA)                   │
├──────────────────────────────────────────────────────────────┤
│                       Domain                                 │
│   Entities: Failure, Classification, RCA, Evidence           │
│   Services: ClassificationService, InvestigationService      │
│   Interfaces: LLMProvider, CacheRepo, CodeFetcher, Notifier  │
├──────────────────────────────────────────────────────────────┤
│                    Infrastructure                            │
│   LLM: Claude, Groq, Ollama                                  │
│   Cache: Redis, Memory                                       │
│   Code: GitHub, Local fetcher + AST parser                   │
│   Notifications: Slack, Teams                                │
│   Repositories: ReportPortal                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Features

- **AI Classification**: Claude, Groq, Ollama with Thinker-Critic pattern
- **90%+ Accuracy**: Structured log parsing + few-shot examples
- **Test Code Analysis**: AST-based flakiness detection
- **GitHub Integration**: Links to test source in RCA comments
- **Test Verification**: Re-run tests to confirm intermittent failures
- **Team Notifications**: Slack/Teams alerts
- **Shared Caching**: Redis for team collaboration

---

**Version**: 2.1 | **Last Updated**: January 2026
