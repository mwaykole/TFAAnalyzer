# TFA (Test Failure Analyzer) - Team Demo & Presentation

---

## Slide 1: The Problem

### Manual Test Failure Triage is Painful

Every time a CI pipeline fails, someone has to:

1. Open ReportPortal
2. Navigate to the failed launch
3. Open each failed test one-by-one
4. Read through hundreds of lines of logs
5. Figure out: *Is this a real bug? A flaky test? An infra issue?*
6. Manually set the defect type in ReportPortal
7. Repeat for every failure, every launch, every day

**The cost:**

| Pain Point                    | Impact                                          |
|-------------------------------|--------------------------------------------------|
| Time per failure              | 5-15 minutes of manual log reading               |
| Inconsistency                 | Different engineers classify the same failure differently |
| Flaky test blindness          | Hard to spot patterns across launches            |
| Knowledge silos               | Only a few people know which errors mean what    |
| Scale                         | Dozens of failures per launch, multiple launches per day |

> **"We spend more time triaging failures than fixing them."**

---

## Slide 2: Introducing TFA

### What is TFA?

**TFA (Test Failure Analyzer)** is an AI-powered CLI tool that automatically analyzes RHOAI/ODH test failures from ReportPortal, classifies them, and posts results back — with deep KServe/RHOAI awareness.

```
          ReportPortal          OpenShift Cluster
               |                      |
               v                      v
    ┌────────────────────────────────────────┐
    │            TFA Analyzer                │
    │                                        │
    │  1. Fetch failures + nested step logs  │
    │  2. Fetch test source code (AST parse) │
    │  3. Parse must-gather artifacts (CRs)  │
    │  4. AI classify (Thinker-Critic-Refiner)│
    │  5. Calibrate confidence (evidence)    │
    │  6. Verify (re-run tests on cluster)   │
    │  7. Post results to ReportPortal       │
    └────────────────────────────────────────┘
               |
               v
       ReportPortal + Slack/Teams
```

### What does it produce?

For each failed test, TFA outputs:

- **Classification**: Product Bug, Test Automation Issue, Infrastructure Issue, Intermittent/Flaky
- **Calibrated Confidence**: Evidence-weighted score adjusted by verification results (e.g., Raw 80% → Calibrated 93%)
- **Root Cause Analysis**: What went wrong and why, tracing KServe resource chains when relevant
- **Verification Result**: Re-runs the test on a live cluster to confirm or adjust the classification
- **Must-Gather Insights**: CR status conditions, pod failures, events from cluster state
- **Recommendation**: Suggested fix with specific `oc` commands for debugging
- **Defect Type Update**: Automatically sets PB/AB/SI/TI in ReportPortal

---

## Slide 3: Classification Categories

TFA classifies every failure into one of these categories:

| Category                  | Icon | Meaning                              | RP Defect Type |
|---------------------------|------|--------------------------------------|----------------|
| **Product Bug**           | 🐛   | RHOAI/KServe component defect: CR reconciliation failure, missing CRD, service crash, model runtime error | PB |
| **Test Automation Issue** | 🔧   | Test code problem: short timeout, bad assertion, fixture issue | AB |
| **Infrastructure Issue**  | 🏗️   | Environment: pod failure, network, auth, GPU, OOM, storage-initializer, Knative/Istio | SI |
| **Intermittent Failure**  | ⚡   | Flaky: timing-dependent, passes on retry, inconsistent history | SI |

**Key KServe/RHOAI-aware classification rules:**

- `"no matches for kind LeaderWorkerSet"` → **Product Bug** (missing CRD dependency)
- `"failed to reconcile multi-node workload"` → **Product Bug** (operator error)
- Generous timeout (>= 300s) + healthy cluster + consistent failure → **Product Bug** (product is broken)
- `"storage-initializer failed"` → **Infrastructure Issue** (S3 credentials)
- Short timeout (< 120s) → **Test Automation Issue** (wait time too short)

**Key point:** These map directly to ReportPortal defect types. "To Investigate" is explicitly forbidden — TFA always commits to one of the four categories.

---

## Slide 4: How It Works - The Hybrid Approach

TFA uses two analysis paths to balance speed, cost, and accuracy:

