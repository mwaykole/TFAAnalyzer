# Developer Guide

This guide covers the architecture, code structure, and development practices for the Test Failure Analyzer (TFA).

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Core Concepts](#core-concepts)
- [Adding New Features](#adding-new-features)
- [Testing](#testing)
- [Code Style](#code-style)
- [Debugging](#debugging)

## Architecture Overview

TFA follows **Clean Architecture** principles with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                        Presentation                         │
│                    (CLI, API, UI)                           │
├─────────────────────────────────────────────────────────────┤
│                      Application                            │
│                    (Use Cases)                              │
├─────────────────────────────────────────────────────────────┤
│                        Domain                               │
│              (Entities, Services, Interfaces)               │
├─────────────────────────────────────────────────────────────┤
│                    Infrastructure                           │
│         (LLM, Cache, Repositories, Notifications)           │
└─────────────────────────────────────────────────────────────┘
```

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **Single Responsibility** | Each class has one reason to change |
| **Open/Closed** | Add new LLM providers without modifying existing code |
| **Liskov Substitution** | All LLM adapters are interchangeable |
| **Interface Segregation** | Small, focused interfaces (CodeFetcher, Notifier) |
| **Dependency Inversion** | High-level modules depend on abstractions |

## Project Structure

```
src/
├── domain/                    # Core business logic (no external dependencies)
│   ├── entities/              # Business objects
│   │   ├── failure.py         # Failure entity
│   │   ├── classification.py  # Classification, FailureCategory, Severity
│   │   ├── evidence.py        # Evidence collected from logs
│   │   └── rca.py             # Root Cause Analysis result
│   ├── interfaces/            # Abstract interfaces (DIP)
│   │   ├── repositories.py    # FailureRepository, CacheRepository, HistoryRepository
│   │   ├── llm_provider.py    # LLMProvider interface
│   │   ├── code_fetcher.py    # CodeFetcher interface
│   │   ├── notifier.py        # Notifier interface
│   │   └── log_parser.py      # LogParser interface
│   └── services/              # Domain services
│       ├── classification_service.py  # Rule-based classification
│       ├── investigation_service.py   # Thinker-Critic pattern
│       └── verification_service.py    # Test verification
│
├── application/               # Use cases (orchestration)
│   └── use_cases/
│       ├── analyze_failure.py     # Quick analysis flow
│       └── investigate_rca.py     # Deep investigation flow
│
├── infrastructure/            # External integrations
│   ├── llm/                   # LLM adapters
│   │   ├── llm_factory.py     # Factory pattern for providers
│   │   ├── claude_adapter.py  # Claude CLI adapter
│   │   ├── groq_adapter.py    # Groq API adapter
│   │   └── ollama_adapter.py  # Ollama adapter
│   ├── cache/                 # Caching
│   │   ├── redis_cache.py     # Redis implementation
│   │   └── memory_cache.py    # In-memory implementation
│   ├── code_fetcher/          # Test code fetching
│   │   ├── github_adapter.py  # GitHub API fetcher
│   │   ├── local_adapter.py   # Local filesystem fetcher
│   │   └── test_parser.py     # AST-based test parser
│   ├── notifications/         # Team notifications
│   │   ├── slack_notifier.py  # Slack webhook
│   │   └── teams_notifier.py  # Teams webhook
│   └── repositories/          # Data repositories
│       └── rp_repository.py   # ReportPortal adapter
│
├── api/                       # FastAPI server
│   ├── server.py              # App setup and lifespan
│   ├── routes/                # API endpoints
│   │   ├── analyze.py
│   │   ├── investigate.py
│   │   └── health.py
│   ├── schemas/               # Pydantic models
│   │   ├── requests.py
│   │   └── responses.py
│   ├── middleware/            # Middleware
│   │   └── error_handler.py
│   ├── dependencies.py        # Dependency injection
│   └── client.py              # API client for CLI
│
├── rp/                        # ReportPortal client (legacy)
│   ├── client.py              # RP API client
│   ├── component_fetcher.py   # Fetch component failures
│   └── test_history.py        # History fetcher
│
├── investigator.py            # Legacy RCA investigator (still used by CLI)
│
└── utils/                     # Utilities
    ├── config.py              # Configuration management
    ├── logging.py             # Structured logging
    ├── metrics.py             # Analysis metrics
    └── knowledge_base.py      # Domain knowledge
```

## Core Concepts

### Entities

Entities are pure Python dataclasses with no external dependencies:

```python
# src/domain/entities/failure.py
@dataclass
class Failure:
    id: str
    test_name: str
    logs: str
    test_code: str = ""
    
    @property
    def cache_key(self) -> str:
        """Generate cache key from logs hash."""
        return hashlib.md5(self.logs[:500].encode()).hexdigest()[:16]
```

### Interfaces

Interfaces define contracts that infrastructure must implement:

```python
# src/domain/interfaces/llm_provider.py
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate response from LLM."""
        pass
    
    # Default implementations for Thinker-Critic pattern
    async def think(self, evidence: str) -> str:
        prompt = f"Analyze this failure:\n{evidence}"
        response = await self.generate(prompt)
        return response.content
```

### Use Cases

Use cases orchestrate the flow between domain and infrastructure:

```python
# src/application/use_cases/investigate_rca.py
class InvestigateRCAUseCase:
    def __init__(
        self,
        failure_repo: FailureRepository,      # Interface
        llm_provider: LLMProvider,            # Interface
        cache_repo: CacheRepository | None,   # Interface
        code_fetcher: CodeFetcher | None,     # Interface
    ):
        # Dependency Injection via constructor
        self._failure_repo = failure_repo
        self._llm_provider = llm_provider
        ...
```

### Infrastructure Adapters

Adapters implement interfaces for external systems:

```python
# src/infrastructure/llm/groq_adapter.py
class GroqAdapter(LLMProvider):
    def __init__(self, api_key: str, model: str = "llama-3.1-70b-versatile"):
        self._client = Groq(api_key=api_key)
        self._model = model
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        response = await self._client.chat.completions.create(...)
        return LLMResponse(content=response.choices[0].message.content)
```

## Adding New Features

### Adding a New LLM Provider

1. Create adapter in `src/infrastructure/llm/`:

```python
# src/infrastructure/llm/new_provider_adapter.py
from src.domain.interfaces.llm_provider import LLMProvider, LLMResponse

class NewProviderAdapter(LLMProvider):
    def __init__(self, api_key: str, model: str = "default-model"):
        self._api_key = api_key
        self._model = model
    
    @property
    def model_name(self) -> str:
        return self._model
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # Implement API call
        ...
        return LLMResponse(content=response_text)
```

2. Register in factory:

```python
# src/infrastructure/llm/llm_factory.py
from src.infrastructure.llm.new_provider_adapter import NewProviderAdapter

class LLMFactory:
    _providers: dict[str, type[LLMProvider]] = {
        "anthropic": AnthropicAdapter,
        "groq": GroqAdapter,
        "new_provider": NewProviderAdapter,  # Add here
    }
```

3. Export in `__init__.py`:

```python
# src/infrastructure/llm/__init__.py
from src.infrastructure.llm.new_provider_adapter import NewProviderAdapter
__all__ = [..., "NewProviderAdapter"]
```

### Adding a New Notification Channel

1. Create notifier in `src/infrastructure/notifications/`:

```python
# src/infrastructure/notifications/discord_notifier.py
from src.domain.interfaces.notifier import Notifier, AnalysisSummary

class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    @property
    def channel_name(self) -> str:
        return "discord"
    
    async def send_summary(self, summary: AnalysisSummary) -> bool:
        # Implement Discord webhook
        ...
```

2. Add to config:

```python
# src/utils/config.py
class NotificationConfig(BaseSettings):
    discord_webhook: str | None = Field(default=None)
```

3. Wire into CLI/API:

```python
# main.py
if settings.get_discord_webhook():
    from src.infrastructure.notifications.discord_notifier import DiscordNotifier
    notifiers.append(DiscordNotifier(settings.get_discord_webhook()))
```

### Adding New Classification Patterns

Edit `knowledge_base.yaml`:

```yaml
quick_rules:
  - name: "New Error Pattern"
    pattern: "YourSpecificError.*message"
    classification: "Infrastructure Issue"
    severity: "high"
    reason: "Detected specific infrastructure error"
```

Or add to `ClassificationService`:

```python
# src/domain/services/classification_service.py
CLASSIFICATION_PATTERNS = [
    ...
    (r"YourPattern.*here", FailureCategory.INFRASTRUCTURE_ISSUE, 0.90),
]
```

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Specific test file
pytest tests/test_domain_entities.py -v

# Specific test class
pytest tests/test_domain_services.py::TestClassificationService -v
```

### Test Structure

```
tests/
├── test_domain_entities.py    # Entity tests
├── test_domain_services.py    # Service tests
├── test_infrastructure.py     # Adapter tests
├── test_api.py                # API endpoint tests
└── test_metrics.py            # Metrics tests
```

### Writing Tests

```python
# tests/test_domain_services.py
import pytest
from src.domain.services.classification_service import ClassificationService
from src.domain.entities.classification import FailureCategory

class TestClassificationService:
    def test_classify_infrastructure_issue(self):
        service = ClassificationService()
        result = service.classify("CrashLoopBackOff detected")
        
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE
        assert result.confidence >= 0.9
    
    @pytest.mark.parametrize("logs,expected", [
        ("OOMKilled", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("AssertionError", FailureCategory.TEST_AUTOMATION_ISSUE),
    ])
    def test_pattern_classification(self, logs, expected):
        service = ClassificationService()
        result = service.classify(logs)
        assert result.category == expected
```

### Mocking External Services

```python
import pytest
from unittest.mock import AsyncMock, patch

class TestInvestigateUseCase:
    @pytest.mark.asyncio
    async def test_investigate_with_mock_llm(self):
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = LLMResponse(
            content="CLASSIFICATION: Product Bug\nCONFIDENCE: 85"
        )
        
        use_case = InvestigateRCAUseCase(
            failure_repo=mock_failure_repo,
            llm_provider=mock_llm,
        )
        
        result = await use_case.execute(request)
        assert result[0].rca.category == FailureCategory.PRODUCT_BUG
```

## Code Style

### Formatting

```bash
# Format with ruff
ruff format src/ tests/

# Lint with ruff
ruff check src/ tests/
```

### Type Hints

All code should use type hints:

```python
def classify(
    self,
    logs: str,
    evidence: Evidence | None = None,
) -> Classification:
    """Classify failure based on logs.
    
    Args:
        logs: Raw log content
        evidence: Optional evidence from analysis
        
    Returns:
        Classification with category and confidence
    """
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def process_failure(
    failure: Failure,
    options: dict[str, Any],
) -> RCA:
    """Process a test failure and generate RCA.
    
    Args:
        failure: The failure to process
        options: Processing options including:
            - deep_analysis: Run LLM analysis
            - verify: Re-run test
            
    Returns:
        RCA with classification and root cause
        
    Raises:
        ValueError: If failure has no logs
    """
    ...
```

## Debugging

### Enable Verbose Logging

```bash
# CLI
python main.py investigate -l 9722 -c Model_server -v

# Or set environment variable
export LOG_LEVEL=DEBUG
python main.py investigate ...
```

### Check API Logs

```bash
# Start server with debug
python main.py serve --reload

# Watch logs
tail -f logs/tfa.log
```

### Debugging LLM Prompts

```python
# Add in InvestigationService
logger.debug("llm_prompt", prompt=prompt[:500])
logger.debug("llm_response", response=response[:500])
```

### Testing Code Fetcher

```python
# Quick test
python -c "
import asyncio
from src.infrastructure.code_fetcher.local_adapter import LocalCodeFetcher
from pathlib import Path

async def test():
    fetcher = LocalCodeFetcher(Path('/path/to/tests'))
    code = await fetcher.fetch_test_code('test_my_function')
    print(code.source_code[:500])
    print(f'Flaky: {code.is_potentially_flaky}')

asyncio.run(test())
"
```

## Common Issues

### Import Errors

If you get circular import errors, use deferred imports:

```python
def my_function():
    from src.some.module import SomeClass  # Import inside function
    ...
```

### Async Context Issues

Always use `async with` for repositories:

```python
async with rp_repo:
    results = await use_case.execute(request)
```

### Cache Misses

Check cache key generation:

```python
# Ensure consistent cache keys
cache_key = f"investigation:{failure.cache_key}"
logger.debug("cache_lookup", key=cache_key)
```

## Getting Help

- Check existing tests for examples
- Read the domain interfaces for contracts
- Look at `notes/TEAM_PRESENTATION.md` for architecture diagrams
- Ask in the team Slack channel
