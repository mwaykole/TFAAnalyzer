Analyze this test failure step by step:

## Failure Details
- **Test**: ${test_name}
- **Error**: ${error_type}: ${error_message}
- **Detected Patterns**: ${patterns}
- **Stack Trace**: ${stack_trace}
- **Test Decorators**: ${decorators}

## Analysis Steps
1. What is the primary error? (the actual exception/failure point)
2. What triggered this error? (the underlying cause)
3. Is this a product issue, test issue, or infrastructure issue?
4. How confident are you? (based on available evidence)

## Classification (MUST pick exactly one)
1. **Product Bug** - Defect in RHOAI/ODH/KServe component code: service fails despite healthy cluster, CR reconciliation error, missing CRD dependency, model runtime crash, inference failure
2. **Test Automation Issue** - Problem with test code (short timeout, bad assertion, fixture issue)
3. **Infrastructure Issue** - Cluster/environment problem: pod failure, network, auth, resources, GPU, OOM, storage-initializer failure, Knative/Istio misconfiguration
4. **Intermittent Failure** - Flaky behavior, timing-dependent, passes on retry

### KServe/RHOAI Classification Guide
When the test involves model serving (KServe, LLMD, InferenceService):
- `"no matches for kind"` (e.g., LeaderWorkerSet, InferenceService) → **Product Bug** (CRD dependency missing)
- `"failed to reconcile"` + operator error → **Product Bug** (operator/controller broken)
- `"RevisionFailed"` + container crash → **Product Bug** (model runtime issue)
- `"storage-initializer failed"` → **Infrastructure Issue** (S3/storage credentials)
- `"IngressNotConfigured"` → **Infrastructure Issue** (Knative/Istio not ready)
- ISVC not ready + generous timeout + healthy cluster → **Product Bug** (product broken)
- ISVC not ready + unhealthy cluster → **Infrastructure Issue**

### Timeout Classification Guide
TimeoutExpiredError is a SYMPTOM. Classify based on WHY it timed out:
- Generous timeout (≥ 300s) + healthy cluster + consistent failure → **Product Bug**
- Generous timeout (≥ 300s) + test usually passes (high pass rate) → **Infrastructure Issue** (environment regressed)
- Short timeout (< 120s) for an operation needing more time → **Test Automation Issue**
- Timeout + unhealthy cluster/pods → **Infrastructure Issue**

### Setup Phase Failures (CRITICAL)
When error says "failed on setup with TimeoutExpiredError":
- The TEST CODE NEVER RAN — the failure is in environment/platform preparation
- `wait_for_condition` timing out means a K8s resource never became ready
- "Last exception: N/A" means the API was accessible but the condition was never met
- This is almost NEVER a Test Automation Issue
- Generous timeout (>=300s) on setup → **Infrastructure Issue** or **Product Bug**

IMPORTANT: "To Investigate" is NOT a valid option. Always commit to one category.
If uncertain, pick the most probable and lower your confidence accordingly.

Provide your analysis with:
- **Classification**: [Product Bug|Test Automation Issue|Infrastructure Issue|Intermittent Failure]
- **Root Cause**: [specific technical explanation]
- **Confidence**: [percentage based on evidence quality]