```
                     Failed Test
                         │
                         ▼
              ┌─────────────────────┐
              │  Log Parsing &      │
              │  Pattern Matching   │
              │  (18+ KServe rules) │
              └─────────────────────┘
                         │
               ┌─────────┴──────────┐
               │                    │
        High Confidence?     Low Confidence?
         (known pattern)     (complex failure)
               │                    │
               ▼                    ▼
        ┌──────────┐     ┌──────────────────────────┐
        │ FAST PATH│     │   DEEP PATH (--deep)     │
        │ Rule-    │     │                          │
        │ Based    │     │  Evidence Gathering:     │
        │ (free!)  │     │   ├── Test code (AST)    │
        │          │     │   ├── Must-gather (CRs)  │
        │          │     │   ├── RP history          │
        │          │     │   └── Few-shot examples   │
        │          │     │                          │
        │          │     │  LLM Reasoning:          │
        │          │     │   Thinker → Critic →     │
        │          │     │   Refiner                │
        │          │     │                          │
        │          │     │  Post-LLM:              │
        │          │     │   ├── Heuristic reclass  │
        │          │     │   └── Confidence calib   │
        └──────────┘     └──────────────────────────┘
               │                    │
               │              ┌─────┴───────┐
               │              │  --verify?  │
               │              └─────┬───────┘
               │                    ▼
               │         ┌──────────────────┐
               │         │ Re-run on cluster │
               │         │ + must-gather     │
               │         │ (sequential)      │
               │         └──────────────────┘
               │                    │
               └─────────┬──────────┘
                         ▼
                   Classification
                   + Root Cause
                   + Calibrated Confidence
                   + Verification Result
                   + Recommendation
```

### Fast Path (Pattern Matching)

Known patterns are matched instantly, with zero LLM cost:

- `OOMKilled` / `CrashLoopBackOff` → Infrastructure Issue
- `no matches for kind "LeaderWorkerSet"` → Product Bug (missing CRD dependency)
- `failed to reconcile multi-node workload` → Product Bug (LLMD operator error)
- `InferenceService not ready` + generous timeout + healthy cluster → Product Bug
- `storage-initializer failed` → Infrastructure Issue (S3 credentials)
- `AssertionError: expected 200 got 503` → Product Bug
- `TimeoutExpiredError` with short timeout (< 120s) → Test Automation Issue

### Deep Path (Thinker-Critic-Refiner LLM)

For complex failures, TFA uses a 3-step LLM reasoning chain with evidence gathering:

| Step       | Role     | What it does                                           |
|------------|----------|--------------------------------------------------------|
| **Gather** | EVIDENCE | Fetch test code, must-gather CRs, RP history, few-shot examples |
| **Step 1** | THINKER  | Reads all evidence, proposes initial root cause tracing KServe resource chain |
| **Step 2** | CRITIC   | Challenges the analysis — "Did you check CR .status.conditions?" |
| **Step 3** | REFINER  | Synthesizes final answer considering the critique      |
| **Post**   | CALIBRATE| Adjusts confidence based on evidence strength + verification |

### Must-Gather Analysis

When must-gather artifacts are available, TFA parses:

- **CR status conditions** on InferenceService, LLMInferenceService, ServingRuntime, LeaderWorkerSet, DataScienceCluster, etc.
- **Pod failures** — CrashLoopBackOff, OOMKilled, ImagePullBackOff, scheduling failures
- **Events** — warnings, errors, and abnormal events
- **Container logs** — storage-initializer, kserve-container, queue-proxy

This distinguishes product bugs from infrastructure issues by reading the actual cluster state.

---

## Slide 5: Architecture Overview

TFA follows Clean Architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                           │
│   CLI (Typer + Rich)              REST API (FastAPI)           │
│   python main.py analyze ...      POST /api/v1/analyze         │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                            │
│   AnalyzeFailureUseCase          InvestigateRCAUseCase         │
│   (fast path)                    (deep path + verify)          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                                 │
│   ClassificationService    InvestigationService                │
│   VerificationService      EnhancedAnalysis (calibration)      │
│   Entities: Failure, RCA, Evidence, Classification             │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                         │
│   LLM Providers      Cache          ReportPortal Client        │
│   (Claude/Groq/       (Redis/        (fetch logs, nested       │
│    Ollama)             Memory)         steps, defect types)     │
│   Code Fetcher       Must-Gather     Embeddings                │
│   (GitHub/Local       (Parser +       (Few-shot learning       │
│    + AST parser)       Analyzer)       failure store)           │
│   Notifications                                                │
│   (Slack/Teams)                                                │
└─────────────────────────────────────────────────────────────────┘
```

**Key modules:**

```
src/
├── api/                # FastAPI server for team deployment
├── application/        # Use cases (Analyze, Investigate)
├── domain/             # Core business logic
│   ├── entities/       # Failure, Classification, RCA, Evidence
│   ├── interfaces/     # LLM, Cache, CodeFetcher, Notifier abstractions
│   └── services/       # Classification, Investigation, Verification, EnhancedAnalysis
├── infrastructure/     # External integrations
│   ├── llm/            # Claude CLI, Anthropic, Groq, Ollama adapters
│   ├── cache/          # Redis, Memory cache
│   ├── code_fetcher/   # GitHub, Local fetchers + AST test parser
│   ├── reportportal/   # RP client, component fetcher, test history
│   ├── k8s/            # Must-gather parser + analyzer (CR status, pods, events)
│   ├── embeddings/     # Text embedder, failure embedding store (few-shot)
│   └── notifications/  # Slack, Teams notifiers
├── prompts/            # LLM prompt templates
│   ├── investigation/  # Thinker, Critic, Refiner, Evidence prompts
│   ├── system/         # Compact system prompt
│   └── context/        # RHOAI/KServe knowledge base prompt
└── utils/              # Config, logging, metrics, knowledge base loader
```

---

## Slide 6: Supported LLM Providers

TFA supports multiple LLM backends -- pick what works for your team:

| Provider       | Setup                      | Cost                | Speed    | Best For                  |
|----------------|----------------------------|---------------------|----------|---------------------------|
| `claude-cli`   | Install Claude CLI         | Free (CLI tier)     | Fast     | Local dev, quick analysis |
| `anthropic`    | Set `ANTHROPIC_API_KEY`    | ~$0.003/analysis    | Fast     | Production use            |
| `groq`         | Set `GROQ_API_KEY`         | Free (rate limited) | Fastest  | High volume, budget       |
| `ollama`       | Run Ollama locally         | Free                | Variable | Air-gapped environments   |

Switch providers with a single flag:

```bash
python main.py investigate -l 10748 -c "Model Server" --provider groq
python main.py investigate -l 10748 -c "Model Server" --provider anthropic
python main.py investigate -l 10748 -c "Model Server" --provider ollama
# Or equivalently with analyze --deep:
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli
```

---

# LIVE DEMO

---

## Demo Step 1: Setup & Configuration

### 1.1 Install dependencies

```bash
git clone https://github.com/your-org/TFAAnalyzer.git
cd TFAAnalyzer
pip install -r requirements.txt
```

### 1.2 Configure environment

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

Edit `.env` with your credentials:

```bash
# Required
RP_URL="https://reportportal.your-company.com"
RP_USERNAME="your-username"
RP_PASSWORD="your-password"
RP_PROJECT="your-project"

