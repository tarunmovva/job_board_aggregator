"""
Enhanced Groq LLM Client for Job Data Extraction with LFU Model Rotation

This module provides an async-enabled client for extracting experience, skills, and summary
from job descriptions using the Groq API with LFU (Least Frequently Used) model rotation
for optimal performance and rate limit handling.
"""

import os
import asyncio
import aiohttp
import json
import time
import re
from typing import Dict, Any, Optional
from datetime import datetime

from job_board_aggregator.config import logger
from job_board_aggregator.util.groq_model_manager import get_model_manager
from job_board_aggregator.api.groq.models import CombinedJobData
from job_board_aggregator.api.groq.preprocessor import JobDescriptionPreprocessor
from job_board_aggregator.api.groq.prompts import PromptGenerator
from job_board_aggregator.api.groq.response_parser import ResponseParser


class JobExtractionError(Exception):
    """Custom exception for job extraction errors."""
    pass


class GroqJobEnhancer:
    """Enhanced Groq client with LFU model rotation for job data extraction."""
    
    def __init__(self):
        """Initialize the enhanced Groq job client with LFU model rotation."""
        self.model_manager = get_model_manager()
        self.preprocessor = JobDescriptionPreprocessor()
        self.prompt_generator = PromptGenerator()
        self.response_parser = ResponseParser()
        
        # API configuration
        self.api_key = os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.max_retries = int(os.getenv('GROQ_MAX_RETRIES', '3'))
        
        logger.info("Initialized GroqJobEnhancer with LFU model rotation")
    
    def _extract_rate_limit_headers(self, response_headers: dict) -> Dict[str, Any]:
        """Extract rate limit information from Groq API response headers."""
        headers = {}
        
        # Extract all rate limit headers provided by Groq
        rate_limit_mapping = {
            'x-ratelimit-limit-requests': 'limit_requests',
            'x-ratelimit-limit-tokens': 'limit_tokens', 
            'x-ratelimit-remaining-requests': 'remaining_requests',
            'x-ratelimit-remaining-tokens': 'remaining_tokens',
            'x-ratelimit-reset-requests': 'reset_requests',
            'x-ratelimit-reset-tokens': 'reset_tokens'
        }
        
        for header_name, key in rate_limit_mapping.items():
            if header_name in response_headers:
                value = response_headers[header_name]
                # Convert to int if it looks like a number
                if isinstance(value, str) and value.isdigit():
                    headers[key] = int(value)
                else:
                    headers[key] = value
        
        return headers
    
    def _should_wait_for_rate_limit(self, headers: Dict[str, Any]) -> tuple[bool, float]:
        """
        Check if we should wait based on rate limit headers.
        Returns (should_wait, wait_seconds)
        """
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
                
            logger.info(f"[JOB_LFU] Low token availability ({remaining_tokens} remaining), will wait {wait_seconds:.1f}s")
            return True, wait_seconds
        
        return False, 0
    
    async def extract_all_job_data(self, job_description: str, job_title: str = "") -> Dict[str, Any]:
        """
        Extract experience, skills, and summary from a job description using LFU model rotation.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing all extracted job data (experience, skills, summary)
        """
        if not job_description or not job_description.strip():
            return self._create_fallback_response(job_title)
        
        # Preprocess the job description
        processed_text = self.preprocessor.preprocess_job_description(job_description, job_title, extract_skills=False)
        if not processed_text.strip():
            return self._create_fallback_response(job_title)
        
        # Try extraction with model rotation
        try:
            logger.info(f"Starting job data extraction with LFU model rotation for: {job_title}")
            result = await self._try_extraction_with_rotation(processed_text, job_title)
            
            if result and hasattr(result, 'min_experience_years'):
                return result
        
        except Exception as e:
            logger.warning(f"Job data extraction with rotation failed: {e}")
        
        # Return fallback response if all attempts fail
        logger.info("All extraction attempts failed, returning fallback response")
        return self._create_fallback_response(job_title)
    
    async def _try_extraction_with_rotation(self, processed_text: str, job_title: str) -> Optional[Dict[str, Any]]:
        """
        Try job data extraction using LFU model rotation.
        
        Args:
            processed_text: Preprocessed job description text
            job_title: Job title for context
            
        Returns:
            Extraction result dict or None if all models failed
        """
        stats = self.model_manager.get_usage_stats()
        available_models = stats['available_models']
        
        if not available_models:
            logger.error("No models available for job data extraction")
            raise JobExtractionError("No models available")
        
        logger.info(f"[JOB_LFU] Starting extraction with {len(available_models)} available models")
        
        # Try each model in LFU order
        models_tried = []
        last_exception = None
        
        for attempt in range(len(available_models)):
            try:
                # Get next model from LFU manager
                selected_model = await self.model_manager.get_next_model()
                
                if selected_model in models_tried:
                    logger.warning(f"[JOB_LFU] Model {selected_model} already tried, skipping")
                    continue
                
                models_tried.append(selected_model)
                logger.info(f"[JOB_LFU] Attempt {attempt + 1}/{len(available_models)}: Trying model {selected_model}")
                
                # Try extraction with this model
                result = await self._try_single_extraction(processed_text, job_title, selected_model)
                
                if result and hasattr(result, 'min_experience_years'):
                    # Success - record usage and return
                    await self.model_manager.record_usage(selected_model, success=True)
                    
                    logger.info(f"[JOB_LFU] SUCCESS with model {selected_model} on attempt {attempt + 1}")
                    return result
                else:
                    # Failed - record failure
                    await self.model_manager.record_usage(selected_model, success=False)
                    logger.warning(f"[JOB_LFU] Model {selected_model} returned no valid result")
                    
            except Exception as e:
                # Record failure for this model
                if 'selected_model' in locals():
                    await self.model_manager.record_usage(selected_model, success=False)
                
                logger.warning(f"[JOB_LFU] Model {selected_model if 'selected_model' in locals() else 'unknown'} failed: {e}")
                last_exception = e
                
                # Continue to next model
                continue
        
        # All models failed
        logger.error(f"[JOB_LFU] All {len(models_tried)} models failed. Models tried: {models_tried}")
        
        if last_exception:
            raise last_exception
        else:
            raise JobExtractionError("All available models failed to extract job data")
    
    async def _try_single_extraction(self, processed_text: str, job_title: str, model_name: str) -> Optional['CombinedJobData']:
        """
        Try job data extraction with a specific model.
        
        Args:
            processed_text: Preprocessed job description text
            job_title: Job title for context
            model_name: Specific model to use
            
        Returns:
            Extraction result dict or None if failed
        """
        try:
            # Create combined extraction prompt
            prompt = self.prompt_generator.create_combined_extraction_prompt(processed_text, job_title)
            
            # Make async HTTP request with aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 1500,  # Increased for combined extraction
                "top_p": 0.9
            }
            
            # Use aiohttp for async HTTP request with rate limit handling
            timeout = aiohttp.ClientTimeout(total=30)
            max_retries_for_rate_limit = 3
            
            for retry_attempt in range(max_retries_for_rate_limit):
                try:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers=headers,
                            json=payload
                        ) as response:
                            # Handle rate limiting - IMMEDIATELY switch to next model instead of waiting
                            if response.status == 429:
                                # Extract retry-after time if available
                                retry_after = response.headers.get('retry-after', '60')
                                if retry_after.isdigit():
                                    retry_after_seconds = int(retry_after)
                                else:
                                    # Try to extract from rate limit headers
                                    rate_limit_headers = self._extract_rate_limit_headers(dict(response.headers))
                                    reset_tokens = rate_limit_headers.get('reset_tokens', '60s')
                                    if isinstance(reset_tokens, str):
                                        import re
                                        # Parse time string like "7.66s" or "2m59.56s"
                                        if 'm' in reset_tokens:
                                            match = re.match(r'(\d+)m([\d.]+)s', reset_tokens)
                                            if match:
                                                minutes = int(match.group(1))
                                                seconds = float(match.group(2))
                                                retry_after_seconds = minutes * 60 + seconds
                                            else:
                                                retry_after_seconds = 60
                                        else:
                                            match = re.match(r'([\d.]+)s', reset_tokens)
                                            if match:
                                                retry_after_seconds = float(match.group(1))
                                            else:
                                                retry_after_seconds = 60
                                    else:
                                        retry_after_seconds = 60
                                
                                # Mark model as rate limited instead of waiting
                                self.model_manager.mark_model_rate_limited(model_name, retry_after_seconds)
                                logger.warning(f"[JOB_LFU] Rate limit hit for model {model_name}. Marked as unavailable for {retry_after_seconds:.1f}s. Moving to next model.")
                                return None  # This will trigger model rotation to try next available model
                            
                            # For other HTTP errors, raise immediately
                            response.raise_for_status()
                            response_data = await response.json()
                            
                            # Success - break out of retry loop
                            break
                            
                except aiohttp.ClientResponseError as e:
                    if e.status == 429:
                        # Rate limit error - mark model as unavailable and move to next model
                        self.model_manager.mark_model_rate_limited(model_name, 60.0)  # Default 60s
                        logger.warning(f"[JOB_LFU] Rate limit error for model {model_name}. Marked as unavailable. Moving to next model.")
                        return None
                    else:
                        # For other HTTP errors, don't retry
                        logger.error(f"[JOB_LFU] HTTP error {e.status} for model {model_name}: {e}")
                        return None
                except Exception as e:
                    # For other errors, don't retry
                    logger.error(f"[JOB_LFU] Unexpected error for model {model_name}: {e}")
                    return None
            
            # Extract text from response
            if response_data and 'choices' in response_data:
                choices = response_data['choices']
                if choices and len(choices) > 0:
                    content = choices[0].get('message', {}).get('content', '')
                    
                    if content and content.strip():
                        logger.debug(f"Groq response content length: {len(content)}")
                        
                        # Parse the combined response
                        try:
                            combined_data = self.response_parser.parse_combined_response(response_data, job_title)
                            logger.info(f"Job data extraction successful with model {model_name}")
                            return combined_data  # Return the CombinedJobData object directly
                        
                        except Exception as parse_error:
                            logger.warning(f"Failed to parse response from model {model_name}: {parse_error}")
                            return None
                    else:
                        logger.warning(f"Empty content in response from model {model_name}")
                        return None
                else:
                    logger.warning(f"No choices in response from model {model_name}")
                    return None
            else:
                logger.warning(f"Invalid response structure from model {model_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error during job extraction with model {model_name}: {e}")
            raise
    
    def _create_fallback_response(self, job_title: str = "") -> 'CombinedJobData':
        """Create a fallback response when all extraction methods fail."""
        from job_board_aggregator.api.groq.models import CombinedJobData
        
        min_years, confidence = self.response_parser._infer_experience_from_title(job_title)
        
        return CombinedJobData(
            # Experience data
            min_experience_years=min_years,
            experience_type='minimum',
            experience_details=f'Experience inferred from job title: {job_title}' if job_title else 'No experience requirements found',
            experience_extracted=False,
            experience_confidence=confidence,
            
            # Skills data
            skills=[],
            skills_extracted=False,
            skills_confidence=0.0,
            
            # Summary data
            summary_points=[],
            summary_extracted=False,
            summary_confidence=0.0
        )


