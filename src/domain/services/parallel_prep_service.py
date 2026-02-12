"""Parallel data preparation service for investigation workflow.

This service optimizes the investigation process by parallelizing I/O operations
(code fetching, verification) while keeping LLM calls sequential.

Key optimizations:
1. Pre-fetch all test code in parallel (builds index once, cache hits for rest)
2. Pre-run all verifications in parallel
3. Prepare all data upfront before sequential LLM processing
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.domain.interfaces.code_fetcher import CodeFetcher, TestCodeInfo
from src.domain.services.verification_service import (
    VerificationService,
    VerificationResult,
    VerifyMode,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PreparedFailureData:
    """All data needed for LLM investigation, pre-fetched."""
    
    test_name: str
    test_id: str
    logs: str
    signature: str
    group_size: int = 1
    
    # Pre-fetched data
    test_code: str = ""
    test_code_info: TestCodeInfo | None = None
    verification_result: str = "not_run"
    verification_output: str = ""
    verification_details: dict[str, Any] = field(default_factory=dict)
    history_data: dict[str, Any] = field(default_factory=dict)
    
    # Status tracking
    code_fetch_error: str = ""
    verification_error: str = ""


@dataclass
class ParallelPrepStats:
    """Statistics from parallel preparation."""
    
    total_failures: int = 0
    unique_signatures: int = 0
    code_fetched: int = 0
    code_cached: int = 0
    code_errors: int = 0
    verifications_run: int = 0
    verification_errors: int = 0
    prep_time_ms: int = 0


class ParallelPrepService:
    """Service for parallel data preparation before LLM investigation.
    
    Optimizes investigation workflow by:
    1. Building code index once (single API call)
    2. Fetching all test code in parallel (cache hits after first batch)
    3. Running all verifications in parallel
    4. Returning all data ready for sequential LLM processing
    """
    
    def __init__(
        self,
        code_fetcher: CodeFetcher | None = None,
        verification_service: VerificationService | None = None,
        history_fetcher: Any | None = None,
        max_concurrent_io: int = 10,
    ):
        """Initialize parallel preparation service.
        
        Args:
            code_fetcher: Code fetcher for getting test source
            verification_service: Service for test verification
            history_fetcher: Fetcher for test history from ReportPortal
            max_concurrent_io: Maximum concurrent I/O operations
        """
        self._code_fetcher = code_fetcher
        self._verification_service = verification_service
        self._history_fetcher = history_fetcher
        self._semaphore = asyncio.Semaphore(max_concurrent_io)
        self._stats = ParallelPrepStats()
    
    async def prepare_all(
        self,
        signature_groups: dict[str, list],
        verify_mode: VerifyMode = VerifyMode.NONE,
        fallback_code_getter: Any = None,
    ) -> tuple[list[PreparedFailureData], ParallelPrepStats]:
        """Prepare all failure data in parallel.
        
        This is the main entry point. It:
        1. Builds code index (if code_fetcher available)
        2. Fetches all test code in parallel
        3. Runs all verifications in parallel
        4. Returns prepared data ready for sequential LLM processing
        
        Args:
            signature_groups: Dict of error_signature -> list of failures
            verify_mode: Verification mode to use
            fallback_code_getter: Optional fallback function for code fetching
            
        Returns:
            Tuple of (prepared_data_list, stats)
        """
        import time
        start_time = time.time()
        
        self._stats = ParallelPrepStats(
            total_failures=sum(len(g) for g in signature_groups.values()),
            unique_signatures=len(signature_groups),
        )
        
        logger.info(
            "parallel_prep_starting",
            total_failures=self._stats.total_failures,
            unique_signatures=self._stats.unique_signatures,
        )
        
        # Phase 1: Build code index once (if available)
        if self._code_fetcher:
            try:
                await self._code_fetcher.build_index()
                logger.info("code_index_built")
            except Exception as e:
                logger.warning("code_index_build_failed", error=str(e))
        
        # Phase 2: Prepare all failure data in parallel
        tasks = []
        for sig, group in signature_groups.items():
            first_failure = group[0]
            task = self._prepare_one(
                failure=first_failure,
                signature=sig,
                group_size=len(group),
                verify_mode=verify_mode,
                fallback_code_getter=fallback_code_getter,
            )
            tasks.append(task)
        
        prepared_data = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        results = []
        for i, data in enumerate(prepared_data):
            if isinstance(data, Exception):
                sig = list(signature_groups.keys())[i]
                logger.error("prep_failed", signature=sig[:12], error=str(data))
            else:
                results.append(data)
        
        self._stats.prep_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "parallel_prep_complete",
            prepared=len(results),
            code_fetched=self._stats.code_fetched,
            code_cached=self._stats.code_cached,
            verifications=self._stats.verifications_run,
            time_ms=self._stats.prep_time_ms,
        )
        
        return results, self._stats
    
    async def _prepare_one(
        self,
        failure: Any,
        signature: str,
        group_size: int,
        verify_mode: VerifyMode,
        fallback_code_getter: Any = None,
    ) -> PreparedFailureData:
        """Prepare data for a single failure group.
        
        Runs code fetch and verification in parallel for this failure.
        """
        async with self._semaphore:
            test_name = failure.test_item.name or "unknown"
            test_id = str(failure.test_item.id)
            logs = failure.combined_logs
            
            # Create prepared data container
            data = PreparedFailureData(
                test_name=test_name,
                test_id=test_id,
                logs=logs,
                signature=signature,
                group_size=group_size,
            )
            
            # Run code fetch and verification in parallel
            code_task = self._fetch_code(test_name, fallback_code_getter)
            verification_task = self._run_verification(
                test_name=test_name,
                logs=logs,
                verify_mode=verify_mode,
            )
            
            code_result, verification_result = await asyncio.gather(
                code_task,
                verification_task,
                return_exceptions=True,
            )
            
            # Process code result
            if isinstance(code_result, Exception):
                data.code_fetch_error = str(code_result)
                self._stats.code_errors += 1
            elif code_result:
                data.test_code_info = code_result
                data.test_code = code_result.source_code
                self._stats.code_fetched += 1
            
            # Process verification result
            if isinstance(verification_result, Exception):
                data.verification_error = str(verification_result)
                self._stats.verification_errors += 1
            elif verification_result:
                v_result = verification_result
                data.verification_result = v_result.status
                data.verification_output = v_result.output
                data.verification_details = v_result.to_dict()
                data.history_data = v_result.details.get("history", {}) if hasattr(v_result, 'details') else {}
                self._stats.verifications_run += 1
            
            return data
    
    async def _fetch_code(
        self,
        test_name: str,
        fallback_getter: Any = None,
    ) -> TestCodeInfo | None:
        """Fetch test code with caching awareness."""
        if not self._code_fetcher:
            if fallback_getter:
                try:
                    code = fallback_getter(test_name)
                    if code:
                        return TestCodeInfo(
                            test_name=test_name,
                            file_path="",
                            function_name=test_name,
                            source_code=code,
                        )
                except Exception as e:
                    logger.debug("fallback_code_getter_failed", error=str(e))
            return None
        
        try:
            result = await self._code_fetcher.fetch_test_code(test_name)
            return result
        except Exception as e:
            logger.debug("code_fetch_failed", test=test_name[:50], error=str(e))
            if fallback_getter:
                try:
                    code = fallback_getter(test_name)
                    if code:
                        return TestCodeInfo(
                            test_name=test_name,
                            file_path="",
                            function_name=test_name,
                            source_code=code,
                        )
                except Exception:
                    pass
            return None
    
    async def _run_verification(
        self,
        test_name: str,
        logs: str,
        verify_mode: VerifyMode,
    ) -> VerificationResult | None:
        """Run verification for a test."""
        if verify_mode == VerifyMode.NONE or not self._verification_service:
            return None
        
        # Get test code for verification (will be available from parallel fetch)
        test_code = ""
        
        # Get history data if needed for analyze-history mode
        history_data = {}
        if verify_mode in (VerifyMode.ANALYZE_HISTORY, VerifyMode.ALL):
            if self._history_fetcher:
                try:
                    history_obj = await self._history_fetcher.get_test_history(test_name)
                    history_data = history_obj.to_dict()
                except Exception as e:
                    logger.debug("history_fetch_failed", test=test_name[:50], error=str(e))
        
        try:
            result = await self._verification_service.verify(
                test_name=test_name,
                mode=verify_mode,
                logs=logs,
                test_code=test_code,
                history=history_data,
            )
            return result
        except Exception as e:
            logger.debug("verification_failed", test=test_name[:50], error=str(e))
            return None