# Optional - for LLM analysis
ANTHROPIC_API_KEY="sk-ant-..."
GROQ_API_KEY="gsk_..."
GITHUB_TOKEN="ghp_..."

# Optional - for notifications
SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
```

Edit `config.yaml` for LLM, test repo, must-gather, and verification settings:

```yaml
reportportal:
  url: ""            # Uses RP_URL from .env
  project: ""        # Uses RP_PROJECT from .env
  verify_ssl: false

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  max_tokens: 4096
  temperature: 0.1

test_repo:
  enabled: true
  repo: "your-org/your-test-repo"
  branch: "main"
  local_path: "/path/to/opendatahub-tests"  # For --verify mode

must_gather:
  enabled: true
  base_path: "/path/to/must-gather-collected"  # Where must-gather artifacts live

verification:
  timeout_per_test: 0       # 0 = let test's own timeout handle it
  max_parallel: 1           # Sequential execution (avoids cluster resource contention)
  collect_must_gather: true  # Auto-collect must-gather on failure

cache:
  enabled: true
  backend: memory    # Use 'redis' for team server
```

### 1.3 Verify connection

```bash
python main.py list-launches -n 5
```

**Expected output:**

```
┌──────────────────────────────────────────────────────────────────┐
│              Recent Launches (5 of 342)                         │
├──────┬──────────────────────────┬────────┬────────┬──────┬──────┤
│ ID   │ Name                     │ Status │ Passed │Failed│Total │
├──────┼──────────────────────────┼────────┼────────┼──────┼──────┤
│ 9722 │ nightly-pipeline-run     │ FAILED │   145  │  12  │  157 │
│ 9721 │ nightly-pipeline-run     │ FAILED │   148  │   9  │  157 │
│ 9720 │ nightly-pipeline-run     │ PASSED │   157  │   0  │  157 │
│ 9719 │ pr-check-feature-xyz     │ FAILED │    42  │   3  │   45 │
│ 9718 │ nightly-pipeline-run     │ FAILED │   150  │   7  │  157 │
└──────┴──────────────────────────┴────────┴────────┴──────┴──────┘
```

> **Speaker note:** Point out we can see launch IDs, pass/fail counts at a glance. Pick a failed launch for the next step.

---

## Demo Step 2: View Component Failures

Before analyzing, let's see what failed:

```bash
python main.py component-logs -l 10748 -c "Model Server"
```

**Expected output:**

```
╭─────────────── Launch Information ───────────────╮
│ Launch: nightly-pipeline-run                     │
│ ID: 9722                                         │
│ Start Time: 2026-03-03 22:00:00                  │
│ Status: FAILED                                   │
╰──────────────────────────────────────────────────╯

┌────────────────────────────────────┬────────┬──────────┐
│ Component                          │ Status │ Failures │
├────────────────────────────────────┼────────┼──────────┤
│ Model_server                       │ FAILED │        5 │
│ Dashboard                          │ PASSED │        - │
│ Pipeline_server                    │ FAILED │        2 │
└────────────────────────────────────┴────────┴──────────┘