# Create a singleton instance for job extraction
job_enhancer = GroqJobEnhancer()


async def extract_all_job_data_async(job_description: str, job_title: str = "") -> 'CombinedJobData':
    """
    Convenience function to extract job data with LFU model rotation (async).
    
    Args:
        job_description: The job description text to analyze
        job_title: Optional job title for context
        
    Returns:
        Dictionary containing all extracted job data
    """
    return await job_enhancer.extract_all_job_data(job_description, job_title)


def extract_all_job_data_sync(job_description: str, job_title: str = "") -> 'CombinedJobData':
    """
    Synchronous wrapper for job data extraction with LFU model rotation.
    
    Args:
        job_description: The job description text to analyze
        job_title: Optional job title for context
        
    Returns:
        CombinedJobData containing all extracted job data
    """
    try:
        # Always create a new event loop for sync calls to avoid conflicts
        import asyncio
        
        # Create a new event loop and run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(extract_all_job_data_async(job_description, job_title))
            return result
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    
    except Exception as e:
        logger.error(f"Error in synchronous job data extraction: {e}")
        # Create a simple fallback response directly
        from job_board_aggregator.api.groq.models import CombinedJobData
        
        return CombinedJobData(
            # Experience data
            min_experience_years=0,
            experience_type='minimum',
            experience_details='Extraction failed',
            experience_extracted=False,
            experience_confidence=0.0,
            
            # Skills data
            skills=[],
            skills_extracted=False,
            skills_confidence=0.0,
            
            # Summary data
            summary_points=[],
            summary_extracted=False,
            summary_confidence=0.0
        )
