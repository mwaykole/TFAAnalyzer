# TFA Quick Reference

## Setup

```bash
pip install -r requirements.txt

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
| `analyze` | Analyze failures in a launch |
| `investigate` | Deep RCA with Thinker-Critic |

```bash
# Dry run
python main.py analyze -l 9657 -c ModelServer --dry-run

# Push to ReportPortal
python main.py analyze -l 9657 -c ModelServer --push

# Deep investigation
python main.py investigate -l 9657 -c ModelServer --push
```

### Server Mode

```bash
# Start server
python main.py serve --port 8000 --workers 4

# Use server (from any machine)
python main.py analyze -l 9657 -c ModelServer --server http://tfa:8000 --push
```

### Information

| Command | Description |
|---------|-------------|
| `list-launches` | Show recent launches |
| `component-logs` | Display failure logs |
| `test-history` | Show test pass/fail history |

```bash
python main.py list-launches -n 20
python main.py component-logs -l 9657 -c ModelServer
python main.py test-history -l 9657 -c ModelServer
```

### Analytics

| Command | Description |
|---------|-------------|
| `stats` | Overall statistics |
| `dashboard` | Full analytics dashboard |
| `health` | Component health scores |
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

---

## Common Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Preview without posting | False |
| `--push` | Post results to RP | False |
| `--json` | Output as JSON | False |
| `--output FILE` | Save to file | None |
| `--no-cache` | Disable caching | False |
| `--provider NAME` | LLM provider | claude-cli |
| `--high-accuracy` | High accuracy mode | True |
| `--cost-optimize` | Use cheaper model | False |

---

## Workflows

### Daily Triage

```bash
python main.py list-launches -n 10
python main.py analyze -l <ID> -c <COMPONENT> --dry-run
python main.py analyze -l <ID> -c <COMPONENT> --push
```

### Multi-Component

```bash
for comp in Model_server Workbenches TrustyAI Pipelines; do
  python main.py analyze -l 9657 -c $comp --push
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
| Product Bug | PB (pb001) | Real defect in product |
| Test Automation Issue | AB (ab001) | Test code problem |
| Infrastructure Issue | SI (si001) | Cluster/env issue |
| Flaky Test | AB (ab_1kbn5su3gqpdt) | Intermittent failure |

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
| Groq | Free | Fast | `GROQ_API_KEY` |
| Anthropic | Paid | Fast | `ANTHROPIC_API_KEY` |
| Ollama | Free | Slow | Local install |

```bash
# Use specific provider
python main.py analyze -l 9657 -c ModelServer --provider groq

# Cost optimization
python main.py analyze -l 9657 -c ModelServer --cost-optimize
```

---

## Troubleshooting

### Authentication Failed

```bash
echo $RP_URL
echo $RP_USERNAME
python main.py list-launches -n 1
```

### Slow Analysis

```bash
--cost-optimize
--provider groq
python main.py cache-stats
```

### Low Accuracy

```bash
--high-accuracy
--provider anthropic
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
```

---

## Web UI

```bash
# Terminal 1
python main.py serve --port 8000

# Terminal 2
cd ui
npm install
npm run dev
```

Access at http://localhost:3000

---

## Files

| File | Purpose |
|------|---------|
| `classification_rules.yaml` | Classification patterns |
| `knowledge_base.yaml` | Component knowledge |
| `config.yaml` | Configuration |
| `tfa_history.db` | SQLite history |

---

**Version**: 2.1 | **Last Updated**: January 2026