Component: Model_server

  ✗ test_model_deploy_runtime_gpu
    TimeoutError: Model deployment timed out after 300s...

  ✗ test_model_inference_rest_api
    AssertionError: expected status 200, got 503...

  ✗ test_model_scaling_replicas
    ConnectionRefusedError: connect to model-mesh:8033...
```

> **Speaker note:** Now we can see the raw failures. Normally you'd have to read each one, figure out the category, and update RP manually. Let's let TFA do it.

---

## Demo Step 3: Quick Analysis (Fast Path)

Run the fast, pattern-based classification:

```bash
python main.py analyze -l 10748 -c "Model Server" --dry-run
```

**Expected output:**

```
Analyzing 5 failures in Model_server (launch 9722)...

  🐛 test_model_inference_rest_api
     Classification: Product Bug (confidence: 92%)
     Root Cause: HTTP 503 from model endpoint indicates service crash
     Recommendation: Check model server logs for OOM or startup failure

  🏗️ test_model_deploy_runtime_gpu
     Classification: Infrastructure Issue (confidence: 88%)
     Root Cause: Deployment timeout suggests GPU node scheduling issue
     Recommendation: Verify GPU node availability in cluster

  🏗️ test_model_scaling_replicas
     Classification: Infrastructure Issue (confidence: 95%)
     Root Cause: Connection refused to model-mesh service
     Recommendation: Check if model-mesh pods are running

  ⚡ test_model_prediction_latency
     Classification: Intermittent Failure (confidence: 78%)
     Root Cause: Latency assertion exceeded threshold by small margin
     Recommendation: Review test threshold or add retry logic

  🔧 test_model_metadata_validation
     Classification: Test Automation Issue (confidence: 85%)
     Root Cause: Test expects deprecated API field
     Recommendation: Update test to use new metadata schema

╭─────────────── Summary ───────────────╮
│ 🐛 Product Bug:           1           │
│ 🏗️ Infrastructure Issue:  2           │
│ ⚡ Intermittent Failure:   1           │
│ 🔧 Test Automation Issue: 1           │
│                                       │
│ Total: 5 failures analyzed            │
│ Mode: DRY RUN (no changes posted)     │
╰───────────────────────────────────────╯
```

> **Speaker note:** This ran in seconds using pattern matching -- no LLM calls. The `--dry-run` flag previews without posting to RP. Remove it and add `--push` to post results.

### Push results to ReportPortal

```bash
python main.py analyze -l 10748 -c "Model Server" --push
```

This updates the defect type for each failure in ReportPortal automatically.

---

## Demo Step 4: Deep Investigation (Thinker-Critic-Refiner)

For failures where pattern matching isn't enough, use `analyze --deep` or the standalone `investigate` command:

```bash
# Option A: Unified command
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli

# Option B: Standalone investigate command (equivalent)
python main.py investigate -l 10748 -c "Model Server" --provider claude-cli
```

**What happens behind the scenes:**

```
Step 1: Fetch failures + nested step logs from ReportPortal
           │
Step 2: Group failures by error signature
           │  (same root cause → analyzed once, applied to all)
           │
Step 3: For each unique error group (in parallel):
           │
           ├── Gather evidence:
           │   ├── Fetch test source code (GitHub or local)
           │   ├── AST-parse test code (extract timeout values, wait patterns)
           │   ├── Fetch RP history (pass/fail pattern, linked JIRA tickets)
           │   ├── Parse must-gather artifacts (CR status conditions, pod failures)
           │   ├── Run failure clustering (detect systemic issues)
           │   └── Find similar past failures (few-shot learning)
           │
           ├── THINKER → reads ALL evidence, proposes root cause
           │   (traces KServe resource chain for model serving failures)
           │
           ├── CRITIC → challenges the analysis
           │   ("Did you check CR .status.conditions? Is the timeout generous?")
           │
           ├── REFINER → synthesizes final RCA considering the critique
           │
           ├── POST-LLM heuristics → evidence-based reclassification
           │   (catches LLM mistakes using deterministic rules)
           │
           └── CALIBRATE → adjust confidence based on evidence strength
           │
Step 4: Post RCA comments and defect types to ReportPortal
```

**Example output (from a real run against launch 10748):**

```
╭──────────────────────────╮
│ 🔍 Investigation Results │
│ Launch: 10748            │
│ Component: Model Server  │
│ Failures: 5              │
╰──────────────────────────╯

🐛 test_llmisvc_authorized
   Classification: Product Bug
   Severity: MEDIUM | Confidence: 80%
   Calibrated: 93% (Raw: 80% → evidence_strength: +5% →
     verification_confirmed: +20% → Final: 93%)
   Root Cause: LLMInferenceService reconciliation failed —
     Gateway resource was never created. 900s timeout is generous
     for a 1.1B model that should be ready in 2-5 minutes.
   Verification: failed (exit=1) — confirmed consistent failure

