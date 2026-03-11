# TFA API Reference

The TFA API provides programmatic access to test failure analysis capabilities.

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, the API does not require authentication. Authentication can be added via environment variables in production.

## Endpoints

### Health Check

```
GET /health
```

Returns the health status of the TFA server.

**Response**

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "cache_available": true,
  "rp_configured": true
}
```

### Root

```
GET /
```

Returns API information.

**Response**

```json
{
  "name": "TFA API",
  "version": "2.0.0",
  "docs": "/docs"
}
```

---

### Analyze Failures

```
POST /api/v1/analyze
```

Quick classification using rule-based patterns with optional LLM fallback.

**Request Body**

```json
{
  "launch_id": "9722",
  "component": "Model_server",
  "test_id": null,
  "push_to_rp": false,
  "use_llm": true,
  "provider": "anthropic"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| launch_id | string | Yes | ReportPortal launch ID |
| component | string | Yes | Component to analyze |
| test_id | string | No | Specific test to analyze |
| push_to_rp | boolean | No | Post results to ReportPortal (default: false) |
| use_llm | boolean | No | Use LLM for uncertain cases (default: true) |
| provider | string | No | LLM provider: anthropic, groq, ollama |

**Response**

```json
{
  "launch_id": "9722",
  "component": "Model_server",
  "total_failures": 3,
  "results": [
    {
      "test_name": "test_model_serving_inference",
      "test_id": "12345",
      "classification": {
        "category": "Product Bug",
        "confidence": 0.85,
        "confidence_percent": 85,
        "severity": "HIGH"
      },
      "root_cause": "InferenceService failed to respond",
      "reasoning": "Server returned 500 error...",
      "recommendation": "Check model server logs"
    }
  ],
  "summary": {
    "Product Bug": 2,
    "Infrastructure Issue": 1
  }
}
```

---

### Investigate RCA

```
POST /api/v1/investigate
```

Deep investigation using Thinker-Critic LLM pattern with optional verification.

**Request Body**

```json
{
  "launch_id": "9722",
  "component": "Model_server",
  "test_id": null,
  "push_to_rp": true,
  "provider": "anthropic",
  "verify_mode": "analyze-history"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| launch_id | string | Yes | ReportPortal launch ID |
| component | string | Yes | Component to analyze |
| test_id | string | No | Specific test to analyze |
| push_to_rp | boolean | No | Post results to ReportPortal |
| provider | string | No | LLM provider (default: anthropic) |
| verify_mode | string | No | none, run, analyze-history |
| verify_tests | boolean | No | Legacy: run test verification |
| must_gather_path | string | No | Path to must-gather artifacts for cluster state analysis |

**Verify Modes**

| Mode | Description |
|------|-------------|
| `none` | No verification (default) |
| `run` | Re-run the test using pytest |
| `analyze-history` | Analyze ReportPortal history for patterns |

**Response**

```json
{
  "launch_id": "9722",
  "component": "Model_server",
  "total_failures": 2,
  "results": [
    {
      "test_name": "test_model_serving_inference",
      "test_id": "12345",
      "classification": {
        "category": "Intermittent Failure",
        "confidence": 0.92,
        "confidence_percent": 92,
        "severity": "LOW"
      },
      "root_cause": "Test passed on re-run, confirming flaky behavior",
      "reasoning": "Historical data shows 60% pass rate...",
      "evidence_summary": "Pass rate: 60% | Uses sleep patterns",
      "recommendation": "Add retry decorator",
      "verified": true,
      "verification_result": "passed",
      "verification_details": {
        "mode": "analyze-history",
        "status": "flaky",
        "confidence": 0.88,
        "reason": "Inconsistent pass/fail pattern detected",
        "is_intermittent": true
      },
      "github_url": "https://github.com/org/repo/blob/main/tests/test_model.py#L45",
      "test_file": "tests/test_model.py",
      "code_analysis": "uses_sleep=True, has_timeout=True",
      "fixtures": ["cluster", "model_server"]
    }
  ],
  "summary": {
    "Intermittent Failure": 1,
    "Product Bug": 1
  }
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Launch or component not found |
| 500 | Internal Server Error |
| 503 | Service Unavailable - LLM or RP not available |

---

## Examples

### cURL

```bash
# Health check
curl http://localhost:8000/health

# Analyze failures
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "launch_id": "9722",
    "component": "Model_server"
  }'

# Deep investigation with verification
curl -X POST http://localhost:8000/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "launch_id": "9722",
    "component": "Model_server",
    "push_to_rp": true,
    "verify_mode": "analyze-history"
  }'
```

### Python

```python
import requests

# Analyze failures
response = requests.post(
    "http://localhost:8000/api/v1/analyze",
    json={
        "launch_id": "9722",
        "component": "Model_server",
        "push_to_rp": True,
    }
)
results = response.json()

for result in results["results"]:
    print(f"{result['test_name']}: {result['classification']['category']}")
```

### Using TFA Client

```python
from src.api.client import TFAClient

async with TFAClient("http://localhost:8000") as client:
    results = await client.investigate(
        launch_id="9722",
        component="Model_server",
        push_to_rp=True,
    )
    
    for result in results:
        print(f"{result['test_name']}: {result['classification']}")
```

---

## Interactive Documentation

When running the server, access interactive API documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
