## Log Chunk Synthesis

You have analyzed multiple chunks of logs from a single test failure. Now synthesize these into a unified analysis.

### Test Information
| Field | Value |
|-------|-------|
| Name | ${test_name} |
| Type | ${test_type} |

### Individual Chunk Analyses
${chunk_analyses}

### Synthesis Instructions

1. **Identify Consistency**: Do the chunk analyses agree on the root cause?
2. **Resolve Conflicts**: If chunks suggest different causes, determine the primary one
3. **Combine Evidence**: Use evidence from all chunks to strengthen the analysis
4. **Adjust Confidence**: 
   - Higher if multiple chunks point to same cause
   - Lower if chunks are contradictory or inconclusive

Provide a single, unified analysis as a JSON object that represents the complete failure.
