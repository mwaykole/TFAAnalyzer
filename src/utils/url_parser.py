"""URL parser utilities for extracting IDs from ReportPortal URLs.

Makes it easier for users to just paste the full URL instead of
manually extracting the launch ID.

Supported URL formats:
- https://reportportal.example.com/ui/#project/launches/all/9378
- https://rp.example.com/ui/#project-name/launches/all/9378
- https://rp.example.com/ui/#project/userdebug/all/9378/test-item/510078
- https://rp.example.com/ui/#project/launches/829/9355 (direct launch ID without 'all')
- Just the ID: 9378
"""

import re
from urllib.parse import urlparse
from typing import NamedTuple

from src.utils.logging import get_logger

logger = get_logger(__name__)


class ParsedRPUrl(NamedTuple):
    """Parsed ReportPortal URL components."""
    launch_id: str
    test_item_id: str | None = None
    project: str | None = None
    base_url: str | None = None


def extract_launch_id(input_str: str) -> str:
    """Extract launch ID from URL or return as-is if already an ID.
    
    Args:
        input_str: Either a full ReportPortal URL or a launch ID
        
    Returns:
        The extracted launch ID
        
    Examples:
        >>> extract_launch_id("9378")
        '9378'
        >>> extract_launch_id("https://rp.example.com/ui/#project/launches/all/9378")
        '9378'
        >>> extract_launch_id("https://rp.example.com/ui/#proj/userdebug/all/9378/test-item/510078")
        '9378'
    """
    if not input_str:
        return input_str
    
    input_str = input_str.strip()
    
    # If it's already just a number, return it
    if input_str.isdigit():
        return input_str
    
    # Try to parse as URL
    parsed = parse_rp_url(input_str)
    if parsed and parsed.launch_id:
        logger.info("extracted_launch_id_from_url",
                    input=input_str[:50],
                    launch_id=parsed.launch_id)
        return parsed.launch_id
    
    # Return original if we couldn't extract
    return input_str


def extract_test_item_id(input_str: str) -> str | None:
    """Extract test item ID from URL if present.
    
    Args:
        input_str: Either a full ReportPortal URL or a test item ID
        
    Returns:
        The extracted test item ID or None
    """
    if not input_str:
        return None
    
    input_str = input_str.strip()
    
    # If it's already just a number, return it
    if input_str.isdigit():
        return input_str
    
    # Try to parse as URL
    parsed = parse_rp_url(input_str)
    return parsed.test_item_id if parsed else None


def parse_rp_url(url: str) -> ParsedRPUrl | None:
    """Parse a ReportPortal URL into components.
    
    Handles various URL formats:
    - /ui/#project/launches/all/LAUNCH_ID
    - /ui/#project/launches/all/LAUNCH_ID/test-item/TEST_ITEM_ID
    - /ui/#project/launches/LAUNCH_ID/TEST_ITEM_ID (direct, no 'all')
    - /ui/#project/userdebug/all/LAUNCH_ID
    - /ui/#project/userdebug/all/LAUNCH_ID/test-item/TEST_ITEM_ID
    
    Args:
        url: Full ReportPortal URL
        
    Returns:
        ParsedRPUrl with extracted components or None if not a valid RP URL
    """
    if not url or not isinstance(url, str):
        return None
    
    url = url.strip()
    
    # Check if it looks like a URL
    if not url.startswith(('http://', 'https://')):
        # Maybe it's just the fragment part
        if '#' not in url and '/' not in url:
            return None
    
    try:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else None
        
        # Get the fragment (part after #)
        fragment = parsed.fragment
        if not fragment:
            # Try to find it in the path
            if '#' in url:
                fragment = url.split('#', 1)[1]
            else:
                return None
        
        # Parse the fragment path
        # Format: project/launches/all/LAUNCH_ID or project/launches/LAUNCH_ID/TEST_ITEM_ID
        parts = fragment.strip('/').split('/')
        
        if len(parts) < 3:
            return None
        
        project = parts[0]
        launch_id = None
        test_item_id = None
        
        # Find launch ID - it's the numeric value after "all" or similar
        for i, part in enumerate(parts):
            if part in ('all', 'latest') and i + 1 < len(parts):
                # Next part should be launch ID
                potential_id = parts[i + 1]
                if potential_id.isdigit():
                    launch_id = potential_id
                    
                    # Check for test-item ID
                    if i + 3 < len(parts) and parts[i + 2] == 'test-item':
                        potential_item_id = parts[i + 3]
                        if potential_item_id.isdigit():
                            test_item_id = potential_item_id
                    break
        
        # Alternative pattern: project/launches/LAUNCH_ID or project/launches/FILTER_ID/LAUNCH_ID
        # This handles URLs like: #opendatascience/launches/829/9355
        # Where 829 could be a filter ID and 9355 is the actual launch ID
        if not launch_id:
            for i, part in enumerate(parts):
                if part == 'launches' and i + 1 < len(parts):
                    next_part = parts[i + 1]
                    
                    # If next part is 'all' or 'latest', skip and look further
                    if next_part in ('all', 'latest') and i + 2 < len(parts):
                        if parts[i + 2].isdigit():
                            launch_id = parts[i + 2]
                            
                            # Check for test-item
                            if i + 4 < len(parts) and parts[i + 3] == 'test-item':
                                if parts[i + 4].isdigit():
                                    test_item_id = parts[i + 4]
                        break
                    
                    # If the next part is numeric
                    if next_part.isdigit():
                        # Check if there's another numeric part after this
                        # Pattern: launches/FILTER_ID/LAUNCH_ID (the LAST numeric ID is usually the launch)
                        if i + 2 < len(parts) and parts[i + 2].isdigit():
                            # Two numbers after launches - assume FILTER_ID/LAUNCH_ID
                            # The second number (9355) is the launch ID
                            launch_id = parts[i + 2]
                            # Note: in this case, parts[i+1] (829) is the filter ID, not test_item_id
                            logger.debug("url_pattern_filter_launch", 
                                        filter_id=next_part, 
                                        launch_id=launch_id)
                        else:
                            # Only one number - it's the launch ID
                            launch_id = next_part
                            
                            # Check for test-item after
                            if i + 2 < len(parts):
                                potential_item = parts[i + 2]
                                if potential_item == 'test-item' and i + 3 < len(parts):
                                    if parts[i + 3].isdigit():
                                        test_item_id = parts[i + 3]
                        break
                    break
        
        if not launch_id:
            return None
        
        logger.debug("parsed_rp_url", 
                     project=project, 
                     launch_id=launch_id, 
                     test_item_id=test_item_id)
        
        return ParsedRPUrl(
            launch_id=launch_id,
            test_item_id=test_item_id,
            project=project,
            base_url=base_url,
        )
        
    except Exception as e:
        logger.debug("url_parse_failed", url=url[:50], error=str(e))
        return None


def is_rp_url(input_str: str) -> bool:
    """Check if input looks like a ReportPortal URL.
    
    Args:
        input_str: Input string to check
        
    Returns:
        True if it looks like a RP URL
    """
    if not input_str:
        return False
    
    input_str = input_str.strip().lower()
    
    # Check for URL indicators
    if input_str.startswith(('http://', 'https://')):
        return 'reportportal' in input_str or '/ui/#' in input_str or '/launches/' in input_str
    
    return False
