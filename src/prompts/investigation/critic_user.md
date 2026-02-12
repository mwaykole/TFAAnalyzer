Review this RCA critically:

## Initial Analysis
${initial_rca}

## Additional Context
${context}

## CRITICAL: Check for Classification Errors

### Common Misclassifications (CHECK THESE FIRST):

1. **TimeoutSampler/wait timeout in TEST code → Should be Test Automation Issue**
   - If the error mentions "TimeoutExpiredError", "TimeoutSampler", "wait_timeout"
   - And it's the TEST waiting for something
   - This is NOT a Product Bug, it's Test Automation Issue (test wait too short)

2. **Network/connection errors → Should be Infrastructure Issue**
   - "upstream connect error", "connection refused", "503 Service Unavailable"
   - These are NOT Product Bugs, they're Infrastructure Issues

3. **Service mesh failures → Should be Infrastructure Issue**
   - "reset before headers", "connection termination"
   - Istio/Envoy routing issues are Infrastructure, not Product

### Critique Checklist

1. **Is the classification consistent with the root cause?**
   - If root cause says "test wait failed" but classification is "Product Bug" → WRONG
   - If root cause says "network error" but classification is "Product Bug" → WRONG

2. **Is there evidence confusion?**
   - Test timeout ≠ Product timeout
   - Test assertion error ≠ Product returned wrong value (unless product actually returned wrong value)

3. **Is confidence appropriate?**
   - Low evidence should mean lower confidence
   - Contradictory analysis should be flagged

## Your Response

If you find a misclassification, clearly state:
- What the current classification is
- What it SHOULD be
- Why (based on the evidence)

Be direct and specific about any errors.
