## Classification Refinement

Review the initial classification and determine if it should be changed based on additional context.

### Initial Analysis
| Field | Value |
|-------|-------|
| Classification | ${classification} |
| Confidence | ${confidence} |
| Summary | ${summary} |

### Additional Indicators Found
${indicators}

### Refinement Checklist

1. **Does new evidence contradict the initial classification?**
   - If yes, what classification does the new evidence support?

2. **Does new evidence strengthen the initial classification?**
   - If yes, should confidence be increased?

3. **Are there any red flags suggesting misclassification?**
   - Timeout in test code classified as Infrastructure Issue?
   - Product error classified as Test Automation Issue?

### Decision

If the classification should change, provide updated JSON with:
- New classification
- Updated confidence
- Explanation of why it changed

If the classification is correct, confirm the original analysis with any confidence adjustments.
