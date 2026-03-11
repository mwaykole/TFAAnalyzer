${few_shot_section}
## Test Failure Analysis

### Failure Information
| Field | Value |
|-------|-------|
| Test | ${test_name} |
| Error Type | ${error_type} |
| Error Message | ${error_message} |
| Detected Patterns | ${patterns} |
| Test Decorators | ${decorators} |

### Stack Trace
${stack_trace}
${setup_failure_section}${test_code_section}${pre_error_context}${timeout_analysis}${systemic_issue}${kb_context}${must_gather_section}${verification_section}${code_analysis_section}${defect_section}${rule_hint_section}

## Analysis Task

Analyze this failure following these steps:

1. **Identify the Error**: What exception/error occurred?
2. **Find the Root Cause**: Why did this error happen? Be SPECIFIC:
   - If must-gather data is available, cite the exact pod/CR/operator that caused the failure
   - Trace the resource chain: InferenceService → Predictor → Pod → container error
   - Name the specific namespace/pod/container that was unhealthy and what its status was
   - If login/auth failures exist, state the specific authentication error
   - NEVER just say "degraded cluster" — explain WHAT was degraded and WHY it caused the timeout
3. **Classify into EXACTLY ONE of these four categories**:
   - **Product Bug** - RHOAI/ODH/KServe component defect: API error, crash, wrong behavior, feature regression, missing CRD dependency ("no matches for kind"), operator reconciliation failure, service consistently fails to become ready despite healthy cluster and generous timeout
   - **Test Automation Issue** - Test code problem (timeout too short for the operation, bad assertion, fixture issue, incorrect wait logic)
   - **Infrastructure Issue** - Environment problem: pod failure, network, auth, resources, GPU, OOM, unhealthy cluster, storage-initializer failure (S3 credentials), Knative/Istio misconfiguration
   - **Intermittent Failure** - Flaky behavior (timing, race condition, passes on retry, inconsistent history)

**KSERVE/RHOAI ROOT CAUSE ANALYSIS**: When analyzing model serving failures, trace the KServe resource chain:
- InferenceService/LLMInferenceService `.status.conditions` → actual error message
- ServingRuntime/ClusterServingRuntime → runtime configuration
- Predictor pod status → scheduling, container crashes, image pulls
- Must-gather resource_failures → CR-level error messages

**TIMEOUT CLASSIFICATION NUANCE**: TimeoutExpiredError is a SYMPTOM, not a root cause.
- If the timeout is SHORT (< 120s) for an operation that legitimately needs more time → Test Automation Issue
- If the timeout is GENEROUS (≥ 300s) AND the cluster is HEALTHY AND the service consistently fails → **Product Bug** (the product is broken, the test correctly detected it)
- If the timeout is GENEROUS (≥ 300s) AND the test usually passes (high pass rate) → **Infrastructure Issue** (the environment regressed, not the test's fault)
- If the timeout occurs because infrastructure is degraded → Infrastructure Issue
- If "failed on setup" + generous timeout → **Infrastructure Issue** (test code never ran; the platform wasn't ready)
- If `wait_for_condition` + "Last exception: N/A" → resource was accessible but never became ready → **Infrastructure or Product Bug**
- If CR `.status.conditions` shows `"no matches for kind"` or `"failed to reconcile"` → **Product Bug** (not a timeout issue, it's a missing dependency or controller error)

4. **Assess Confidence**: How certain are you based on the evidence?

CRITICAL: You MUST pick one of the four categories above. "To Investigate" is NOT a valid classification.
If uncertain, pick the most likely category and set confidence accordingly.

Provide:
- Classification: [Product Bug|Test Automation Issue|Infrastructure Issue|Intermittent Failure]
- Root Cause: [specific explanation — cite pod names, CR conditions, operator status, or error messages from must-gather/logs. If a resource timed out, explain WHAT prevented it from becoming ready]
- Confidence: [percentage]