🔄 test_llmd_oci_cpu
   Classification: Intermittent Failure
   Severity: LOW | Confidence: 95%
   Calibrated: 98% (verification_confirmed: +20%)
   Root Cause: Test passed on re-run, confirming intermittent behavior.
     Original error: TimeoutExpiredError.
   Verification: passed (exit=0) — confirmed intermittent

              Summary
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Classification          ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 🔄 Intermittent Failure │     2 │
│ 🐛 Product Bug          │     3 │
└─────────────────────────┴───────┘
```

> **Speaker note:** Notice the **calibrated confidence** — the raw LLM confidence (80%) gets boosted to 93% because verification confirmed the failure is real. TFA groups failures by error signature and analyzes each group once to save LLM calls.

---

## Demo Step 5: Must-Gather Investigation

TFA analyzes must-gather artifacts to read actual cluster state — CR status conditions, pod failures, and events.

### Option A: Use existing must-gather

If you already have must-gather artifacts collected:

```bash
# Using analyze --deep
python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli \
  --must-gather-path /path/to/must-gather-collected

# Using investigate
python main.py investigate -l 10748 -c "Model Server" --provider claude-cli \
  --must-gather-path /path/to/must-gather-collected
```

Or configure the path in `config.yaml`:

```yaml
must_gather:
  enabled: true
  base_path: "/path/to/opendatahub-tests/must-gather-collected"
```

### Option B: Auto-collect during verification

When using `--verify`, must-gather is collected automatically after each failed test re-run:

```bash
# Using analyze --deep --verify
python main.py analyze -l 10748 -c "Model Server" --deep --verify --provider claude-cli

# Using investigate --verify
python main.py investigate -l 10748 -c "Model Server" --verify --provider claude-cli
```

The `opendatahub-tests` framework's `--collect-must-gather` flag is added to the pytest command.

### What does must-gather analysis find?

TFA parses must-gather directories and extracts:

```
Must-Gather Analysis:
  cluster_health: degraded
  resource_failures:
    - llminferenceservice/llmd-ns/llm-test:
        Ready=False: "failed to reconcile multi-node main workload:
        failed to build the expected main LWS: no matches for kind
        LeaderWorkerSet in version leaderworkerset.x-k8s.io/v1"
    - inferenceservice/serving-ns/my-model:
        PredictorReady=False: "RevisionFailed — container crashed"
  unhealthy_pods:
    - storage-initializer (Exit code 1) — S3 credentials invalid
    - kserve-container (OOMKilled) — model exceeds memory limit
  events:
    - FailedScheduling: insufficient nvidia.com/gpu
```

The must-gather analyzer checks these CR types:
| CR Type | What TFA Extracts |
|---------|-------------------|
| InferenceService / LLMInferenceService | `.status.conditions` — Ready, PredictorReady, IngressReady |
| ServingRuntime / ClusterServingRuntime | Runtime configuration errors |
| LeaderWorkerSet | Multi-node orchestration failures |
| Knative Revision / Configuration | Container crash details |
| DataScienceCluster / DSCInitialization | RHOAI platform health |

> **Speaker note:** This is critical — many model serving failures show as `TimeoutExpiredError`, but the REAL root cause is in the CR `.status.conditions`. Must-gather lets TFA trace the KServe resource chain automatically.

---

## Demo Step 6: Verification Mode

TFA can re-run failed tests on the live cluster to confirm or adjust classifications.

### Prerequisites

```bash
# 1. Login to the cluster with a cluster-admin token
oc login --token=sha256~<TOKEN> --server=https://api.your-cluster.com:6443

# 2. Set environment variables for test framework
source .env.ods   # Copy from .env.ods.example

# 3. Configure test repo path
# config.yaml:
test_repo:
  local_path: "/path/to/opendatahub-tests"
```

### Run with verification

```bash
# Using analyze --deep --verify
python main.py analyze -l 10748 -c "Model Server" --deep --verify --provider claude-cli

# Using investigate --verify
python main.py investigate -l 10748 -c "Model Server" --verify --provider claude-cli
```

Tests are re-run **sequentially** (one at a time) to avoid resource contention on shared cluster resources like Gateways:

```
Investigating 5 failures...
  verification_slot_acquired: test_llmisvc_authorized
  → FAILED (exit=1) — confirmed consistent failure → Product Bug boosted
  verification_slot_acquired: test_llmd_oci_cpu
  → PASSED (exit=0) — confirmed intermittent → classification adjusted

Verification Results:
  test_llmisvc_authorized:    FAILED on re-run → Confirmed Product Bug (93%)
  test_llmd_oci_cpu:          PASSED on re-run → Confirmed Intermittent (98%)
  test_llmd_gateway_bypass:   FAILED on re-run → Product Bug (auth bypass)
