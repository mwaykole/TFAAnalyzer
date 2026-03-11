# TFA Quick Reference

## Setup

```bash
uv sync                # or: pip install -r requirements.txt

export RP_URL="https://reportportal.example.com"
export RP_USERNAME="your-username"
export RP_PASSWORD="your-password"
export RP_PROJECT="your-project"

python main.py list-launches -n 5
```

---

## Commands

### Analysis

| Command | Description |
|---------|-------------|
| `analyze` | Analyze failures (fast or deep) |
| `investigate` | Alias for `analyze --deep` |

```bash
# Fast classification (rule-based, no LLM)
python main.py analyze -l 10748 -c "Model Server"

# Deep LLM investigation
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli

# Deep + verify (re-run tests on cluster)
python main.py analyze -l 10748 -c "Model Server" --deep --verify --provider claude-cli

# Deep + must-gather cluster diagnostics
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli \
  --must-gather-path /path/to/must-gather-collected

# Push results to ReportPortal
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli --push

# Investigate (same as analyze --deep)
python main.py investigate -l 10748 -c "Model Server" --verify --provider claude-cli
```

### Server Mode

```bash
# Start server
python main.py serve --port 8000 --workers 4

# Use server (from any machine)
python main.py analyze -l 10748 -c "Model Server" --server http://tfa:8000 --push
```

### Information

| Command | Description |
|---------|-------------|
| `list-launches` | Show recent launches |
| `component-logs` | Display failure logs |
| `test-history` | Show test pass/fail history |

```bash
python main.py list-launches -n 20
python main.py component-logs -l 10748 -c "Model Server"
python main.py test-history -l 10748 -c "Model Server"
```

### Analytics

| Command | Description |
|---------|-------------|
| `stats` | Overall statistics |
| `dashboard` | Full analytics dashboard |
| `health` | Component health scores |
| `digest` | Weekly summary digest |
| `trends` | Failure trends |
| `accuracy-report` | Model accuracy metrics |

```bash
python main.py stats --days 30
python main.py dashboard --days 7
python main.py health --days 7
python main.py accuracy-report
```

### Utilities

| Command | Description |
|---------|-------------|
| `cache-stats` | Show cache statistics |
| `cache-clear` | Clear analysis cache |
| `learn` | Manage custom patterns |
| `record-feedback` | Record correction |
| `parse-logs` | Parse logs standalone |

---

## Common Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Preview without posting | False |
| `--push` | Post results to RP | False |
| `--deep` / `-d` | Enable LLM analysis | False |
| `--verify` | Re-run tests on cluster | False |
| `--analyze-history` | RP history flakiness check | False |
| `--must-gather-path` | Path to must-gather artifacts | None |
| `--json` / `-j` | Output as JSON | False |
| `--no-cache` | Disable caching | False |
| `--no-llm` | Rule-based only (fast path) | False |
| `--provider NAME` | LLM provider | claude-cli |
| `--server URL` | Use centralized TFA server | None |
| `-p, --project` | RP project name | env var |
| `--config` | Config file path | config.yaml |

---

## Workflows

### Daily Triage

```bash
python main.py list-launches -n 10
python main.py analyze -l <ID> -c <COMPONENT> --dry-run
python main.py analyze -l <ID> -c <COMPONENT> --push
```

### ODH/RHOAI with --verify

```bash
# 1. Clone: git clone https://github.com/opendatahub-io/opendatahub-tests
# 2. config.yaml: test_repo.enabled=true, local_path=/path/to/opendatahub-tests
# 3. Login: oc login --token=sha256~TOKEN --server=https://api.cluster:6443
# 4. Export env vars (see .env.ods.example)
python main.py analyze -l 10748 -c "Model Server" --deep --verify --provider claude-cli
```

### Multi-Component

```bash
for comp in "Model Server" Workbenches TrustyAI Pipelines; do
  python main.py analyze -l 10748 -c "$comp" --push
done
```

### Weekly Review

```bash
python main.py stats --days 7
python main.py health --days 7
python main.py dashboard --days 7
```

---

## Classification Categories

| Category | RP Code | When |
|----------|---------|------|
| Product Bug | PB (pb001) | Real defect in RHOAI/KServe component |
| Test Automation Issue | AB (ab001) | Test code problem (short timeout, bad assertion) |
| Infrastructure Issue | SI (si001) | Cluster/env issue (pod crash, auth, GPU, OOM) |
| Intermittent Failure | SI | Flaky (passes on retry, inconsistent history) |

---

## Confidence Levels

| Range | Action |
|-------|--------|
| 90-100% | Trust the result |
| 75-89% | Brief review |
| 60-74% | Careful review |
| < 60% | Manual review needed |

---

## LLM Providers

| Provider | Cost | Speed | Setup |
|----------|------|-------|-------|
| Claude CLI | Free | Medium | `which claude` |
| Anthropic | Paid | Fast | `ANTHROPIC_API_KEY` |
| Groq | Free | Fast | `GROQ_API_KEY` |
| Ollama | Free | Slow | Local install |

```bash
python main.py analyze -l 10748 -c "Model Server" --deep --provider groq
```

---

## Troubleshooting

### Authentication Failed

```bash
echo $RP_URL
echo $RP_USERNAME
python main.py list-launches -n 1
```

### Low Accuracy

```bash
python main.py learn --add
python main.py record-feedback --id <ID> --correct "Product Bug"
```

---

## Configuration

### Environment

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
  verify_ssl: false

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  temperature: 0.1

test_repo:
  enabled: true
  local_path: "/path/to/opendatahub-tests"

verification:
  timeout_per_test: 0
  collect_must_gather: true

must_gather:
  enabled: true
  base_path: "must-gather-collected"

analysis:
  confidence_threshold: 0.7

cache:
  enabled: true
  backend: memory
```

---

## Key Files

| File | Purpose |
|------|---------|
| `knowledge_base.yaml` | Domain rules, component context, quick rules |
| `config.yaml` | Configuration |
| `config.example.yaml` | Config template |
| `.env.example` | General env var template |
| `.env.ods.example` | ODH/RHOAI env vars for --verify |

---

**Version**: 3.0 | **Last Updated**: March 2026
