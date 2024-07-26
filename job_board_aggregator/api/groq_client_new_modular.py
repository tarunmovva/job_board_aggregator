"""
Groq LLM Client for Experience Extraction

This module provides a client for extracting minimum experience requirements 
from job descriptions using the Groq API with proper rate limiting.

This is a compatibility wrapper around the new modular Groq client structure.
"""

import logging
from typing import Dict

# Import from the new modular structure
from .groq.groq_client import GroqLLMClient as ModularGroqLLMClient
from .groq.models import ExperienceData, SkillsData, JobSummaryData, ExperienceType, SkillCategory

logger = logging.getLogger(__name__)

# Export the models for backward compatibility
__all__ = ['GroqLLMClient', 'ExperienceData', 'SkillsData', 'JobSummaryData', 'ExperienceType', 'SkillCategory']


class GroqLLMClient:
    """
    Compatibility wrapper for the modular Groq client.
    
    This maintains the same interface as the original monolithic client
    while delegating to the new modular structure.
    """
    
    def __init__(self):
        """Initialize the client using the modular implementation."""
        self._client = ModularGroqLLMClient()
        logger.info("Initialized GroqLLMClient (modular wrapper)")
    
    def extract_experience(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract experience requirements from a job description.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing extracted experience data        """
        return self._client.extract_experience(job_description, job_title)

    def extract_skills(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract skills from a job description.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing extracted skills data
        """
        return self._client.extract_skills(job_description, job_title)

    def extract_job_summary(self, job_description: str, job_title: str = "") -> Dict:
        """
        Extract a 5-point job summary from a job description.
        
        Args:
            job_description: The job description text to analyze
            job_title: Optional job title for context
            
        Returns:
            Dictionary containing extracted job summary data
        """
        return self._client.extract_job_summary(job_description, job_title)
    
    # Expose internal components for advanced usage
    @property
    def rate_limiter(self):
        """Access to the rate limiter component."""
        return self._client.rate_limiter
    
    @property
    def preprocessor(self):
        """Access to the preprocessor component."""
        return self._client.preprocessor
    
    @property
    def prompt_generator(self):
        """Access to the prompt generator component."""
        return self._client.prompt_generator
    
    @property
    def api_client(self):
        """Access to the API client component."""
        return self._client.api_client
    
    @property
    def response_parser(self):
        """Access to the response parser component."""
        return self._client.response_parser
