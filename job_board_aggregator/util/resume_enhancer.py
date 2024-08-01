"""Resume text enhancement using Groq with LFU model rotation - Async version."""

import aiohttp
import asyncio
import re
from typing import Optional, Dict, Any
from job_board_aggregator.config import logger
from job_board_aggregator.api.groq_client import GroqLLMClient
from job_board_aggregator.util.groq_model_manager import get_model_manager


class ResumeEnhancementError(Exception):
    """Custom exception for resume enhancement errors."""
    pass


class ResumeEnhancer:
    """Resume text enhancer using Groq LLM with model rotation."""
    
    # JSON Schema for structured response
    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "enhanced_resume": {
                "type": "string",
                "description": "Enhanced resume text optimized for vector search matching with job postings. Must use job posting format: Job Title, Experience Required, Required Skills, Job Summary"
            },
            "extracted_experience": {
                "type": "integer",
                "description": "Total years of professional experience extracted from resume",
                "minimum": 0,
                "maximum": 50
            },
            "extracted_skills": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "Array of technical skills and technologies mentioned in the resume"
            }
        },
        "required": ["enhanced_resume", "extracted_experience", "extracted_skills"],
        "additionalProperties": False
    }

    # Enhancement prompt template optimized for vector search matching
    ENHANCEMENT_PROMPT = """You are a professional resume optimization expert specializing in optimizing resumes for vector search and semantic matching with job postings.

ORIGINAL RESUME TEXT:
{resume_text}

TASK: You need to both enhance the resume text for optimal vector search matching AND extract key information.

CRITICAL: The enhanced resume must be structured to match EXACTLY how job postings are formatted in our vector database. Job postings use this EXACT structured format:
- Job Title: [title]
- Experience Required: [details]  
- Required Skills: [skills]
- Job Summary: [description]

OPTIMIZATION INSTRUCTIONS:
1. Use IDENTICAL headers as job postings: "Job Title", "Experience Required", "Required Skills", "Job Summary"
2. Express experience as "X years of experience required in [field]" (match job format exactly)
3. List skills as comma-separated list exactly like jobs: "skill1, skill2, skill3"
4. Write summaries in requirements-fulfilled style, not achievement style
5. Use job posting language patterns: "Experience required", "Knowledge of", "Proficiency in"
6. Preserve ALL original information while restructuring for semantic matching
7. DO NOT add information not in the original text
8. Format consistently with clear section headers matching job postings exactly

LANGUAGE TRANSFORMATION EXAMPLES:
AVOID: "5 years of professional experience in..."
USE: "5 years of experience required in..."

AVOID: "Proficient in Python, skilled in React"  
USE: "Required Skills: Python, React"

AVOID: "Successfully delivered 10+ projects"
USE: "Experience required: Delivered 10+ projects"

STRUCTURE THE ENHANCED RESUME EXACTLY LIKE THIS:
Job Title: [Derived from experience, matching common job titles like "Senior Software Engineer"]
Experience Required: [X years of experience required in Y field]
Required Skills: [Comma-separated list: Python, JavaScript, React, AWS, Docker, etc.]
Job Summary: [Requirements-focused summary describing capabilities as fulfilled requirements]
[Additional sections following same requirement-focused language]

EXTRACTION INSTRUCTIONS:
Also extract:
- Total years of professional experience (estimate if not stated) as integer
- Key technical skills and technologies mentioned as array of strings

You must respond with a valid JSON object matching this exact schema:
{{
  "enhanced_resume": "enhanced resume text with job posting format",
  "extracted_experience": number_of_years_as_integer,
  "extracted_skills": ["skill1", "skill2", "skill3"]
}}"""

    FALLBACK_PROMPT = """Clean and format this resume text with structured headings and extract basic information:

{resume_text}

Structure the resume with clear headings matching job posting format EXACTLY:
- Job Title: [Role based on experience]
- Experience Required: [X years of experience required in field]
- Required Skills: [Comma-separated list of skills]
- Job Summary: [Requirements-focused summary]

LANGUAGE REQUIREMENTS:
- Use "Experience Required" not "Experience Level"
- Use "Required Skills" not "Technical Skills"  
- Use "Job Summary" not "Professional Summary"
- Express experience as "X years of experience required in [field]"
- List skills as comma-separated format

You must respond with a valid JSON object matching this exact schema:
{{
  "enhanced_resume": "cleaned and structured resume text with job posting format",
  "extracted_experience": number_of_years_as_integer,
  "extracted_skills": ["skill1", "skill2", "skill3"]
}}"""
    
    def __init__(self):
        """Initialize the resume enhancer."""
        self.groq_client = None
        self.model_manager = get_model_manager()
        self._initialize_groq_client()
    
    def _initialize_groq_client(self):
        """Initialize Groq client."""
        try:
            self.groq_client = GroqLLMClient()
            logger.info("Resume enhancer initialized with Groq client")
            
            # Log model manager statistics
            stats = self.model_manager.get_usage_stats()
            logger.info(f"Model manager initialized: {len(stats['available_models'])} models, rotation: {stats['rotation_enabled']}")
        except Exception as e:
            logger.error(f"Failed to initialize Groq client for resume enhancement: {e}")
            self.groq_client = None
    
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
                
            logger.info(f"[RESUME_LFU] Low token availability ({remaining_tokens} remaining), will wait {wait_seconds:.1f}s")
            return True, wait_seconds
        
        return False, 0
    
    async def enhance_resume_text(self, resume_text: str, fallback_on_error: bool = True) -> Dict[str, Any]:
        """
        Enhance resume text using Groq with model rotation (async version).
        
        Args:
            resume_text: Raw resume text to enhance
            fallback_on_error: Whether to return original text if enhancement fails
            
        Returns:
            Dict containing enhanced text and metadata
        """
        if not resume_text or not resume_text.strip():
            return {
                'enhanced_text': resume_text,
                'original_text': resume_text,
                'enhancement_used': False,
                'enhancement_method': 'none',
                'error': 'Empty resume text provided'
            }
        
        original_length = len(resume_text)
        
        # Check if Groq client is available
        if not self.groq_client:
            logger.warning("Groq client not available for resume enhancement")
            if fallback_on_error:
                return {
                    'enhanced_text': resume_text,
                    'original_text': resume_text,
                    'original_length': original_length,
                    'enhanced_length': original_length,
                    'enhancement_used': False,
                    'enhancement_method': 'groq_unavailable',
                    'error': 'Groq client not available'
                }
            else:
                raise ResumeEnhancementError("Groq client not available")
        
        try:
            # Try main enhancement prompt with model rotation
            logger.info("Starting resume enhancement with model rotation...")
            result = await self._try_enhancement_with_rotation(resume_text, self.ENHANCEMENT_PROMPT)
            
            if result and result.get('enhanced_text'):
                return {
                    'enhanced_text': result['enhanced_text'],
                    'original_text': resume_text,
                    'original_length': original_length,
                    'enhanced_length': len(result['enhanced_text']),
                    'enhancement_used': True,
                    'enhancement_method': result.get('enhancement_method', 'groq_primary'),
                    'model_used': result.get('model_used', 'unknown'),
                    'extracted_experience': result.get('extracted_experience'),
                    'extracted_skills': result.get('extracted_skills', [])
                }
        
        except Exception as e:
            logger.warning(f"Primary enhancement with rotation failed, trying fallback: {e}")
        
        try:
            # Try fallback prompt with model rotation
            result = await self._try_enhancement_with_rotation(resume_text, self.FALLBACK_PROMPT)
            
            if result and result.get('enhanced_text'):
                return {
                    'enhanced_text': result['enhanced_text'],
                    'original_text': resume_text,
                    'original_length': original_length,
                    'enhanced_length': len(result['enhanced_text']),
                    'enhancement_used': True,
                    'enhancement_method': result.get('enhancement_method', 'groq_fallback'),
                    'model_used': result.get('model_used', 'unknown'),
                    'extracted_experience': result.get('extracted_experience'),
                    'extracted_skills': result.get('extracted_skills', [])
                }
        
        except Exception as e:
            logger.error(f"Fallback enhancement with rotation also failed: {e}")
        
        # Return original text if all enhancement attempts fail
        if fallback_on_error:
            logger.info("All enhancement attempts failed, returning original text")
            return {
                'enhanced_text': resume_text,
                'original_text': resume_text,
                'original_length': original_length,
                'enhanced_length': original_length,
                'enhancement_used': False,
                'enhancement_method': 'fallback_original',
                'error': 'Enhancement failed, using original text',
                'extracted_experience': None,
                'extracted_skills': []
            }
        else:
            raise ResumeEnhancementError("All enhancement attempts failed")
    
    async def _try_enhancement_with_rotation(self, resume_text: str, prompt_template: str) -> Optional[Dict[str, Any]]:
        """
        Try to enhance resume text using model rotation (async version).
        
        Args:
            resume_text: Resume text to enhance
            prompt_template: Prompt template to use
            
        Returns:
            Enhancement result dict or None if all models failed
        """
        stats = self.model_manager.get_usage_stats()
        available_models = stats['available_models']
        
        if not available_models:
            logger.error("No models available for enhancement")
            raise ResumeEnhancementError("No models available")
        
        logger.info(f"[MODEL_ROTATION] Starting enhancement with {len(available_models)} available models")
        
        # Try each model in LFU order
        models_tried = []
        last_exception = None
        
        for attempt in range(len(available_models)):
            try:
                # Get next model from LFU manager
                selected_model = await self.model_manager.get_next_model()
                
                if selected_model in models_tried:
                    logger.warning(f"[MODEL_ROTATION] Model {selected_model} already tried, skipping")
                    continue
                
                models_tried.append(selected_model)
                logger.info(f"[MODEL_ROTATION] Attempt {attempt + 1}/{len(available_models)}: Trying model {selected_model}")
                
                # Try enhancement with this model
                result = await self._try_enhancement(resume_text, prompt_template, selected_model)
                
                if result and result.get('enhanced_text'):
                    # Success - record usage and return
                    await self.model_manager.record_usage(selected_model, success=True)
                    
                    # Add model info to result
                    result['model_used'] = selected_model
                    result['enhancement_method'] = f"groq_primary_{selected_model.split('/')[-1]}" if 'primary' in prompt_template else f"groq_fallback_{selected_model.split('/')[-1]}"
                    
                    logger.info(f"[MODEL_ROTATION] SUCCESS with model {selected_model} on attempt {attempt + 1}")
                    return result
                else:
                    # Failed - record failure
                    await self.model_manager.record_usage(selected_model, success=False)
                    logger.warning(f"[MODEL_ROTATION] Model {selected_model} returned no result")
                    
            except Exception as e:
                # Record failure for this model
                if 'selected_model' in locals():
                    await self.model_manager.record_usage(selected_model, success=False)
                
                logger.warning(f"[MODEL_ROTATION] Model {selected_model if 'selected_model' in locals() else 'unknown'} failed: {e}")
                last_exception = e
                
                # Continue to next model
                continue
        
        # All models failed
        logger.error(f"[MODEL_ROTATION] All {len(models_tried)} models failed. Models tried: {models_tried}")
        
        if last_exception:
            raise last_exception
        else:
            raise ResumeEnhancementError("All available models failed to enhance resume")
    
    async def _try_enhancement(self, resume_text: str, prompt_template: str, model_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Try to enhance resume text with a specific prompt and model (async version).
        
        Args:
            resume_text: Resume text to enhance
            prompt_template: Prompt template to use
            model_name: Specific model to use (if None, uses model manager)
            
        Returns:
            Enhancement result dict or None if failed
        """
        try:
            # Get model to use
            if model_name is None:
                model_to_use = await self.model_manager.get_next_model()
            else:
                model_to_use = model_name
            
            logger.debug(f"Using model: {model_to_use}")
            
            # Format the prompt
            prompt = prompt_template.format(resume_text=resume_text)
            
            # Make async HTTP request with aiohttp - using the same method as the working direct call
            import os
            
            headers = {
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model_to_use,
                "messages": [
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 4000,  # Increased for resume content
                "top_p": 0.9,
                "response_format": {"type": "json_object"}  # Force JSON response
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
                                self.model_manager.mark_model_rate_limited(model_to_use, retry_after_seconds)
                                logger.warning(f"[RESUME_LFU] Rate limit hit for model {model_to_use}. Marked as unavailable for {retry_after_seconds:.1f}s. Moving to next model.")
                                return None  # This will trigger model rotation to try next available model
                            
                            # For other HTTP errors, raise immediately
                            if response.status != 200:
                                error_text = await response.text()
                                logger.error(f"API call failed with status {response.status}: {error_text}")
                                return None
                            
                            response_data = await response.json()
                            
                            # Success - break out of retry loop
                            break
                            
                except aiohttp.ClientResponseError as e:
                    if e.status == 429:
                        # Rate limit error - mark model as unavailable and move to next model
                        self.model_manager.mark_model_rate_limited(model_to_use, 60.0)  # Default 60s
                        logger.warning(f"[RESUME_LFU] Rate limit error for model {model_to_use}. Marked as unavailable. Moving to next model.")
                        return None
                    else:
                        # For other HTTP errors, don't retry
                        logger.error(f"[RESUME_LFU] HTTP error {e.status} for model {model_to_use}: {e}")
                        return None
                except Exception as e:
                    # For other errors, don't retry
                    logger.error(f"[RESUME_LFU] Unexpected error for model {model_to_use}: {e}")
                    return None
            
            # Extract text from response
            if response_data and 'choices' in response_data:
                choices = response_data['choices']
                if choices and len(choices) > 0:
                    content = choices[0].get('message', {}).get('content', '')
                    
                    if content and content.strip():
                        logger.info(f"DEBUG - Groq response content length: {len(content)}")
                        logger.info(f"DEBUG - First 200 chars of response: {content[:200]}")
                        
                        # Parse the JSON response
                        enhanced_text, extracted_experience, extracted_skills = self._parse_json_response(content)
                        
                        logger.info(f"DEBUG - Parsed enhanced_text length: {len(enhanced_text) if enhanced_text else 'None'}")
                        logger.info(f"DEBUG - Parsed extracted_experience: {extracted_experience}")
                        logger.info(f"DEBUG - Parsed extracted_skills: {extracted_skills}")
                        
                        # Basic validation - enhanced text should not be too short
                        if enhanced_text and len(enhanced_text) >= len(resume_text) * 0.1:  # Lowered from 0.3 to 0.1 (10% minimum)
                            return {
                                'enhanced_text': enhanced_text,
                                'extracted_experience': extracted_experience,
                                'extracted_skills': extracted_skills
                            }
                        else:
                            logger.warning(f"Enhanced text too short: {len(enhanced_text) if enhanced_text else 0} vs {len(resume_text)} original. Groq response may not be following the expected JSON format.")
                            return None
                    else:
                        logger.warning("Empty content in Groq response")
                        return None
                else:
                    logger.warning("No choices in Groq response")
                    return None
            else:
                logger.warning("Invalid response structure from Groq")
                return None
                
        except Exception as e:
            logger.error(f"Error during Groq enhancement with model {model_to_use if 'model_to_use' in locals() else 'unknown'}: {e}")
            raise
    
    def _parse_json_response(self, content: str) -> tuple:
        """
        Parse the JSON response from Groq containing enhanced text and extracted info.
        
        Args:
            content: Raw JSON response content from Groq
            
        Returns:
            Tuple of (enhanced_text, extracted_experience, extracted_skills)
        """
        try:
            import json
            
            # Try to parse as JSON first
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response: {e}")
                # Try to clean the content and parse again
                # Sometimes Groq adds extra text before/after JSON
                content_clean = content.strip()
                
                # Look for JSON object in the content
                start_brace = content_clean.find('{')
                end_brace = content_clean.rfind('}')
                
                if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                    json_part = content_clean[start_brace:end_brace + 1]
                    try:
                        data = json.loads(json_part)
                    except json.JSONDecodeError:
                        logger.warning("Could not extract valid JSON from response, falling back to old parser")
                        return self._parse_structured_response(content)
                else:
                    logger.warning("No JSON object found in response, falling back to old parser")
                    return self._parse_structured_response(content)
            
            # Extract data from JSON
            enhanced_text = data.get('enhanced_resume', '')
            extracted_experience = data.get('extracted_experience')
            extracted_skills = data.get('extracted_skills', [])
            
            # Validate extracted experience
            if extracted_experience is not None:
                try:
                    extracted_experience = int(extracted_experience)
                except (ValueError, TypeError):
                    extracted_experience = None
            
            # Validate extracted skills
            if not isinstance(extracted_skills, list):
                extracted_skills = []
            else:
                # Filter out empty or invalid skills
                extracted_skills = [str(skill).strip() for skill in extracted_skills if skill and str(skill).strip()]
            
            return enhanced_text, extracted_experience, extracted_skills
                
        except Exception as e:
            logger.warning(f"Error parsing JSON response: {e}, falling back to text parser")
            # Fallback to old structured response parser
            return self._parse_structured_response(content)
    def _parse_structured_response(self, content: str) -> tuple:
        """
        Parse the structured response from Groq containing enhanced text and extracted info.
        This is a fallback method for when JSON parsing fails.
        
        Args:
            content: Raw response content from Groq
            
        Returns:
            Tuple of (enhanced_text, extracted_experience, extracted_skills)
        """
        try:
            # Split by the separator
            sections = content.split('---')
            
            if len(sections) >= 3:
                # Parse enhanced resume
                enhanced_section = sections[0].strip()
                if enhanced_section.startswith('ENHANCED_RESUME:'):
                    enhanced_text = enhanced_section.replace('ENHANCED_RESUME:', '').strip()
                else:
                    enhanced_text = enhanced_section
                
                # Parse experience
                experience_section = sections[1].strip()
                if experience_section.startswith('EXTRACTED_EXPERIENCE:'):
                    experience_text = experience_section.replace('EXTRACTED_EXPERIENCE:', '').strip()
                else:
                    experience_text = experience_section
                
                # Try to extract number from experience
                try:
                    import re
                    experience_numbers = re.findall(r'\d+', experience_text)
                    extracted_experience = int(experience_numbers[0]) if experience_numbers else None
                except (ValueError, IndexError):
                    extracted_experience = None
                
                # Parse skills
                skills_section = sections[2].strip()
                if skills_section.startswith('EXTRACTED_SKILLS:'):
                    skills_text = skills_section.replace('EXTRACTED_SKILLS:', '').strip()
                else:
                    skills_text = skills_section
                
                # Clean up skills list
                extracted_skills = []
                if skills_text:
                    skills_list = [skill.strip() for skill in skills_text.split(',')]
                    extracted_skills = [skill for skill in skills_list if skill and len(skill) > 1]
                
                return enhanced_text, extracted_experience, extracted_skills
            else:
                # Fallback: treat entire content as enhanced text
                logger.warning("Could not parse structured response, using content as enhanced text")
                return content.strip(), None, []
                
        except Exception as e:
            logger.warning(f"Error parsing structured response: {e}")
            return content.strip(), None, []
    
    def quick_clean_text(self, resume_text: str) -> str:
        """
        Quick text cleaning without Groq enhancement.
        
        Args:
            resume_text: Text to clean
            
        Returns:
            Cleaned text
        """
        if not resume_text:
            return ""
        
        import re
        
        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', resume_text)
        
        # Remove extra newlines
        cleaned = re.sub(r'\n+', '\n', cleaned)
        
        # Remove leading/trailing whitespace
        cleaned = cleaned.strip()
        
        return cleaned


# Create a singleton instance
resume_enhancer = ResumeEnhancer()


async def enhance_resume_text(resume_text: str, fallback_on_error: bool = True) -> Dict[str, Any]:
    """
    Convenience function to enhance resume text (async version).
    
    Args:
        resume_text: Raw resume text to enhance
        fallback_on_error: Whether to return original text if enhancement fails
        
    Returns:
        Dict containing enhanced text and metadata
    """
    return await resume_enhancer.enhance_resume_text(resume_text, fallback_on_error)