```

### How verification adjusts confidence

| Scenario | Original | Re-run Result | Confidence Change |
|----------|----------|---------------|-------------------|
| Product Bug → re-run fails | 80% | FAILED | +20% → **93%** (confirmed) |
| Product Bug → re-run passes | 80% | PASSED | -25% → reclassified to Intermittent |
| Intermittent → re-run passes | 75% | PASSED | +20% → **90%** (confirmed flaky) |
| Intermittent → re-run fails | 75% | FAILED | -25% → reclassified to Product Bug |

> **Speaker note:** The `max_parallel: 1` default ensures tests run one at a time on the cluster, preventing Gateway/resource conflicts we saw during early parallel verification runs.

---

## Demo Step 7: Analytics & Tracking

### View classification statistics

```bash
python main.py stats --days 30
```

**Expected output:**

```
╭─────────────── 📊 Overall Statistics ───────────────╮
│ Total Analyses:    847                               │
│ Unique Launches:   62                                │
│ Unique Tests:      198                               │
│ Components:        12                                │
│ First Analysis:    2026-02-01                        │
│ Last Analysis:     2026-03-04                        │
╰──────────────────────────────────────────────────────╯

Classification Summary (Last 30 Days)
┌───────────────────────────┬───────┬────────────┐
│ Classification            │ Count │ Percentage │
├───────────────────────────┼───────┼────────────┤
│ 🐛 Product Bug            │  187  │   22.1%    │
│ 🔧 Test Automation Issue  │  245  │   28.9%    │
│ 🏗️ Infrastructure Issue   │  198  │   23.4%    │
│ ⚡ Intermittent Failure    │  156  │   18.4%    │
│ ❓ To Investigate          │   61  │    7.2%    │
└───────────────────────────┴───────┴────────────┘

Component Health (Last 30 Days)
┌──────────────────┬───────┬────────┬────────┬───────┬──────────┐
│ Component        │ Total │ 🐛 Bugs│ 🔧 Auto│ ⚡Flaky│ Avg Conf │
├──────────────────┼───────┼────────┼────────┼───────┼──────────┤
│ Model_server     │   124 │    31  │    38  │   29  │    89%   │
│ Pipeline_server  │    98 │    22  │    29  │   18  │    91%   │
│ Dashboard        │    67 │    18  │    21  │   12  │    87%   │
└──────────────────┴───────┴────────┴────────┴───────┴──────────┘

⚠️ Tests with Inconsistent Classifications (3):
  • test_model_prediction_latency - ["Intermittent Failure", "Product Bug"]
  • test_pipeline_timeout_large - ["Infrastructure Issue", "Intermittent Failure"]
