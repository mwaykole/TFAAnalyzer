"""LLM prompt templates for test failure analysis."""

from string import Template

SYSTEM_PROMPT = """You are an expert software test failure analyst. Your task is to analyze test failures from automated test runs and provide structured analysis.

You will be given:
1. Test name and metadata
2. Test logs and stack traces
3. Optional: Test code or additional context

Your analysis must include:
- A brief summary of what failed
- Root cause analysis explaining why the failure occurred
- Classification of the failure type
- Recommended fix or investigation steps
- Confidence level in your analysis

## Classification Categories

You MUST classify each failure into exactly ONE of these categories:

1. **Application Bug**: A defect in the application code under test
   - Examples: Logic errors, null pointer exceptions, incorrect calculations
   
2. **Test Bug**: A defect in the test code itself
   - Examples: Incorrect assertions, wrong selectors, outdated test data
   
3. **Flaky**: Intermittent failure that may pass on retry
   - Examples: Race conditions, timing issues, order-dependent tests
   
4. **Environment**: Infrastructure or configuration issues
   - Examples: Service unavailable, connection timeouts, missing dependencies
   
5. **Data Issue**: Problems with test data or data state
   - Examples: Missing test data, stale data, database state issues

## Response Format

You MUST respond with valid JSON in this exact format:
{
    "summary": "Brief one-sentence description of the failure",
    "root_cause": "Detailed explanation of why the failure occurred",
    "classification": "One of: Application Bug, Test Bug, Flaky, Environment, Data Issue",
    "recommendation": "Specific actionable steps to fix or investigate",
    "confidence": 0.0 to 1.0
}

## Confidence Guidelines

- 0.9-1.0: Clear evidence in logs, definitive root cause
- 0.7-0.9: Strong indicators, likely root cause
- 0.5-0.7: Partial evidence, probable cause
- 0.3-0.5: Limited information, possible cause
- 0.0-0.3: Insufficient data, speculative

Respond ONLY with the JSON object, no additional text."""


ANALYSIS_PROMPT_TEMPLATE = Template("""Analyze this test failure:

## Test Information
- **Name**: ${test_name}
- **Type**: ${test_type}
- **Status**: ${status}
${attributes_section}

## Logs and Stack Trace
${logs}

${additional_context}

Provide your analysis as a JSON object.""")


CHUNK_ANALYSIS_PROMPT_TEMPLATE = Template("""Analyze this test failure. Note: The logs have been truncated to show the most relevant sections.

## Test Information
- **Name**: ${test_name}
- **Type**: ${test_type}
- **Status**: ${status}

## Log Excerpt (${chunk_info})
${logs}

Provide your analysis as a JSON object, noting any limitations due to truncated logs in your confidence score.""")


MULTI_CHUNK_SYNTHESIS_PROMPT = Template("""You have analyzed multiple chunks of logs from a single test failure. Synthesize your findings into a final analysis.

## Test Information
- **Name**: ${test_name}
- **Type**: ${test_type}

## Individual Chunk Analyses
${chunk_analyses}

Provide a unified analysis as a JSON object, considering all chunk analyses.""")


def format_attributes(attributes: list[dict[str, str]]) -> str:
    """Format test attributes for prompt inclusion."""
    if not attributes:
        return ""
    
    lines = ["- **Attributes**:"]
    for attr in attributes:
        key = attr.get("key", "")
        value = attr.get("value", "")
        if key and value:
            lines.append(f"  - {key}: {value}")
    return "\n".join(lines)


def build_analysis_prompt(
    test_name: str,
    test_type: str,
    status: str,
    logs: str,
    attributes: list[dict[str, str]] | None = None,
    additional_context: str | None = None,
) -> str:
    """Build the analysis prompt for a test failure.
    
    Args:
        test_name: Name of the test
        test_type: Type of test item (TEST, STEP, etc.)
        status: Test status
        logs: Log content
        attributes: Optional test attributes
        additional_context: Optional additional context
        
    Returns:
        Formatted prompt string
    """
    attributes_section = format_attributes(attributes or [])
    context_section = ""
    if additional_context:
        context_section = f"\n## Additional Context\n{additional_context}"
    
    return ANALYSIS_PROMPT_TEMPLATE.substitute(
        test_name=test_name,
        test_type=test_type,
        status=status,
        attributes_section=attributes_section,
        logs=logs,
        additional_context=context_section,
    )


def build_chunk_analysis_prompt(
    test_name: str,
    test_type: str,
    status: str,
    logs: str,
    chunk_index: int,
    total_chunks: int,
) -> str:
    """Build prompt for analyzing a single log chunk.
    
    Args:
        test_name: Name of the test
        test_type: Type of test item
        status: Test status
        logs: Log chunk content
        chunk_index: Current chunk index (0-based)
        total_chunks: Total number of chunks
        
    Returns:
        Formatted prompt string
    """
    chunk_info = f"Chunk {chunk_index + 1} of {total_chunks}"
    
    return CHUNK_ANALYSIS_PROMPT_TEMPLATE.substitute(
        test_name=test_name,
        test_type=test_type,
        status=status,
        chunk_info=chunk_info,
        logs=logs,
    )


def build_synthesis_prompt(
    test_name: str,
    test_type: str,
    chunk_analyses: list[dict],
) -> str:
    """Build prompt for synthesizing multiple chunk analyses.
    
    Args:
        test_name: Name of the test
        test_type: Type of test item
        chunk_analyses: List of analysis results from individual chunks
        
    Returns:
        Formatted prompt string
    """
    analyses_text = ""
    for i, analysis in enumerate(chunk_analyses):
        analyses_text += f"\n### Chunk {i + 1} Analysis\n"
        analyses_text += f"- Summary: {analysis.get('summary', 'N/A')}\n"
        analyses_text += f"- Root Cause: {analysis.get('root_cause', 'N/A')}\n"
        analyses_text += f"- Classification: {analysis.get('classification', 'N/A')}\n"
        analyses_text += f"- Confidence: {analysis.get('confidence', 0)}\n"
    
    return MULTI_CHUNK_SYNTHESIS_PROMPT.substitute(
        test_name=test_name,
        test_type=test_type,
        chunk_analyses=analyses_text,
    )


CLASSIFICATION_REFINEMENT_PROMPT = Template("""Review this initial classification and refine if needed based on additional context:

## Initial Analysis
- Classification: ${classification}
- Confidence: ${confidence}
- Summary: ${summary}

## Additional Indicators
${indicators}

If the classification should change, provide updated JSON. Otherwise, confirm the original analysis.""")


def build_refinement_prompt(
    classification: str,
    confidence: float,
    summary: str,
    indicators: list[str],
) -> str:
    """Build prompt for refining a classification.
    
    Args:
        classification: Initial classification
        confidence: Initial confidence score
        summary: Initial summary
        indicators: Additional indicators found
        
    Returns:
        Formatted prompt string
    """
    indicators_text = "\n".join(f"- {ind}" for ind in indicators)
    
    return CLASSIFICATION_REFINEMENT_PROMPT.substitute(
        classification=classification,
        confidence=confidence,
        summary=summary,
        indicators=indicators_text,
    )

