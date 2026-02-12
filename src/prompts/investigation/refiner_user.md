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

Read your ROOT_CAUSE carefully, then apply these rules STRICTLY:

| If Root Cause Contains... | Classification MUST Be |
|--------------------------|----------------------|
| "wait", "sampler", "timeout" in TEST code | Test Automation Issue |
| "TimeoutExpiredError", "TimeoutSampler" | Test Automation Issue |
| "assertion", "expected", "actual" mismatch | Test Automation Issue |
| "fixture", "setup", "teardown" failure | Test Automation Issue |
| Pod failure (OOM, CrashLoop, ImagePull) | Infrastructure Issue |
| Network error (connection refused/reset) | Infrastructure Issue |
| "upstream connect error", "503", "service mesh" | Infrastructure Issue |
| Authentication/credentials failure | Infrastructure Issue |
| GPU/CUDA error | Infrastructure Issue |
| Product API returned wrong value/behavior | Product Bug |
| Product code crash/exception | Product Bug |
| Feature regression | Product Bug |
| Passed on retry, flaky history | Intermittent Failure |

## VALIDATION CHECK

Before responding, verify:
1. Does your ROOT_CAUSE match your CLASSIFICATION according to the table above?
2. If ROOT_CAUSE mentions "test wait", "sampler", "timeout in test" → it CANNOT be Product Bug
3. If ROOT_CAUSE mentions "network", "connection", "upstream" → it should be Infrastructure Issue

## Output Format (EXACT)

CLASSIFICATION: [Product Bug|Test Automation Issue|Infrastructure Issue|Intermittent Failure]
CONFIDENCE: [number]%
SEVERITY: [LOW|MEDIUM|HIGH|CRITICAL]
ROOT_CAUSE: [One specific sentence - what actually failed and why]
REASONING: [1-2 sentences - why this classification fits the root cause]
RECOMMENDATION: [Specific actionable steps]

IMPORTANT: Your CLASSIFICATION must be consistent with your ROOT_CAUSE. Do not contradict yourself.
