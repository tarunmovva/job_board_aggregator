"""Resume text enhancement using Groq."""

from typing import Optional, Dict, Any
from job_board_aggregator.config import logger
from job_board_aggregator.api.groq_client import GroqLLMClient
from job_board_aggregator.util.groq_model_manager import get_model_manager


class ResumeEnhancementError(Exception):
    """Custom exception for resume enhancement errors."""
    pass


class ResumeEnhancer:
    """Resume text enhancer using Groq LLM."""    # Enhancement prompt template optimized for vector search matching
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
- Total years of professional experience (estimate if not stated)
- Key technical skills and technologies mentioned

RESPONSE FORMAT:
Return your response in this exact format with three sections separated by "---":

ENHANCED_RESUME:
[Enhanced resume text with structured format matching job posting style exactly]

---

EXTRACTED_EXPERIENCE:
[Total years of experience as a number only, e.g., "5"]

---

EXTRACTED_SKILLS:
[Comma-separated list of technical skills, e.g., "Python, JavaScript, React, Django, AWS"]"""

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

RESPONSE FORMAT:
Return your response in this exact format with three sections separated by "---":

ENHANCED_RESUME:
[Cleaned and structured resume text with job posting format]

---

EXTRACTED_EXPERIENCE:
[Total years of experience as a number, e.g., "3"]

---

EXTRACTED_SKILLS:
[Comma-separated list of skills, e.g., "Python, Java, SQL"]"""
    
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
    
    def enhance_resume_text(self, resume_text: str, fallback_on_error: bool = True) -> Dict[str, Any]:
        """
        Enhance resume text using Groq.
        
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
                    'enhancement_used': False,                    'enhancement_method': 'groq_unavailable',
                    'error': 'Groq client not available'
                }
            else:
                raise ResumeEnhancementError("Groq client not available")
        
        try:
            # Try main enhancement prompt with model rotation
            logger.info("Starting resume enhancement with model rotation...")
            result = self._try_enhancement_with_rotation(resume_text, self.ENHANCEMENT_PROMPT)
            
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
            result = self._try_enhancement_with_rotation(resume_text, self.FALLBACK_PROMPT)
            
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
    
    def _try_enhancement(self, resume_text: str, prompt_template: str, model_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Try to enhance resume text with a specific prompt and model.
        
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
                model_to_use = self.model_manager.get_next_model()
            else:
                model_to_use = model_name
            
            logger.debug(f"Using model: {model_to_use}")
            
            # Format the prompt
            prompt = prompt_template.format(resume_text=resume_text)
            
            # Make a direct API request without JSON-only constraint
            import requests
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
                "top_p": 0.9
                # Removed response_format constraint to allow plain text
            }
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            response_data = response.json()
            
            # Extract text from response
            if response_data and 'choices' in response_data:
                choices = response_data['choices']
                if choices and len(choices) > 0:
                    content = choices[0].get('message', {}).get('content', '')
                    
                    if content and content.strip():
                        logger.info(f"DEBUG - Groq response content length: {len(content)}")
                        logger.info(f"DEBUG - First 200 chars of response: {content[:200]}")
                        
                        # Parse the structured response
                        enhanced_text, extracted_experience, extracted_skills = self._parse_structured_response(content)
                        
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
                            logger.warning(f"Enhanced text too short: {len(enhanced_text) if enhanced_text else 0} vs {len(resume_text)} original")
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
    
    def _try_enhancement_with_rotation(self, resume_text: str, prompt_template: str) -> Optional[Dict[str, Any]]:
        """
        Try to enhance resume text using model rotation.
        
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
                selected_model = self.model_manager.get_next_model()
                
                if selected_model in models_tried:
                    logger.warning(f"[MODEL_ROTATION] Model {selected_model} already tried, skipping")
                    continue
                
                models_tried.append(selected_model)
                logger.info(f"[MODEL_ROTATION] Attempt {attempt + 1}/{len(available_models)}: Trying model {selected_model}")
                
                # Try enhancement with this model
                result = self._try_enhancement(resume_text, prompt_template, selected_model)
                
                if result and result.get('enhanced_text'):
                    # Success - record usage and return
                    self.model_manager.record_usage(selected_model, success=True)
                    
                    # Add model info to result
                    result['model_used'] = selected_model
                    result['enhancement_method'] = f"groq_primary_{selected_model.split('/')[-1]}" if 'primary' in prompt_template else f"groq_fallback_{selected_model.split('/')[-1]}"
                    
                    logger.info(f"[MODEL_ROTATION] SUCCESS with model {selected_model} on attempt {attempt + 1}")
                    return result
                else:
                    # Failed - record failure
                    self.model_manager.record_usage(selected_model, success=False)
                    logger.warning(f"[MODEL_ROTATION] Model {selected_model} returned no result")
                    
            except Exception as e:
                # Record failure for this model
                if selected_model:
                    self.model_manager.record_usage(selected_model, success=False)
                
                logger.warning(f"[MODEL_ROTATION] Model {selected_model} failed: {e}")
                last_exception = e
                
                # Continue to next model
                continue
        
        # All models failed
        logger.error(f"[MODEL_ROTATION] All {len(models_tried)} models failed. Models tried: {models_tried}")
        
        if last_exception:
            raise last_exception
        else:
            raise ResumeEnhancementError("All available models failed to enhance resume")
    
    def _try_enhancement(self, resume_text: str, prompt_template: str, model_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Parse the structured response from Groq containing enhanced text and extracted info.
        
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


def enhance_resume_text(resume_text: str, fallback_on_error: bool = True) -> Dict[str, Any]:
    """
    Convenience function to enhance resume text.
    
    Args:
        resume_text: Raw resume text to enhance
        fallback_on_error: Whether to return original text if enhancement fails
        
    Returns:
        Dict containing enhanced text and metadata
    """
    return resume_enhancer.enhance_resume_text(resume_text, fallback_on_error)
