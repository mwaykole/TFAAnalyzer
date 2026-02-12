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

## Classification Options
1. **Product Bug** - Defect in RHOAI/ODH component code
2. **Test Automation Issue** - Problem with test code, waits, or assertions
3. **Infrastructure Issue** - Cluster, network, resources, or environment problem
4. **Intermittent Failure** - Flaky behavior, timing-dependent, passes on retry

Provide your analysis with:
- **Classification**: [one of the above]
- **Root Cause**: [specific technical explanation]
- **Confidence**: [percentage based on evidence quality]
