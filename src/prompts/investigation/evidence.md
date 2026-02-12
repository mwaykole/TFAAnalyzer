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
${pre_error_context}${timeout_analysis}${systemic_issue}${kb_context}

## Analysis Task

Analyze this failure following these steps:

1. **Identify the Error**: What exception/error occurred?
2. **Find the Root Cause**: Why did this error happen?
3. **Classify Accurately**:
   - **Product Bug** - RHOAI/ODH component defect (API error, crash, wrong behavior)
   - **Test Automation Issue** - Test code problem (bad assertion, timeout too short, fixture issue)
   - **Infrastructure Issue** - Environment problem (pod failure, network, auth, resources)
   - **Intermittent Failure** - Flaky behavior (timing, race condition, passes on retry)

4. **Assess Confidence**: How certain are you based on the evidence?

Provide:
- Classification: [category]
- Root Cause: [specific explanation]
- Confidence: [percentage]
