"""API client for job board aggregator."""

import json
from typing import Dict, Optional, Any

import requests

from job_board_aggregator.config import logger, API_TIMEOUT


class JobAPIClient:
    """Handles API calls to job board endpoints."""
    
    def __init__(self, timeout: int = API_TIMEOUT):
        """Initialize the API client with a timeout.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
    
    def fetch_jobs(self, company_name: str, api_endpoint: str) -> Optional[Dict[str, Any]]:
        """Fetch jobs from a company's API endpoint.
        
        Args:
            company_name: Name of the company
            api_endpoint: URL for the company's job board API
            
        Returns:
            Dict containing the JSON response or None if the request failed
        """
        try:
            logger.info(f"Fetching jobs for {company_name} from {api_endpoint}")
            response = requests.get(api_endpoint, timeout=self.timeout)
            response.raise_for_status()  # Raise an exception for 4XX/5XX responses
            
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching jobs for {company_name}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON for {company_name}: {e}")
            return None