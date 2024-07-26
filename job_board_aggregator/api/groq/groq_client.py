"""
Main Groq LLM Client for Experience and Skills Extraction

This module provides the main client interface for extracting minimum experience 
requirements and skills from job descriptions using the Groq API.
"""

import time
import logging
from typing import Dict

import requests

from job_board_aggregator.api.groq.models import ExperienceData, SkillsData, JobSummaryData, CombinedJobData
from job_board_aggregator.api.groq.rate_limiter import RateLimiter
from job_board_aggregator.api.groq.preprocessor import JobDescriptionPreprocessor
from job_board_aggregator.api.groq.prompts import PromptGenerator
from job_board_aggregator.api.groq.api_client import GroqAPIClient
from job_board_aggregator.api.groq.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class GroqLLMClient:
    """
    Main client for extracting experience requirements and skills from job descriptions using Groq API.
    Implements proper rate limiting to ensure we stay within API limits.
    """    
    
    def __init__(self):
        """Initialize Groq client with all components."""
        # Initialize components
        self.rate_limiter = RateLimiter()
        self.preprocessor = JobDescriptionPreprocessor()
        self.prompt_generator = PromptGenerator()
        self.api_client = GroqAPIClient()
        self.response_parser = ResponseParser()
        
        logger.info(f"Initialized GroqLLMClient with model {self.api_client.model} using header-based rate limiting")
    
    def extract_experience(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract experience requirements from a job description.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing extracted experience data
        """
        # Preprocess the job description
        processed_text = self.preprocessor.preprocess_job_description(job_description, job_title)
        if not processed_text.strip():
            return self._create_fallback_response(job_title)
        
        # Create extraction prompt
        prompt = self.prompt_generator.create_extraction_prompt(processed_text, job_title)
        
        # Try extraction with retries
        for attempt in range(self.api_client.max_retries):
            try:
                # Check rate limits before making request
                if self.rate_limiter.last_rate_limit_headers:
                    self.rate_limiter.handle_rate_limit_wait(self.rate_limiter.last_rate_limit_headers)
                
                # Make API request
                response_data, http_response = self.api_client.make_api_request(prompt)
                
                # Extract and store rate limit headers
                rate_limit_headers = self.rate_limiter.extract_rate_limit_headers(http_response)
                self.rate_limiter.last_rate_limit_headers = rate_limit_headers
                
                # Log rate limit info
                if rate_limit_headers:
                    remaining_requests = rate_limit_headers.get('remaining_requests', 'N/A')
                    remaining_tokens = rate_limit_headers.get('remaining_tokens', 'N/A')
                    logger.debug(f"Rate limits - Requests remaining: {remaining_requests}, Tokens remaining: {remaining_tokens}")
                
                # Parse response
                experience_data = self.response_parser.parse_groq_response(response_data, job_title)
                
                # Convert to dict and return
                return experience_data.__dict__
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit hit
                    logger.warning(f"Rate limit hit on experience extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        # Use retry-after header if available
                        if hasattr(e.response, 'headers') and 'retry-after' in e.response.headers:
                            retry_after = int(e.response.headers['retry-after'])
                            logger.info(f"Using retry-after header: waiting {retry_after}s")
                            time.sleep(retry_after + 1)  # Add 1 second buffer
                        else:
                            # Fallback to default wait
                            time.sleep(60)
                        continue
                    else:
                        logger.error("Rate limit hit on final experience extraction attempt, using fallback")
                        return self._create_fallback_response(job_title)
                else:
                    logger.warning(f"HTTP error on experience extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        continue
                    else:
                        return self._create_fallback_response(job_title)
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"Experience extraction API request failed on attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_fallback_response(job_title)
                    
            except Exception as e:
                logger.error(f"Unexpected error on experience extraction attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_fallback_response(job_title)
        
        # If all attempts failed
        logger.error(f"All experience extraction attempts failed")
        return self._create_fallback_response(job_title)

    def extract_skills(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract skills from a job description.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing extracted skills data
        """
        # Preprocess the job description for skills extraction
        processed_text = self.preprocessor.preprocess_job_description(job_description, job_title, extract_skills=True)
        if not processed_text.strip():
            return self._create_failed_skills_response("Empty processed text", job_title)
        
        # Create skills extraction prompt
        prompt = self.prompt_generator.create_skills_extraction_prompt(processed_text, job_title)
        
        # Try extraction with retries
        for attempt in range(self.api_client.max_retries):
            try:
                # Check rate limits before making request
                if self.rate_limiter.last_rate_limit_headers:
                    self.rate_limiter.handle_rate_limit_wait(self.rate_limiter.last_rate_limit_headers)
                
                # Make API request
                response_data, http_response = self.api_client.make_api_request(prompt)
                
                # Extract and store rate limit headers
                rate_limit_headers = self.rate_limiter.extract_rate_limit_headers(http_response)
                self.rate_limiter.last_rate_limit_headers = rate_limit_headers
                
                # Log rate limit info
                if rate_limit_headers:
                    remaining_requests = rate_limit_headers.get('remaining_requests', 'N/A')
                    remaining_tokens = rate_limit_headers.get('remaining_tokens', 'N/A')
                    logger.debug(f"Rate limits - Requests remaining: {remaining_requests}, Tokens remaining: {remaining_tokens}")
                
                # Parse response
                skills_data = self.response_parser.parse_skills_response(response_data, job_title)
                
                # Convert to dict and return
                return skills_data.__dict__
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit hit
                    logger.warning(f"Rate limit hit on skills extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        # Use retry-after header if available
                        if hasattr(e.response, 'headers') and 'retry-after' in e.response.headers:
                            retry_after = int(e.response.headers['retry-after'])
                            logger.info(f"Using retry-after header: waiting {retry_after}s")
                            time.sleep(retry_after + 1)  # Add 1 second buffer
                        else:
                            # Fallback to default wait
                            time.sleep(60)
                        continue
                    else:
                        logger.error("Rate limit hit on final skills extraction attempt, using fallback")
                        return self._create_failed_skills_response("Rate limit exceeded", job_title)
                else:
                    logger.warning(f"HTTP error on skills extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        continue
                    else:
                        return self._create_failed_skills_response(f"HTTP error: {e}", job_title)
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"Skills extraction API request failed on attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_failed_skills_response(f"Request error: {e}", job_title)
                    
            except Exception as e:
                logger.error(f"Unexpected error on skills extraction attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:                    return self._create_failed_skills_response(f"Unexpected error: {e}", job_title)
        
        # If all attempts failed
        logger.error(f"All skills extraction attempts failed")
        return self._create_failed_skills_response("All attempts failed", job_title)

    def extract_job_summary(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract a 5-point job summary from a job description.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing extracted job summary data
        """
        # Preprocess the job description for summary extraction
        processed_text = self.preprocessor.preprocess_job_description(job_description, job_title, extract_skills=False)
        if not processed_text.strip():
            return self._create_failed_summary_response("Empty processed text", job_title)
        
        # Create job summary extraction prompt
        prompt = self.prompt_generator.create_job_summary_prompt(processed_text, job_title)
        
        # Try extraction with retries
        for attempt in range(self.api_client.max_retries):
            try:
                # Check rate limits before making request
                if self.rate_limiter.last_rate_limit_headers:
                    self.rate_limiter.handle_rate_limit_wait(self.rate_limiter.last_rate_limit_headers)
                
                # Make API request
                response_data, http_response = self.api_client.make_api_request(prompt)
                
                # Extract and store rate limit headers
                rate_limit_headers = self.rate_limiter.extract_rate_limit_headers(http_response)
                self.rate_limiter.last_rate_limit_headers = rate_limit_headers
                
                # Log rate limit info
                if rate_limit_headers:
                    remaining_requests = rate_limit_headers.get('remaining_requests', 'N/A')
                    remaining_tokens = rate_limit_headers.get('remaining_tokens', 'N/A')
                    logger.debug(f"Rate limits - Requests remaining: {remaining_requests}, Tokens remaining: {remaining_tokens}")
                
                # Parse response
                summary_data = self.response_parser.parse_summary_response(response_data, job_title)
                
                # Convert to dict and return
                return summary_data.__dict__
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit hit
                    logger.warning(f"Rate limit hit on job summary extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        # Use retry-after header if available
                        if hasattr(e.response, 'headers') and 'retry-after' in e.response.headers:
                            retry_after = int(e.response.headers['retry-after'])
                            logger.info(f"Using retry-after header: waiting {retry_after}s")
                            time.sleep(retry_after + 1)  # Add 1 second buffer
                        else:
                            # Fallback to default wait
                            time.sleep(60)
                        continue
                    else:
                        logger.error("Rate limit hit on final job summary extraction attempt, using fallback")
                        return self._create_failed_summary_response("Rate limit exceeded", job_title)
                else:
                    logger.warning(f"HTTP error on job summary extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        continue
                    else:
                        return self._create_failed_summary_response(f"HTTP error: {e}", job_title)
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"Job summary extraction API request failed on attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_failed_summary_response(f"Request error: {e}", job_title)
                    
            except Exception as e:
                logger.error(f"Unexpected error on job summary extraction attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_failed_summary_response(f"Unexpected error: {e}", job_title)
        
        # If all attempts failed
        logger.error(f"All job summary extraction attempts failed")
        return self._create_failed_summary_response("All attempts failed", job_title)

    def extract_all_job_data(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract experience, skills, and summary from a job description in a single API call.
        
        This method combines all three extractions into one API request, reducing costs 
        and processing time by ~66%.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing all extracted job data (experience, skills, summary)
        """
        # Preprocess the job description once for all extractions
        processed_text = self.preprocessor.preprocess_job_description(job_description, job_title, extract_skills=False)
        if not processed_text.strip():
            return self._create_failed_combined_response("Empty processed text", job_title)
        
        # Create combined extraction prompt
        prompt = self.prompt_generator.create_combined_extraction_prompt(processed_text, job_title)
        
        # Try extraction with retries
        for attempt in range(self.api_client.max_retries):
            try:
                # Check rate limits before making request
                if self.rate_limiter.last_rate_limit_headers:
                    self.rate_limiter.handle_rate_limit_wait(self.rate_limiter.last_rate_limit_headers)
                
                # Make API request
                response_data, http_response = self.api_client.make_api_request(prompt)
                
                # Extract and store rate limit headers
                rate_limit_headers = self.rate_limiter.extract_rate_limit_headers(http_response)
                self.rate_limiter.last_rate_limit_headers = rate_limit_headers
                
                # Log rate limit info
                if rate_limit_headers:
                    remaining_requests = rate_limit_headers.get('remaining_requests', 'N/A')
                    remaining_tokens = rate_limit_headers.get('remaining_tokens', 'N/A')
                    logger.debug(f"Rate limits - Requests remaining: {remaining_requests}, Tokens remaining: {remaining_tokens}")
                
                # Parse combined response
                combined_data = self.response_parser.parse_combined_response(response_data, job_title)
                
                # Convert to dict and return
                return combined_data.__dict__
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit hit
                    logger.warning(f"Rate limit hit on combined extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        # Use retry-after header if available
                        if hasattr(e.response, 'headers') and 'retry-after' in e.response.headers:
                            retry_after = int(e.response.headers['retry-after'])
                            logger.info(f"Using retry-after header: waiting {retry_after}s")
                            time.sleep(retry_after + 1)  # Add 1 second buffer
                        else:
                            # Fallback to default wait
                            time.sleep(60)
                        continue
                    else:
                        logger.error("Rate limit hit on final combined extraction attempt, using fallback")
                        return self._create_failed_combined_response("Rate limit exceeded", job_title)
                else:
                    logger.warning(f"HTTP error on combined extraction attempt {attempt + 1}: {e}")
                    if attempt < self.api_client.max_retries - 1:
                        continue
                    else:
                        return self._create_failed_combined_response(f"HTTP error: {e}", job_title)
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"Combined extraction API request failed on attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_failed_combined_response(f"Request error: {e}", job_title)
                    
            except Exception as e:
                logger.error(f"Unexpected error on combined extraction attempt {attempt + 1}: {e}")
                if attempt < self.api_client.max_retries - 1:
                    continue
                else:
                    return self._create_failed_combined_response(f"Unexpected error: {e}", job_title)
        
        # If all attempts failed
        logger.error(f"All combined extraction attempts failed")
        return self._create_failed_combined_response("All attempts failed", job_title)

    def _create_fallback_response(self, job_title: str = "") -> Dict:
        """Create a fallback response when all extraction methods fail."""
        min_years, confidence = self.response_parser._infer_experience_from_title(job_title)
        
        return {
            "min_experience_years": min_years,
            "experience_type": "minimum",
            "experience_details": f"Fallback: inferred from title '{job_title}'" if job_title else "Fallback: no title available",
            "experience_extracted": False,
            "extraction_confidence": confidence
        }
    
    def _create_failed_skills_response(self, reason: str, job_title: str = "") -> Dict:
        """Create a fallback skills response when extraction fails."""
        failed_skills = self.response_parser._create_failed_skills_extraction(reason, job_title)
        return failed_skills.__dict__

    def _create_failed_summary_response(self, reason: str, job_title: str = "") -> Dict:
        """Create a fallback summary response when extraction fails."""
        failed_summary = self.response_parser._create_failed_summary_extraction(reason, job_title)
        return failed_summary.__dict__

    def _create_failed_combined_response(self, reason: str, job_title: str = "") -> Dict:
        """Create a fallback combined response when extraction fails."""
        failed_combined = self.response_parser._create_failed_combined_extraction(reason, job_title)
        return failed_combined.__dict__
