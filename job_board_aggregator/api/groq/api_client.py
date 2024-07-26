"""
Low-level API client for communicating with Groq API.
"""

import os
import logging
import requests
from typing import Dict, Tuple, Union

logger = logging.getLogger(__name__)


class GroqAPIClient:
    """Low-level client for making requests to the Groq API."""
    
    def __init__(self):
        """Initialize API client with configuration."""
        self.api_key = self._load_api_key()
        self.model = os.getenv('GROQ_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.max_retries = int(os.getenv('GROQ_MAX_RETRIES', '3'))
        
        logger.info(f"Initialized GroqAPIClient with model {self.model}")
    
    def _load_api_key(self) -> str:
        """Load API key from environment variables."""
        key = os.getenv('GROQ_API_KEY')
        if not key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        return key
    
    def make_api_request(self, prompt: str) -> Tuple[Dict, Dict[str, Union[int, str]]]:
        """
        Make a request to the Groq API using OpenAI-compatible format.
        Returns (response_data, rate_limit_headers)
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # Low temperature for consistent extraction
            "max_tokens": 500,
            "top_p": 0.9,
            "response_format": {"type": "json_object"}  # Force JSON-only responses
        }
        
        response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        return response.json(), response
