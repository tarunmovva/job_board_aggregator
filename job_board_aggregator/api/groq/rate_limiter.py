"""
Rate limiting functionality for the Groq API.
"""

import time
import logging
import re
from typing import Dict, Tuple, Union
import requests

logger = logging.getLogger(__name__)


class RateLimiter:
    """Handles rate limiting for Groq API requests."""
    
    def __init__(self):
        """Initialize rate limiter with tracking variables."""
        self.last_rate_limit_headers = {}
    
    def extract_rate_limit_headers(self, response: requests.Response) -> Dict[str, Union[int, str]]:
        """Extract rate limit information from Groq API response headers."""
        headers = {}
        
        # Extract all rate limit headers provided by Groq
        rate_limit_headers = {
            'x-ratelimit-limit-requests': 'limit_requests',
            'x-ratelimit-limit-tokens': 'limit_tokens', 
            'x-ratelimit-remaining-requests': 'remaining_requests',
            'x-ratelimit-remaining-tokens': 'remaining_tokens',
            'x-ratelimit-reset-requests': 'reset_requests',
            'x-ratelimit-reset-tokens': 'reset_tokens',
            'retry-after': 'retry_after'
        }
        
        for header_name, key in rate_limit_headers.items():
            if header_name in response.headers:
                value = response.headers[header_name]
                # Convert numeric values to int, keep time strings as is
                if header_name in ['retry-after', 'x-ratelimit-limit-requests', 'x-ratelimit-limit-tokens', 
                                   'x-ratelimit-remaining-requests', 'x-ratelimit-remaining-tokens']:
                    try:
                        headers[key] = int(value)
                    except ValueError:
                        headers[key] = value
                else:
                    headers[key] = value
        
        return headers
    
    def should_wait_for_rate_limit(self, headers: Dict[str, Union[int, str]]) -> Tuple[bool, float]:
        """
        Check if we should wait based on rate limit headers.
        Returns (should_wait, wait_seconds)
        """
        # Check remaining requests (RPD - Requests Per Day)
        remaining_requests = headers.get('remaining_requests', 1)
        if isinstance(remaining_requests, int) and remaining_requests <= 1:
            logger.warning(f"Low remaining daily requests: {remaining_requests}")
            # Don't wait for daily limit, just log warning
        
        # Check remaining tokens (TPM - Tokens Per Minute) - this is more critical
        remaining_tokens = headers.get('remaining_tokens', 1000)
        if isinstance(remaining_tokens, int) and remaining_tokens < 500:  # Conservative threshold
            # Parse reset time for tokens (should be in seconds)
            reset_tokens = headers.get('reset_tokens', '60s')
            if isinstance(reset_tokens, str):
                # Parse time string like "7.66s" or "2m59.56s"
                if 'm' in reset_tokens:
                    # Format like "2m59.56s"
                    match = re.match(r'(\d+)m([\d.]+)s', reset_tokens)
                    if match:
                        minutes = int(match.group(1))
                        seconds = float(match.group(2))
                        wait_seconds = minutes * 60 + seconds + 1  # Add buffer
                    else:
                        wait_seconds = 60  # Default fallback
                else:
                    # Format like "7.66s"
                    match = re.match(r'([\d.]+)s', reset_tokens)
                    if match:
                        wait_seconds = float(match.group(1)) + 1  # Add buffer
                    else:
                        wait_seconds = 60  # Default fallback
            else:
                wait_seconds = 60  # Default fallback
                
            logger.info(f"Low token availability ({remaining_tokens} remaining), will wait {wait_seconds:.1f}s")
            return True, wait_seconds
        
        return False, 0
    
    def handle_rate_limit_wait(self, headers: Dict[str, Union[int, str]]) -> None:
        """Handle waiting for rate limits based on headers."""
        should_wait, wait_seconds = self.should_wait_for_rate_limit(headers)
        if should_wait:
            logger.info(f"Rate limit triggered, waiting {wait_seconds:.1f} seconds...")
            time.sleep(wait_seconds)
