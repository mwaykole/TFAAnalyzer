Produce the final RCA by synthesizing the initial analysis and critique.

## Initial Analysis
${initial_rca}

## Critique
${critique}

## Evidence Summary
- **Error**: ${error_message}
- **Patterns Detected**: ${patterns}
- **Suggested Confidence**: ${suggested_confidence}

## CRITICAL: Classification Rules (MUST FOLLOW)

Read your ROOT_CAUSE carefully, then apply these rules with CONTEXT:

| If Root Cause Contains... | Classification |
|--------------------------|---------------|
| "no matches for kind", missing CRD | **Product Bug** (dependency not installed) |
| "failed to reconcile", operator error | **Product Bug** (controller broken) |
| "RevisionFailed", container crash during model startup | **Product Bug** (runtime issue) |
| "LeaderWorkerSet" missing/not found | **Product Bug** (LLMD dependency) |
| InferenceService/ISVC not ready + healthy cluster + generous timeout | **Product Bug** |
| ServingRuntime not found/misconfigured | **Product Bug** |
| "assertion", "expected", "actual" mismatch | Test Automation Issue |
| "fixture", "setup", "teardown" failure in test code | Test Automation Issue |
| Short timeout (< 120s) for operation needing more time | Test Automation Issue |
| Pod failure (OOM, CrashLoop, ImagePull) | Infrastructure Issue |
| Network error (connection refused/reset) | Infrastructure Issue |
| "upstream connect error", "503", "service mesh" | Infrastructure Issue |
| "storage-initializer" failure (S3/model download) | Infrastructure Issue |
| "IngressNotConfigured" (Knative/Istio) | Infrastructure Issue |
| Authentication/credentials failure | Infrastructure Issue |
| GPU/CUDA error, unhealthy cluster | Infrastructure Issue |
| Product API returned wrong value/behavior | Product Bug |
| Product code crash/exception | Product Bug |
| Feature regression | Product Bug |
| Service fails to become ready despite generous timeout AND healthy cluster | Product Bug |
| Passed on retry, flaky history | Intermittent Failure |

### KSERVE/RHOAI ROOT CAUSE TRACING
This tool analyzes RHOAI/KServe test failures. When root cause involves model serving:
1. Check if CR `.status.conditions` shows the REAL error (not just "not ready")
2. `"no matches for kind"` = missing CRD = **Product Bug** (always!)
3. `"failed to reconcile"` = operator controller error = **Product Bug**
4. `"storage-initializer"` = S3/credentials = **Infrastructure Issue**
5. ISVC timeout + healthy cluster = **Product Bug** (product broken, test detected it)

### TIMEOUT IS A SYMPTOM, NOT A ROOT CAUSE
TimeoutExpiredError/TimeoutSampler tells you the test waited and gave up. Ask WHY:
- Timeout ≥ 300s + cluster HEALTHY + 0% pass rate → **Product Bug** (product is broken, test detected it correctly)
- Timeout < 120s for an operation needing more time → **Test Automation Issue** (timeout too short)
- Timeout + cluster DEGRADED/unhealthy pods → **Infrastructure Issue**
- Timeout + passes sometimes (pass rate 20-80%) → **Intermittent Failure**
- Timeout + CR status shows "no matches for kind" or "failed to reconcile" → **Product Bug** (not a timeout issue!)

## VALIDATION CHECK

Before responding, verify:
1. Does your ROOT_CAUSE match your CLASSIFICATION?
2. If timeout is generous (≥ 300s) and cluster is healthy, do NOT default to Test Automation Issue
3. If ROOT_CAUSE mentions "network", "connection", "upstream" → Infrastructure Issue
4. If ROOT_CAUSE mentions "no matches for kind", "failed to reconcile", missing CRD → Product Bug (NEVER Infrastructure Issue)
5. If must-gather resource_failures show CR status errors, use those as root cause

## Output Format (EXACT — follow precisely)

CLASSIFICATION: [Product Bug|Test Automation Issue|Infrastructure Issue|Intermittent Failure]
CONFIDENCE: [number]%
SEVERITY: [LOW|MEDIUM|HIGH|CRITICAL]
ROOT_CAUSE: [One specific sentence - what actually failed and why]
REASONING: [1-2 sentences - why this classification fits the root cause]
RECOMMENDATION: [Specific actionable steps]

CRITICAL RULES:
1. CLASSIFICATION must be EXACTLY one of: Product Bug, Test Automation Issue, Infrastructure Issue, Intermittent Failure.
2. "To Investigate" is FORBIDDEN — always commit to the most likely category.
3. If evidence is weak, lower CONFIDENCE (e.g., 40-60%) but still classify.
4. Your CLASSIFICATION must be consistent with your ROOT_CAUSE — do not contradict yourself.
