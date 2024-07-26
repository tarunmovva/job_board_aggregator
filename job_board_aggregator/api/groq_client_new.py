"""
Groq LLM Client for Experience Extraction

This module provides a client for extracting minimum experience requirements 
from job descriptions using the Groq API with proper rate limiting.
"""

import os
import time
import json
import re
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ExperienceType(Enum):
    TOTAL = "total"
    RELEVANT = "relevant" 
    PREFERRED = "preferred"
    MINIMUM = "minimum"

@dataclass
class ExperienceData:
    min_experience_years: int
    experience_type: str
    experience_details: str
    experience_extracted: bool
    extraction_confidence: float

class GroqLLMClient:
    """
    Client for extracting experience requirements from job descriptions using Groq API.
    Implements proper rate limiting to ensure we stay within API limits.
    """
    
    def __init__(self):
        """Initialize Groq client with rate limiting."""
        self.api_key = self._load_api_key()
        self.model = os.getenv('GROQ_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        
        # Rate limiting configuration
        self.requests_per_minute = int(os.getenv('GROQ_REQUESTS_PER_MINUTE', '30'))
        self.max_retries = int(os.getenv('GROQ_MAX_RETRIES', '3'))
        
        # Rate limiting tracking
        self.request_times = []  # Track individual request times
        
        logger.info(f"Initialized GroqLLMClient with model {self.model}, rate limit: {self.requests_per_minute}/min")
    
    def _load_api_key(self) -> str:
        """Load API key from environment variables."""
        key = os.getenv('GROQ_API_KEY')
        if not key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        return key
    
    def _can_make_request(self) -> bool:
        """Check if we can make a request without hitting rate limits."""
        now = datetime.now()
        
        # Clean up old request times (older than 1 minute)
        self.request_times = [req_time for req_time in self.request_times 
                             if (now - req_time).total_seconds() < 60]
        
        # Check if we're under the rate limit
        return len(self.request_times) < self.requests_per_minute
    
    def _wait_for_rate_limit_reset(self) -> None:
        """Wait until we can make another request."""
        if not self.request_times:
            return
            
        # Find the oldest request in the current minute window
        oldest_request = min(self.request_times)
        time_since_oldest = (datetime.now() - oldest_request).total_seconds()
        
        if time_since_oldest < 60:
            wait_time = 60 - time_since_oldest + 1  # Add 1 second buffer
            logger.info(f"Rate limit reached, waiting {wait_time:.1f} seconds before next request")
            time.sleep(wait_time)
            
        # Clean up old requests after waiting
        now = datetime.now()
        self.request_times = [req_time for req_time in self.request_times 
                             if (now - req_time).total_seconds() < 60]
    
    def _preprocess_job_description(self, job_description: str, job_title: str = "") -> str:
        """
        Aggressive preprocessing to extract only the most relevant text around experience requirements.
        """
        if not job_description:
            return ""
        
        # Experience-related keywords
        experience_keywords = [
            'years', 'year', 'yrs', 'experience', 'experienced',
            'minimum', 'required', 'requirements', 'qualifications',
            'senior', 'junior', 'entry', 'mid-level'
        ]
        
        text = job_description.lower()
        
        # Find sentences with experience-related numbers
        experience_sentences = []
        sentences = re.split(r'[.!?\n]+', job_description)
        
        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            if not sentence_lower:
                continue
                
            # Look for numeric experience patterns first
            if re.search(r'\d+\s*[-+]?\s*(years?|yrs?|months?)', sentence_lower):
                experience_sentences.append((sentence.strip(), 10))  # Highest priority
                continue
            
            # Then look for experience keywords
            score = 0
            for keyword in experience_keywords:
                if keyword in sentence_lower:
                    score += 1
            
            if score > 0:
                experience_sentences.append((sentence.strip(), score))
        
        # Sort by score and take only top 3 most relevant sentences
        experience_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [s[0] for s in experience_sentences[:3]]
        
        # Build minimal result
        result = f"Job: {job_title}\n" if job_title else ""
        result += " ".join(top_sentences)
        
        # Very aggressive limit - max 800 characters
        max_chars = 800
        if len(result) > max_chars:
            result = result[:max_chars] + "..."        
        return result

    def _create_extraction_prompt(self, job_text: str, job_title: str = "") -> str:
        """Create a comprehensive prompt for extracting experience requirements."""
        
        prompt = f"""You are an expert HR analyst specializing in extracting precise experience requirements from job postings. You MUST always return valid JSON with no additional text or explanation.

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_text}

EXTRACTION INSTRUCTIONS:
1. First, scan the job description for explicit experience requirements (e.g., "3+ years", "minimum 5 years", "2-4 years experience")
2. If explicit experience is found, use the MINIMUM value from any range (e.g., "2-4 years" = 2, "3+" = 3)
3. If NO explicit experience is mentioned in the description, you MUST infer based on the job title using these guidelines:
   - "Senior" roles = 5-8 years minimum experience
   - "Lead" roles = 6-10 years minimum experience 
   - "Principal" or "Staff" roles = 8+ years minimum experience
   - "Manager" or "Director" roles = 7+ years minimum experience
   - "Junior" or "Associate" roles = 0-2 years minimum experience
   - "Entry Level" or "Intern" roles = 0 years experience
   - Standard role titles without seniority indicators = 2-3 years minimum experience
4. Always provide a confidence score based on how explicit the information was

RESPONSE FORMAT - Return ONLY this JSON structure with NO additional text:
{{"min_experience_years": <integer 0-50>, "experience_type": "minimum", "experience_details": "<brief explanation of how you determined this number>", "experience_extracted": <true if found in description, false if inferred from title>, "extraction_confidence": <0.1-1.0 where 1.0=explicitly stated, 0.8=clearly inferred from title, 0.5=general inference>}}

CRITICAL RULES:
- NEVER return null, undefined, or empty values
- ALWAYS return a valid integer for min_experience_years (0-50)
- ALWAYS return valid strings for experience_type and experience_details
- ALWAYS return a boolean for experience_extracted
- ALWAYS return a number between 0.0 and 1.0 for extraction_confidence
- ALWAYS infer experience from job title if not found in description
- NO explanatory text outside the JSON object
- NO markdown formatting or code blocks
- Response must be parseable as valid JSON
- The JSON must contain exactly these 5 keys: min_experience_years, experience_type, experience_details, experience_extracted, extraction_confidence

EXAMPLES:
Job with "3+ years experience required" → {{"min_experience_years": 3, "experience_type": "minimum", "experience_details": "Explicitly stated 3+ years required", "experience_extracted": true, "extraction_confidence": 1.0}}

Senior Software Engineer (no experience mentioned) → {{"min_experience_years": 5, "experience_type": "minimum", "experience_details": "Inferred from Senior level title", "experience_extracted": false, "extraction_confidence": 0.8}}

Software Developer (no experience mentioned) → {{"min_experience_years": 2, "experience_type": "minimum", "experience_details": "Standard developer role typically requires 2-3 years", "experience_extracted": false, "extraction_confidence": 0.6}}"""
        return prompt
    
    def _make_api_request(self, prompt: str) -> Dict:
        """Make a request to the Groq API using OpenAI-compatible format."""
        # Check rate limits before making request
        if not self._can_make_request():
            self._wait_for_rate_limit_reset()        
        
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
        
        # Track this request for rate limiting
        self.request_times.append(datetime.now())
        
        return response.json()
    
    def _parse_groq_response(self, response: Dict, job_title: str = "") -> ExperienceData:
        """Parse the response from Groq API and extract experience data."""
        try:
            # Extract content from Groq response structure
            if 'choices' not in response or not response['choices']:
                logger.error(f"Malformed Groq response (no 'choices'): {response}")
                return self._create_failed_extraction("No choices in response", job_title)
            
            choice = response['choices'][0]
            if 'message' not in choice or 'content' not in choice['message']:
                logger.error(f"Malformed Groq response (no message content): {choice}")
                return self._create_failed_extraction("No message content", job_title)
            
            content = choice['message']['content'].strip()
            logger.debug(f"Raw Groq response content: {content[:200]}...")
            
            # Remove markdown code blocks if present
            if content.startswith('```json'):
                content = content[7:]  # Remove ```json
            if content.startswith('```'):
                content = content[3:]  # Remove ```
            if content.endswith('```'):
                content = content[:-3]  # Remove closing ```
            
            content = content.strip()
            
            # Try to parse as JSON first
            try:
                data = json.loads(content)
                logger.debug(f"Successfully parsed JSON: {data}")
                
                # Apply validation and fixing
                data = self._validate_and_fix_groq_response(data, job_title)
                logger.debug(f"Validated and fixed Groq response: {data}")
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode failed: {e}, attempting regex extraction")
                # Fallback: extract JSON from text using regex
                json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        logger.debug(f"Successfully extracted JSON with regex: {data}")
                        
                        # Apply validation and fixing
                        data = self._validate_and_fix_groq_response(data, job_title)
                        logger.debug(f"Validated and fixed Groq response: {data}")
                        
                    except json.JSONDecodeError:
                        logger.warning("Regex extracted JSON is also invalid, using unstructured parsing")
                        return self._parse_unstructured_response(content, job_title)
                else:
                    logger.warning("No JSON found with regex, using unstructured parsing")
                    return self._parse_unstructured_response(content, job_title)
            
            # Validate and create ExperienceData
            result = ExperienceData(
                min_experience_years=data['min_experience_years'],
                experience_type=data['experience_type'],
                experience_details=data['experience_details'],
                experience_extracted=data['experience_extracted'],
                extraction_confidence=data['extraction_confidence']
            )
            
            logger.debug(f"Successfully created ExperienceData: {result}")
            return result
            
        except KeyError as e:
            logger.error(f"KeyError parsing Groq response - missing key {e}: {response}")
            return self._create_failed_extraction(f"Missing key: {e}", job_title)
        except Exception as e:
            logger.error(f"Unexpected error parsing Groq response: {e}")
            logger.error(f"Response was: {response}")
            return self._create_failed_extraction(f"Unexpected error: {e}", job_title)
    
    def _validate_and_fix_groq_response(self, data: Dict, job_title: str = "") -> Dict:
        """Validate and fix the response from Groq to ensure it matches the expected schema."""
        
        # Define required keys with defaults
        required_keys = {
            'min_experience_years': 0,
            'experience_type': 'minimum',
            'experience_details': 'Default extraction',
            'experience_extracted': False,
            'extraction_confidence': 0.5
        }
        
        # Ensure all required keys exist
        for key, default_value in required_keys.items():
            if key not in data:
                data[key] = default_value
                logger.warning(f"Missing key '{key}' in response, using default: {default_value}")
        
        # Validate and fix min_experience_years
        try:
            years = int(data['min_experience_years'])
            # Enforce constraints (0-50 years)
            data['min_experience_years'] = max(0, min(50, years))
        except (TypeError, ValueError):
            data['min_experience_years'] = 0
            logger.warning("Invalid min_experience_years, using default: 0")
        
        # Validate and fix experience_type
        valid_types = ['total', 'relevant', 'preferred', 'minimum']
        if data['experience_type'] not in valid_types:
            data['experience_type'] = 'minimum'
            logger.warning(f"Invalid experience_type, using default: minimum")
        
        # Validate and fix experience_details
        try:
            details = str(data['experience_details'])
            # Limit to 200 characters
            if len(details) > 200:
                data['experience_details'] = details[:197] + "..."
            elif len(details) == 0:
                data['experience_details'] = f"Extracted from {job_title}" if job_title else "Default extraction"
        except (TypeError, AttributeError):
            data['experience_details'] = f"Extracted from {job_title}" if job_title else "Default extraction"
        
        # Validate and fix experience_extracted
        try:
            data['experience_extracted'] = bool(data['experience_extracted'])
        except (TypeError, ValueError):
            data['experience_extracted'] = False
        
        # Validate and fix extraction_confidence
        try:
            confidence = float(data['extraction_confidence'])
            # Enforce constraints (0.0-1.0)
            data['extraction_confidence'] = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            data['extraction_confidence'] = 0.5
            logger.warning("Invalid extraction_confidence, using default: 0.5")
        
        # Remove any additional properties not in schema
        allowed_keys = set(required_keys.keys())
        data = {k: v for k, v in data.items() if k in allowed_keys}
        
        return data
    
    def _create_failed_extraction(self, reason: str, job_title: str = "") -> ExperienceData:
        """Create a failed extraction result with a specific reason, using title inference as fallback."""
        logger.warning(f"Creating failed extraction: {reason}")
        
        # Try to infer from job title as a fallback
        min_years, confidence = self._infer_experience_from_title(job_title)
        
        return ExperienceData(
            min_experience_years=min_years,
            experience_type="minimum",
            experience_details=f"Title-based inference ({reason}): {job_title}" if job_title else f"Failed extraction ({reason})",
            experience_extracted=False,
            extraction_confidence=confidence
        )
    
    def _parse_unstructured_response(self, content: str, job_title: str = "") -> ExperienceData:
        """Parse unstructured response as fallback with title-based inference."""
        logger.info("Parsing unstructured response with title-based inference")
        
        # Try to extract numbers from the text
        numbers = re.findall(r'\d+', content)
        min_years = 0
        confidence = 0.3
        
        if numbers:
            # Take the first reasonable number (between 0 and 20)
            for num_str in numbers:
                num = int(num_str)
                if 0 <= num <= 20:
                    min_years = num
                    confidence = 0.4
                    break
        
        # If no reasonable number found, infer from title
        if min_years == 0:
            min_years, confidence = self._infer_experience_from_title(job_title)
        
        return ExperienceData(
            min_experience_years=min_years,
            experience_type="minimum",
            experience_details=f"Unstructured parsing from {job_title}" if job_title else "Unstructured parsing",
            experience_extracted=min_years > 0 and confidence > 0.4,
            extraction_confidence=confidence
        )
    
    def _infer_experience_from_title(self, job_title: str) -> Tuple[int, float]:
        """Infer experience requirements from job title."""
        if not job_title:
            return 0, 0.2
        
        title_lower = job_title.lower()
        
        # Senior-level indicators (5-8 years)
        if any(keyword in title_lower for keyword in ['senior', 'sr.', 'sr ']):
            return 5, 0.8
        
        # Lead-level indicators (6-10 years)
        if any(keyword in title_lower for keyword in ['lead', 'principal', 'staff']):
            return 6, 0.8
        
        # Management-level indicators (7+ years)
        if any(keyword in title_lower for keyword in ['manager', 'director', 'head of']):
            return 7, 0.8
        
        # Junior-level indicators (0-2 years)
        if any(keyword in title_lower for keyword in ['junior', 'jr.', 'jr ', 'associate', 'entry', 'intern']):
            return 0, 0.8
        
        # Mid-level indicators (3-4 years)
        if any(keyword in title_lower for keyword in ['mid-level', 'mid level', 'intermediate']):
            return 3, 0.8
        
        # Default for standard titles (2-3 years)
        return 2, 0.6
    
    def _create_fallback_response(self, job_title: str = "") -> Dict:
        """Create a fallback response when all extraction methods fail."""
        min_years, confidence = self._infer_experience_from_title(job_title)
        
        return {
            "min_experience_years": min_years,
            "experience_type": "minimum",
            "experience_details": f"Fallback: inferred from title '{job_title}'" if job_title else "Fallback: no title available",
            "experience_extracted": False,
            "extraction_confidence": confidence
        }
    
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
        processed_text = self._preprocess_job_description(job_description, job_title)
        if not processed_text.strip():
            return self._create_fallback_response(job_title)
        
        # Create extraction prompt
        prompt = self._create_extraction_prompt(processed_text, job_title)
        
        # Try extraction with retries
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Making extraction request to Groq API (attempt {attempt + 1})")
                response = self._make_api_request(prompt)
                
                # Parse response
                experience_data = self._parse_groq_response(response, job_title)
                
                # Convert to dict for return
                result = {
                    "min_experience_years": experience_data.min_experience_years,
                    "experience_type": experience_data.experience_type,
                    "experience_details": experience_data.experience_details,
                    "experience_extracted": experience_data.experience_extracted,
                    "extraction_confidence": experience_data.extraction_confidence
                }
                
                logger.info(f"Successfully extracted experience data: {experience_data.min_experience_years} years")
                return result
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit error
                    logger.warning(f"Rate limit hit on attempt {attempt + 1}: {e}")
                    if attempt < self.max_retries - 1:
                        self._wait_for_rate_limit_reset()
                        continue
                    else:
                        logger.error("Rate limit hit on final attempt, using fallback")
                        return self._create_fallback_response(job_title)
                else:
                    logger.warning(f"HTTP error on attempt {attempt + 1}: {e}")
                    if attempt < self.max_retries - 1:
                        continue
                    else:
                        return self._create_fallback_response(job_title)
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"API request failed on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    continue
                else:
                    return self._create_fallback_response(job_title)
                    
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    continue
                else:
                    return self._create_fallback_response(job_title)
        
        # If all attempts failed
        logger.error(f"All extraction attempts failed")
        return self._create_fallback_response(job_title)