```

### View accuracy report

```bash
python main.py accuracy-report --days 30
```

### Record feedback to improve accuracy

```bash
python main.py record-feedback --id 42 --correct "Product Bug" --by "John"
```

> **Speaker note:** Feedback loop -- if TFA gets it wrong, we record the correction. This helps track accuracy and can feed into future improvements.

---

## Demo Step 8: Team Server Mode

For team-wide deployment with shared caching:

### Start the server

```bash
python main.py serve --port 8000
```

```
INFO:     TFA API server starting...
INFO:     Redis cache connected (redis://localhost:6379)
INFO:     Swagger docs: http://localhost:8000/docs
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Use from CLI (any team member)

```bash
python main.py analyze -l 10748 -c "Model Server" --server http://tfa-server:8000 --push
```

### Use via REST API (CI/CD integration)

```bash
curl -X POST http://tfa-server:8000/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "launch_id": "9722",
    "component": "Model_server",
    "push_to_rp": true,
    "verify_mode": "analyze-history"
  }'
```

### API documentation

Visit `http://tfa-server:8000/docs` for interactive Swagger UI.

### Docker Compose deployment

```bash
docker-compose up -d    # Starts TFA API + Redis
```

### Why server mode?

| Benefit                     | Details                                              |
|-----------------------------|------------------------------------------------------|
| **95% Cache Hit Rate**      | Same failure analyzed once, cached for all users     |
| **Consistent Results**      | Everyone gets the same classification                |
| **Cost Savings**            | Shared LLM calls instead of duplicate calls per user |
| **CI/CD Integration**       | POST to API from Jenkins/GitLab pipelines            |
| **Centralized Metrics**     | Track accuracy and usage across the team             |

---

## Demo Step 9: Notifications

### Slack notifications

When `--push` is used, TFA can send a summary to Slack:

```
┌────────────────────────────────────────────────────┐
│  🔍 TFA Analysis Complete                          │
│                                                    │
│  Launch: 9722 (nightly-pipeline-run)               │
│  Component: Model_server                           │
│                                                    │
│  🐛 Product Bug:          1                        │
│  🏗️ Infrastructure Issue: 2                        │
│  ⚡ Intermittent Failure:  1                        │
│  🔧 Test Automation Issue: 1                       │
│                                                    │
│  Total: 5 failures analyzed                        │
│  View in ReportPortal →                            │
└────────────────────────────────────────────────────┘
```

### Teams notifications

Same format, delivered to Microsoft Teams via webhook.

Configure in `.env`:

```bash
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/..."
```

---

## Slide 7: Code-Level Intelligence

TFA doesn't just read logs -- it can fetch and analyze test source code:

### What it detects via AST parsing:

| Signal                 | What TFA finds                     | Implication              |
|------------------------|------------------------------------|--------------------------|
| `time.sleep()` calls   | Hardcoded wait times               | Timing-dependent = flaky |
| `@retry` decorators    | Retry logic in test                | Author knew it was flaky |
| `@timeout` decorators  | Explicit timeout constraints       | Timeout-sensitive test   |
| Wait/poll patterns     | `wait_for()`, polling loops        | Async dependency         |
| Fixtures used          | Setup/teardown dependencies        | Environment sensitivity  |

### GitHub integration:

RCA comments posted to ReportPortal include links to the exact test source:

```markdown
**Test Source:** [tests/model/test_inference.py#L45](https://github.com/your-org/tests/blob/main/tests/model/test_inference.py#L45)

**Flakiness Indicators:**
- Line 52: `time.sleep(10)` - hardcoded wait
- Line 38: `@pytest.mark.flaky(reruns=3)` - known flaky marker
```

---

## Slide 8: Complete Command Reference

| Command              | Purpose                                   | Example                                                     |
|----------------------|-------------------------------------------|--------------------------------------------------------------|
| `list-launches`      | List recent launches                      | `python main.py list-launches -n 20`                         |
| `component-logs`     | View failures with logs                   | `python main.py component-logs -l 10748 -c "Model Server"`  |
| `test-history`       | Show pass/fail history                    | `python main.py test-history -l 10748`                       |
| `analyze`            | Quick pattern-based classification        | `python main.py analyze -l 10748 -c "Model Server" --push`  |
| `analyze --deep`     | Deep Thinker-Critic-Refiner RCA           | `python main.py analyze -l 10748 -c "Model Server" --deep --provider claude-cli` |
| `analyze --verify`   | Deep RCA + re-run tests on cluster        | `python main.py analyze -l 10748 -c "Model Server" --deep --verify --provider claude-cli` |
| `analyze --must-gather-path` | Deep RCA with existing must-gather | `python main.py analyze -l 10748 -c "Model Server" --deep --must-gather-path /path/to/mg` |
| `investigate`        | Standalone deep investigation (same as `analyze --deep`) | `python main.py investigate -l 10748 -c "Model Server" --provider claude-cli` |
| `investigate --verify` | Deep investigation + re-run tests      | `python main.py investigate -l 10748 -c "Model Server" --verify --provider claude-cli` |
| `serve`              | Start API server                          | `python main.py serve --port 8000`                           |
| `stats`              | View classification statistics            | `python main.py stats --days 30`                             |
| `dashboard`          | Analytics dashboard                       | `python main.py dashboard --days 30`                         |
| `digest`             | Weekly summary digest                     | `python main.py digest --days 7`                             |
| `record-feedback`    | Correct a misclassification               | `python main.py record-feedback --id 42 --correct "PB"`     |
| `parse-logs`         | Debug log parsing locally                 | `python main.py parse-logs failure.log`                      |
| `accuracy-report`    | Model accuracy metrics                    | `python main.py accuracy-report --days 30`                   |

---

## Slide 9: Performance & Impact

| Metric                          | Before TFA         | After TFA            |
|---------------------------------|---------------------|----------------------|
| Time to triage per failure      | 5-15 minutes        | 3-10 seconds         |
| Classification consistency      | Varies by engineer  | 90%+ consistent      |
| Flaky test detection            | Manual, ad-hoc      | Automatic, data-driven |
| ReportPortal defect type updates| Manual, often skipped| Automatic            |
| Cross-launch pattern detection  | Nearly impossible   | Built-in             |
| Knowledge sharing               | Tribal knowledge    | Codified in rules    |

### Cost efficiency

| Item                      | Cost                            |
|---------------------------|---------------------------------|
| Per analysis (cached)     | $0 (instant)                    |
| Per analysis (LLM)        | ~$0.003 - $0.005                |
| With 95% cache hit rate   | ~$0.0002 per analysis average   |
| Free providers (Groq/Ollama)| $0                            |

---

## Slide 10: Getting Started for Your Team

### Quick start (5 minutes)

```bash
# 1. Clone and install
git clone <repo-url>
cd TFAAnalyzer
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your RP credentials

# 3. Test connection
python main.py list-launches -n 5

# 4. Analyze a launch
python main.py analyze -l <LAUNCH_ID> -c <COMPONENT> --dry-run

# 5. Push results when satisfied
python main.py analyze -l <LAUNCH_ID> -c <COMPONENT> --push
```

### For deeper analysis

```bash
# Set up an LLM provider (pick one)
export ANTHROPIC_API_KEY="sk-ant-..."   # Option A: Anthropic
export GROQ_API_KEY="gsk_..."           # Option B: Groq (free)
# Or install Claude CLI                 # Option C: Claude CLI (free)

# Run deep investigation (two equivalent ways)
python main.py investigate -l <LAUNCH_ID> -c "<COMPONENT>" --provider claude-cli
python main.py analyze -l <LAUNCH_ID> -c "<COMPONENT>" --deep --provider claude-cli

# With must-gather analysis
python main.py investigate -l <LAUNCH_ID> -c "<COMPONENT>" --provider claude-cli \
  --must-gather-path /path/to/must-gather

# With verification (re-run tests + must-gather collection)
python main.py investigate -l <LAUNCH_ID> -c "<COMPONENT>" --verify --provider claude-cli
```

### For team deployment

```bash
# Start server with Redis for shared caching
docker-compose up -d

# Everyone uses the server
python main.py analyze -l <ID> -c "<COMP>" --server http://tfa-server:8000 --push
```

---

## Slide 11: Workflow Integration Ideas

### CI/CD Pipeline Integration

```yaml
# Jenkinsfile / GitLab CI example
post_failure:
  - curl -X POST http://tfa-server:8000/api/v1/analyze \
      -d '{"launch_id": "$RP_LAUNCH_ID", "component": "Model Server",
           "deep": true, "push_to_rp": true}'
```

### Daily triage workflow

```
Morning standup:
  1. TFA already analyzed overnight failures
  2. Check Slack notification for summary
  3. Open ReportPortal - defect types already set
  4. Focus on Product Bugs (real issues)
  5. Ignore confirmed flaky tests
  6. File infra tickets for cluster issues
```

### Trend monitoring

```bash
# Weekly: check what's getting flakier
python main.py digest --days 7

# Monthly: accuracy and classification trends
python main.py accuracy-report --days 30
python main.py stats --days 30
```

---

## Q&A Topics

**Q: How accurate is it?**
A: 90%+ for pattern-matched failures, 92-97% with Thinker-Critic-Refiner LLM analysis. Confidence is calibrated based on evidence strength, verification results, and similar past failures. Track accuracy with the `accuracy-report` command.

**Q: Does it modify anything in ReportPortal?**
A: Only when you use `--push`. It sets the defect type and adds an RCA comment. Use `--dry-run` to preview first.

**Q: What if it gets a classification wrong?**
A: Use `record-feedback` to correct it. You can also manually override in ReportPortal as usual. Post-LLM heuristics catch common misclassifications (e.g., generous timeout with healthy cluster mislabeled as Test Automation Issue instead of Product Bug).

**Q: Is it expensive to run?**
A: Pattern matching is free. LLM calls cost ~$0.003-0.005 each. With caching (95% hit rate), team cost is minimal. Groq and Ollama providers are completely free.

**Q: Can I use it without an LLM?**
A: Yes. The `analyze` command (without `--deep`) uses pattern matching and doesn't require an LLM. It covers 18+ KServe/RHOAI-specific patterns plus general infrastructure patterns.

**Q: How does must-gather analysis work?**
A: TFA parses must-gather directories (or zips), extracts CR `.status.conditions` for KServe resources (InferenceService, LLMInferenceService, ServingRuntime, LeaderWorkerSet, etc.), pod failures, and events. This lets it distinguish "product is broken" from "infrastructure is down" by reading actual cluster state. You can provide must-gather via `--must-gather-path` or configure `must_gather.base_path` in `config.yaml`. With `--verify`, must-gather is auto-collected after each failed test re-run.

**Q: What is the Thinker-Critic-Refiner pattern? Is it LangChain?**
A: No external agent frameworks. TFA uses a custom 3-step LLM reasoning chain: (1) Thinker proposes a root cause with full evidence context, (2) Critic challenges it with domain expertise, (3) Refiner synthesizes the final answer. Each step is a direct Claude API call — no LangChain, CrewAI, or AutoGen dependencies.

**Q: Does `--verify` actually run tests on the cluster?**
A: Yes. It runs `uv run pytest -k <test_name>` against the `opendatahub-tests` repo on a live cluster. Tests are run sequentially (one at a time) to prevent Gateway/resource contention. Requires `oc login` with a cluster-admin token.

**Q: How do I add new patterns?**
A: Edit `knowledge_base.yaml` to add domain-specific rules, known errors, and component context. The `src/domain/services/classification_service.py` has `DEFINITIVE_PATTERNS` for high-confidence regex-based classification.

**Q: Does it work with private test repos?**
A: Yes. Set `GITHUB_TOKEN` for private GitHub repos, or use `local_path` in `config.yaml` to point to a local clone.

---

*TFA v3.0 | Python 3.11+ | RHOAI/KServe-aware | Apache 2.0 License*
