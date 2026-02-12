## Test Failure Analysis Request

### Test Information
| Field | Value |
|-------|-------|
| Name | ${test_name} |
| Type | ${test_type} |
| Status | ${status} |
${attributes_section}

### Logs and Stack Trace
```
${logs}
```

${additional_context}

### Analysis Required

Please analyze this failure and provide:
1. **Summary**: Brief description of what failed
2. **Root Cause**: Technical explanation of why it failed
3. **Classification**: Category of failure
4. **Recommendation**: How to fix or investigate
5. **Confidence**: How certain you are (0.0-1.0)

Respond with a JSON object only.
