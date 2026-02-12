"""LLM prompt templates for test failure analysis.

This module provides backward-compatible access to prompts while using
the new file-based prompt system under the hood.
"""

from src.prompts.loader import get_prompt_loader

_loader = get_prompt_loader()


def _load_prompt(path: str) -> str:
    """Load a prompt from file."""
    return _loader.load(path)


SYSTEM_PROMPT = _load_prompt("system/analysis_system.md")


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
    
    return _loader.render(
        "analysis/failure_analysis.md",
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
    
    return _loader.render(
        "analysis/chunk_analysis.md",
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
    
    return _loader.render(
        "analysis/synthesis.md",
        test_name=test_name,
        test_type=test_type,
        chunk_analyses=analyses_text,
    )


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
    
    return _loader.render(
        "classification/refinement.md",
        classification=classification,
        confidence=confidence,
        summary=summary,
        indicators=indicators_text,
    )


def get_rhoai_context() -> str:
    """Get RHOAI/ODH domain knowledge context."""
    return _load_prompt("context/rhoai_knowledge.md")


def get_compact_system_prompt() -> str:
    """Get compact system prompt for token reduction."""
    return _load_prompt("system/compact_system.md")


def build_thinker_prompt(
    test_name: str,
    error_type: str,
    error_message: str,
    patterns: str,
    stack_trace: str,
    decorators: str,
    rhoai_context: str = "",
) -> tuple[str, str]:
    """Build thinker system and user prompts.
    
    Args:
        test_name: Name of the test
        error_type: Type of error
        error_message: Error message content
        patterns: Detected patterns
        stack_trace: Stack trace content
        decorators: Test decorators
        rhoai_context: Optional RHOAI context
        
    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    if not rhoai_context:
        rhoai_context = get_rhoai_context()
    
    system_prompt = _loader.render(
        "investigation/thinker_system.md",
        rhoai_context=rhoai_context,
    )
    
    user_prompt = _loader.render(
        "investigation/thinker_user.md",
        test_name=test_name,
        error_type=error_type,
        error_message=error_message,
        patterns=patterns,
        stack_trace=stack_trace,
        decorators=decorators,
    )
    
    return system_prompt, user_prompt


def build_critic_prompt(
    initial_rca: str,
    context: str,
) -> tuple[str, str]:
    """Build critic system and user prompts.
    
    Args:
        initial_rca: Initial RCA from thinker
        context: Additional context
        
    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    system_prompt = _load_prompt("investigation/critic_system.md")
    
    user_prompt = _loader.render(
        "investigation/critic_user.md",
        initial_rca=initial_rca,
        context=context,
    )
    
    return system_prompt, user_prompt


def build_refiner_prompt(
    initial_rca: str,
    critique: str,
    error_message: str,
    patterns: str,
    suggested_confidence: str,
) -> tuple[str, str]:
    """Build refiner system and user prompts.
    
    Args:
        initial_rca: Initial RCA from thinker
        critique: Critique from critic
        error_message: Error message
        patterns: Detected patterns
        suggested_confidence: Suggested confidence percentage
        
    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    system_prompt = _load_prompt("investigation/refiner_system.md")
    
    user_prompt = _loader.render(
        "investigation/refiner_user.md",
        initial_rca=initial_rca,
        critique=critique,
        error_message=error_message,
        patterns=patterns,
        suggested_confidence=suggested_confidence,
    )
    
    return system_prompt, user_prompt
