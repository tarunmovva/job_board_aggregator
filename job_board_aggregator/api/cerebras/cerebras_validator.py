"""
Cerebras AI validator for false positive detection using schema-enforced responses.
"""

import os
import logging
import asyncio
import json
import random
import math
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """Configuration for each Cerebras model."""
    name: str
    display_name: str
    context_tokens: int = 65536

class CerebrasSchemaValidator:
    """
    Schema-enforced validator using random selection of 2 Cerebras models for unanimous consensus.
    """
    
    def __init__(self):
        self.api_key = self._load_api_key()
        self.timeout = int(os.getenv('CEREBRAS_TIMEOUT_SECONDS', '30'))
        
        # Available Cerebras models (high context length models for better performance)
        # Ordered by performance: qwen-3-coder-480b (0.23s) is fastest
        self.available_models = [
            # High context models (65,536 tokens)
            ModelConfig("llama-3.3-70b", "Llama 3.3 70B", 65536),
            ModelConfig("qwen-3-coder-480b", "Qwen 3 Coder 480B", 65536),
            # ModelConfig("qwen-3-235b-a22b-thinking-2507", "Qwen 3 235B Thinking", 65536),
            ModelConfig("qwen-3-32b", "Qwen 3 32B", 65536),
            # ModelConfig("gpt-oss-120b", "GPT OSS 120B", 65536),
            # High context model (64,000 tokens)
            ModelConfig("qwen-3-235b-a22b-instruct-2507", "Qwen 3 235B Instruct", 64000),
        ]
        
        # Configuration
        self.max_jobs_per_batch = int(os.getenv('CEREBRAS_MAX_JOBS_PER_BATCH', '180'))
        self.resume_max_chars = int(os.getenv('CEREBRAS_RESUME_MAX_CHARS', '15000'))
        self.require_unanimous = os.getenv('CEREBRAS_REQUIRE_UNANIMOUS', 'true').lower() == 'true'
        
        # JSON Schema for reference (now using JSON mode for better compatibility)
        self.response_schema = {
            "type": "object",
            "properties": {
                "flagged_job_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of job URLs that are false positives"
                }
            },
            "required": ["flagged_job_urls"],
            "additionalProperties": False
        }
        
        # Use JSON mode instead of strict schema for better compatibility
        self.use_json_mode = os.getenv('CEREBRAS_USE_JSON_MODE', 'true').lower() == 'true'
        
        # Models that have issues with JSON mode and should use schema mode
        self.schema_mode_models = {'qwen-3-32b'}  # Add problematic models here
        
        logger.info(f"Initialized CerebrasSchemaValidator with {len(self.available_models)} available models")
        logger.info(f"Default mode: {'JSON mode' if self.use_json_mode else 'strict schema mode'}")
        logger.info(f"Schema mode override for models: {self.schema_mode_models}")
        logger.info(f"Max jobs per batch: {self.max_jobs_per_batch}")
        logger.info(f"Require unanimous consensus: {self.require_unanimous}")
    
    def _load_api_key(self) -> str:
        """Load Cerebras API key from environment."""
        key = os.getenv('CERABRAS_API_KEY')  # Keeping your current env var name
        if not key:
            raise ValueError("CERABRAS_API_KEY not found in environment variables")
        return key
    
    async def validate_job_matches(self, job_matches: List[Dict], resume_text: str) -> Tuple[List[str], Dict[str, Any]]:
        """
        Validate job matches using random 2-model consensus with schema enforcement.
        
        Args:
            job_matches: List of job match dictionaries
            resume_text: Enhanced resume text (optimized by Groq for better semantic matching)
            
        Returns:
            Tuple of (false_positive_urls, validation_metadata)
        """
        if not job_matches:
            return [], {"models_used": [], "jobs_evaluated": 0}
        
        # Randomly select 2 models for this validation
        selected_models = random.sample(self.available_models, 2)
        
        logger.info(f"Selected models for validation: {[m.display_name for m in selected_models]}")
        
        try:
            # Determine if we need batch processing
            job_batches = self._create_job_batches(job_matches, resume_text)
            
            logger.info(f"Processing {len(job_matches)} jobs in {len(job_batches)} batches")
            
            # Process all batches in parallel for maximum speed
            all_false_positives = set()
            batch_metadata = []
            
            if len(job_batches) == 1:
                # Single batch - process directly
                batch_false_positives, batch_meta = await self._validate_job_batch(
                    job_batches[0], resume_text, selected_models, 0
                )
                all_false_positives.update(batch_false_positives)
                batch_metadata.append(batch_meta)
            else:
                # Multiple batches - process all in parallel
                logger.info(f"Processing all {len(job_batches)} batches in parallel")
                
                # Create tasks for all batches
                batch_tasks = []
                for batch_idx, job_batch in enumerate(job_batches):
                    task = self._validate_job_batch(
                        job_batch, resume_text, selected_models, batch_idx
                    )
                    batch_tasks.append(task)
                
                # Wait for all batches to complete in parallel
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # Process results from all batches
                for batch_idx, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"Batch {batch_idx + 1} failed: {result}")
                        # Add empty metadata for failed batch
                        batch_metadata.append({
                            "batch_index": batch_idx,
                            "jobs_count": len(job_batches[batch_idx]),
                            "models_successful": 0,
                            "false_positives_found": 0,
                            "error": str(result)
                        })
                    else:
                        batch_false_positives, batch_meta = result
                        all_false_positives.update(batch_false_positives)
                        batch_metadata.append(batch_meta)
            
            # Create comprehensive metadata
            metadata = {
                "models_used": [m.display_name for m in selected_models],
                "jobs_evaluated": len(job_matches),
                "batches_processed": len(job_batches),
                "batch_details": batch_metadata,
                "false_positives_removed": len(all_false_positives),
                "response_method": "json_mode" if self.use_json_mode else "schema_mode",
                "schema_enforced": not self.use_json_mode,  # Only true when using strict schema
                "require_unanimous": self.require_unanimous
            }
            
            logger.info(f"Validation complete: {len(all_false_positives)} false positives from {len(job_matches)} jobs")
            return list(all_false_positives), metadata
            
        except Exception as e:
            logger.error(f"Cerebras validation failed: {e}")
            return [], {"error": str(e), "models_used": []}
    
    def _create_job_batches(self, job_matches: List[Dict], resume_text: str) -> List[List[Dict]]:
        """Create optimal job batches based on token limits."""
        truncated_resume = self._truncate_resume(resume_text)
        resume_tokens = len(truncated_resume) // 4  # Rough token estimation
        
        # Calculate tokens available for jobs (leaving buffer for prompt structure)
        # Based on analysis: resume ~4000, prompt ~2000, buffer ~1000 = ~7000 overhead
        available_tokens_for_jobs = 58000  # Conservative estimate within 65K context
        estimated_tokens_per_job = 305  # Based on actual job data analysis: ~1220 chars / 4
        max_jobs_by_context = available_tokens_for_jobs // estimated_tokens_per_job
        
        # Use the smaller of configured limit or context-based limit
        effective_batch_size = min(self.max_jobs_per_batch, max_jobs_by_context)
        
        logger.info(f"Batch size: {effective_batch_size} jobs per batch (context allows {max_jobs_by_context})")
        
        # Create batches
        batches = []
        for i in range(0, len(job_matches), effective_batch_size):
            batch = job_matches[i:i + effective_batch_size]
            batches.append(batch)
        
        return batches
    
    async def _validate_job_batch(self, job_batch: List[Dict], resume_text: str, 
                                  selected_models: List[ModelConfig], batch_idx: int) -> Tuple[List[str], Dict[str, Any]]:
        """Validate a single batch of jobs using the selected models."""
        
        loop = asyncio.get_event_loop()
        
        # Create validation tasks for both selected models
        with ThreadPoolExecutor(max_workers=2) as executor:
            task1 = loop.run_in_executor(
                executor,
                self._validate_with_single_model,
                selected_models[0],
                job_batch,
                resume_text,
                batch_idx
            )
            
            task2 = loop.run_in_executor(
                executor,
                self._validate_with_single_model,
                selected_models[1],
                job_batch,
                resume_text,
                batch_idx
            )
            
            # Wait for both models to complete
            results = await asyncio.gather(task1, task2, return_exceptions=True)
        
        # Process results
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Model {selected_models[i].display_name} batch {batch_idx} failed: {result}")
            else:
                successful_results.append(result)
        
        # Apply unanimous consensus
        false_positives = self._apply_unanimous_consensus(successful_results)
        
        # Create batch metadata
        batch_meta = {
            "batch_index": batch_idx,
            "jobs_count": len(job_batch),
            "models_successful": len(successful_results),
            "false_positives_found": len(false_positives)
        }
        
        return false_positives, batch_meta
    
    def _validate_with_single_model(self, model_config: ModelConfig, job_batch: List[Dict], 
                                   resume_text: str, batch_idx: int) -> Dict[str, Any]:
        """Validate a batch of jobs with a single Cerebras model using JSON mode or schema enforcement."""
        
        try:
            # Import here to avoid circular imports and ensure it's available
            from cerebras.cloud.sdk import Cerebras
            
            client = Cerebras(api_key=self.api_key)
            
            prompt = self._create_validation_prompt(job_batch, resume_text, model_config.display_name, batch_idx)
            
            # Choose response format based on configuration and model compatibility
            use_schema_mode = (not self.use_json_mode) or (model_config.name in self.schema_mode_models)
            
            if use_schema_mode:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "false_positive_detection",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
                messages = [{"role": "user", "content": prompt}]
                logger.debug(f"Using strict schema mode for {model_config.display_name}")
            else:
                response_format = {"type": "json_object"}
                messages = [
                    {"role": "system", "content": "You are a JSON API that ONLY returns JSON objects. You must not provide any explanations, analysis, reasoning, or text outside JSON. Respond with valid JSON only. Maximum 200 tokens. Be extremely concise. No other text is allowed."},
                    {"role": "user", "content": prompt}
                ]
                logger.debug(f"Using JSON mode for {model_config.display_name}")
            
            response = client.chat.completions.create(
                model=model_config.name,
                messages=messages,
                temperature=0.1,  # Lower temperature for more focused, deterministic responses
                max_completion_tokens=200,  # Reduced from 1000 to force concise responses
                response_format=response_format
            )
            
            # Validate response exists
            if not response or not response.choices:
                logger.error(f"Empty response from {model_config.display_name} batch {batch_idx}")
                return self._create_error_result(model_config, batch_idx, job_batch, "Empty response from API")
            
            content = response.choices[0].message.content
            if not content or content.strip() == "":
                logger.error(f"Empty content from {model_config.display_name} batch {batch_idx}")
                return self._create_error_result(model_config, batch_idx, job_batch, "Empty content in response")
            
            # Log raw content for debugging (first 200 chars)
            logger.debug(f"Raw response from {model_config.display_name}: {content[:200]}...")
            
            # Parse JSON response with fallback extraction
            try:
                parsed_result = json.loads(content)
            except json.JSONDecodeError as json_error:
                # Try to extract JSON from mixed content
                logger.warning(f"Initial JSON parse failed for {model_config.display_name}, attempting extraction...")
                parsed_result = self._extract_json_from_text(content)
                
                if parsed_result is None:
                    logger.error(f"JSON decode error for {model_config.display_name} batch {batch_idx}: {json_error}")
                    logger.error(f"Raw content that failed parsing: {content[:500]}")
                    return self._create_error_result(model_config, batch_idx, job_batch, f"JSON decode error: {json_error}")
                else:
                    logger.info(f"Successfully extracted JSON from mixed content for {model_config.display_name}")
            
            # Extract flagged URLs with fallback parsing
            flagged_urls = self._extract_flagged_urls(parsed_result, model_config.display_name)
            
            return {
                "model": model_config.name,
                "model_display": model_config.display_name,
                "batch_index": batch_idx,
                "flagged_job_urls": flagged_urls,
                "jobs_processed": len(job_batch),
                "success": True,
                "response_method": "schema_mode" if use_schema_mode else "json_mode"
            }
            
        except Exception as e:
            error_str = str(e)
            
            # Handle specific Cerebras API errors
            if "incomplete_json_output" in error_str or "Failed to generate JSON" in error_str:
                logger.warning(f"Model {model_config.display_name} failed to generate JSON (likely too verbose), assuming no flagged jobs")
                # Extract any partial analysis from the failed generation if available
                if "failed_generation" in error_str:
                    # Try to extract flagged URLs from the failed generation text
                    failed_text = self._extract_failed_generation_text(error_str)
                    if failed_text:
                        flagged_urls = self._extract_urls_from_analysis(failed_text)
                        if flagged_urls:
                            logger.info(f"Extracted {len(flagged_urls)} URLs from failed generation analysis")
                            return {
                                "model": model_config.name,
                                "model_display": model_config.display_name,
                                "batch_index": batch_idx,
                                "flagged_job_urls": flagged_urls,
                                "jobs_processed": len(job_batch),
                                "success": True,
                                "response_method": "failed_generation_extraction"
                            }
                
                # Default to empty result for incomplete JSON
                return {
                    "model": model_config.name,
                    "model_display": model_config.display_name,
                    "batch_index": batch_idx,
                    "flagged_job_urls": [],
                    "jobs_processed": len(job_batch),
                    "success": True,
                    "response_method": "incomplete_json_fallback"
                }
            
            logger.error(f"Single model validation failed for {model_config.display_name} batch {batch_idx}: {e}")
            return self._create_error_result(model_config, batch_idx, job_batch, str(e))
    
    def _create_error_result(self, model_config: ModelConfig, batch_idx: int, job_batch: List[Dict], error_msg: str) -> Dict[str, Any]:
        """Create a standardized error result."""
        return {
            "model": model_config.name,
            "model_display": model_config.display_name,
            "batch_index": batch_idx,
            "flagged_job_urls": [],
            "error": error_msg,
            "jobs_processed": len(job_batch),
            "success": False
        }
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """Extract JSON object from text that may contain additional content."""
        import re
        
        # First try to find any JSON-like structure
        json_patterns = [
            r'\{[^{}]*"flagged_job_urls"[^{}]*\}',  # Simple pattern
            r'\{[^{}]*"flagged_job_urls"[^{}]*(?:\[[^\]]*\])[^{}]*\}',  # With array
            r'\{(?:[^{}]|{[^{}]*})*\}',  # Nested braces
            r'\{[^{}]*"flagged_job_urls"[^{}]*\[[^\]]*\][^{}]*\}',  # More specific with array
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    # Try to parse each potential JSON match
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and "flagged_job_urls" in parsed:
                        logger.info(f"Extracted valid JSON from text using pattern: {pattern[:30]}...")
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        # If no complete JSON found, try to find array patterns and construct JSON
        array_patterns = [
            r'"flagged_job_urls":\s*\[([^\]]*)\]',
            r'"flagged_job_urls":\s*\[\s*\]',  # Empty array
            r'flagged_job_urls["\']?\s*:\s*\[([^\]]*)\]',  # Without quotes around key
        ]
        
        for pattern in array_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    # Construct a simple JSON object with the found array
                    if r'flagged_job_urls":\s*\[\s*\]' in pattern:  # Empty array pattern
                        constructed_json = '{"flagged_job_urls": []}'
                    else:
                        array_content = match.group(1).strip()
                        # Clean up the array content
                        if array_content:
                            constructed_json = f'{{"flagged_job_urls": [{array_content}]}}'
                        else:
                            constructed_json = '{"flagged_job_urls": []}'
                    
                    parsed = json.loads(constructed_json)
                    logger.info(f"Constructed valid JSON from array pattern")
                    return parsed
                except json.JSONDecodeError:
                    continue
        
        # If model is being verbose but mentions no flagged jobs, assume empty result
        if any(phrase in text.lower() for phrase in [
            'no jobs should be flagged',
            'no role mismatches',
            'no false positives',
            'all jobs appear suitable',
            'no clear mismatches',
            'no fundamental incompatibilities',
            'all positions appear to be suitable',
            'found no clear role mismatches',
            'no jobs that should be flagged',
            'all seem appropriate',
            'no mismatches found',
            'appear suitable for the candidate'
        ]):
            logger.info("Model indicates no flagged jobs in verbose response, returning empty result")
            return {"flagged_job_urls": []}
        
        # Last resort: if response is very long and doesn't contain any JSON structure,
        # and doesn't mention specific job URLs being flagged, assume no flagged jobs
        if len(text) > 500 and 'http' not in text and '{' not in text and '[' not in text:
            logger.info("Long response without JSON structure or URLs, assuming no flagged jobs")
            return {"flagged_job_urls": []}
        
        logger.warning(f"Could not extract valid JSON from text: {text[:200]}...")
        return None
    
    def _extract_failed_generation_text(self, error_str: str) -> Optional[str]:
        """Extract the failed_generation text from Cerebras API error."""
        import re
        
        # Look for the failed_generation field in the error
        match = re.search(r"'failed_generation':\s*[\"']([^\"']*)[\"']", error_str)
        if match:
            return match.group(1)
        
        # Alternative pattern for different quote styles
        match = re.search(r'"failed_generation":\s*"([^"]*)"', error_str)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_urls_from_analysis(self, analysis_text: str) -> List[str]:
        """Extract flagged job URLs from analysis text."""
        import re
        
        flagged_urls = []
        
        # Look for patterns like "flag this URL" or "Flag this" near job numbers
        flag_patterns = [
            r'Job\s+(\d+).*?[Ff]lag',
            r'job\s+(\d+).*?[Ff]lag',
            r'URL\s+(\d+).*?[Ff]lag',
            r'[Ff]lag.*?job\s+(\d+)',
            r'[Ff]lag.*?Job\s+(\d+)',
        ]
        
        job_numbers = set()
        for pattern in flag_patterns:
            matches = re.findall(pattern, analysis_text, re.IGNORECASE)
            for match in matches:
                job_numbers.add(int(match))
        
        # Look for explicit mentions of flagging specific jobs
        explicit_patterns = [
            r'So flag this URL',
            r'Flag this URL',
            r'flag this',
            r'Flag this',
        ]
        
        # Find job numbers mentioned before flag statements
        lines = analysis_text.split('\n')
        for i, line in enumerate(lines):
            if any(pattern.lower() in line.lower() for pattern in explicit_patterns):
                # Look for job number in current or previous lines
                context_lines = lines[max(0, i-2):i+1]
                context_text = ' '.join(context_lines)
                job_match = re.search(r'[Jj]ob\s+(\d+)', context_text)
                if job_match:
                    job_numbers.add(int(job_match.group(1)))
        
        logger.info(f"Extracted job numbers from analysis: {sorted(job_numbers)}")
        
        # Convert job numbers to URLs (we need to map them to actual URLs from the batch)
        # For now, return empty list since we don't have the URL mapping here
        # This would need to be enhanced to map job numbers to actual URLs
        return []
    
    def _extract_flagged_urls(self, parsed_result: Dict, model_name: str) -> List[str]:
        """Extract flagged URLs from parsed JSON with fallback parsing."""
        # Try standard format first
        if "flagged_job_urls" in parsed_result:
            urls = parsed_result["flagged_job_urls"]
            if isinstance(urls, list):
                return [str(url) for url in urls if url]  # Convert to strings and filter empty
        
        # Try alternative formats that might be returned
        alternative_keys = ["flagged_urls", "false_positives", "removed_jobs", "flagged_jobs"]
        for key in alternative_keys:
            if key in parsed_result:
                urls = parsed_result[key]
                if isinstance(urls, list):
                    logger.warning(f"Model {model_name} used alternative key '{key}' instead of 'flagged_job_urls'")
                    return [str(url) for url in urls if url]
        
        # If no valid array found, log and return empty
        logger.warning(f"Model {model_name} response did not contain valid flagged URLs: {parsed_result}")
        return []
    
    def _apply_unanimous_consensus(self, validation_results: List[Dict]) -> List[str]:
        """Apply unanimous consensus - both models must agree to flag a job."""
        
        if len(validation_results) != 2:
            logger.warning(f"Expected 2 model results, got {len(validation_results)}. No consensus possible.")
            return []
        
        # Get flagged URLs from each model
        model1_flagged = set(validation_results[0].get("flagged_job_urls", []))
        model2_flagged = set(validation_results[1].get("flagged_job_urls", []))
        
        # Find intersection - both models must agree
        unanimous_false_positives = model1_flagged & model2_flagged
        
        logger.info(f"Model 1 ({validation_results[0].get('model_display', 'Unknown')}) flagged: {len(model1_flagged)}, "
                   f"Model 2 ({validation_results[1].get('model_display', 'Unknown')}) flagged: {len(model2_flagged)}, "
                   f"Unanimous: {len(unanimous_false_positives)}")
        
        return list(unanimous_false_positives)
    
    def _truncate_resume(self, resume_text: str) -> str:
        """Apply minimal truncation to enhanced resume if needed (enhanced resumes are pre-optimized)."""
        if len(resume_text) <= self.resume_max_chars:
            return resume_text
        
        # Enhanced resumes are already optimized, so minimal truncation should be needed
        # Smart truncation at paragraph boundary for edge cases
        truncated = resume_text[:self.resume_max_chars]
        last_paragraph = truncated.rfind('\n\n')
        if last_paragraph > self.resume_max_chars * 0.8:
            truncated = truncated[:last_paragraph]
        
        return truncated + "\n\n[ENHANCED RESUME TRUNCATED FOR API EFFICIENCY]"
    
    def _create_validation_prompt(self, job_batch: List[Dict], resume_text: str, 
                                 model_name: str, batch_idx: int) -> str:
        """Create validation prompt for schema-enforced false positive detection using enhanced resume."""
        
        truncated_resume = self._truncate_resume(resume_text)
        
        # Create job list with minimal data (URL + chunk text only)
        jobs_list = []
        for i, job in enumerate(job_batch):
            jobs_list.append(f"{i + 1}. URL: {job.get('job_link', '')} - Description: {job.get('chunk_text', '')[:300]}...")
        
        jobs_text = "\n".join(jobs_list)
        
        prompt = f"""You are an expert HR recruiter using {model_name} to identify FALSE POSITIVE job matches based on ROLE COMPATIBILITY.

CANDIDATE RESUME (Enhanced & Optimized):
{truncated_resume}"

JOBS TO EVALUATE (Batch {batch_idx + 1} - {len(job_batch)} jobs):
{jobs_text}

TASK: Identify job URLs that are clearly ROLE MISMATCHES or poor fits. Focus on fundamental incompatibilities.

CRITICAL ROLE MISMATCH CRITERIA:
1. **Role Category Mismatch**: 
   - Software Engineer ↔ Data Scientist/ML Engineer
   - Frontend Developer ↔ DevOps/Infrastructure
   - Web Developer ↔ Mobile App Developer
   - Backend Developer ↔ UI/UX Designer

2. **Seniority Level Mismatch**:
   - Junior candidate (0-3 years) ↔ Senior/Lead roles (8+ years)
   - Individual contributor ↔ Management positions

3. **Core Technology Mismatch**:
   - Java enterprise candidate ↔ Python/JavaScript roles
   - Web development background ↔ Data science/ML roles
   - Frontend specialist ↔ Backend-only positions

4. **Domain Expertise Mismatch**:
   - E-commerce experience ↔ Scientific computing roles
   - Web applications ↔ Embedded systems
   - Consumer apps ↔ Enterprise infrastructure

5. **Educational/Certification Requirements**:
   - PhD required positions for Bachelor's candidates
   - Security clearance required roles
   - Specific certifications mandatory

EVALUATION RULES:
- Flag ONLY when there's a fundamental role/domain incompatibility
- Consider acceptable career transitions (Frontend → Fullstack is OK)
- Don't flag for minor skill gaps that can be learned
- Be CONSERVATIVE: When uncertain, do NOT flag

YOU MUST RESPOND ONLY WITH VALID JSON. NO OTHER TEXT ALLOWED.

DO NOT EXPLAIN. DO NOT ANALYZE. DO NOT PROVIDE COMMENTARY.
DO NOT THINK OUT LOUD. DO NOT PROVIDE REASONING.
RETURN ONLY THE JSON OBJECT BELOW.

MAXIMUM 200 TOKENS. BE EXTREMELY CONCISE.

For role mismatches, return this exact JSON format:

{{
  "flagged_job_urls": ["url1", "url2", "url3"]
}}

If no jobs should be flagged, return this exact JSON:

{{
  "flagged_job_urls": []
}}

CRITICAL: Your entire response must be ONLY the JSON object above. No additional text, no explanations, no analysis. JSON ONLY."""

        return prompt


# Standalone validation function for easy import
async def validate_jobs_with_cerebras(job_matches: List[Dict], resume_text: str) -> Tuple[List[str], Dict[str, Any]]:
    """
    Convenience function to validate jobs using Cerebras AI.
    
    Args:
        job_matches: List of job dictionaries with job_link and chunk_text
        resume_text: Enhanced resume text (optimized by Groq for consistent validation)
        
    Returns:
        Tuple of (false_positive_urls, validation_metadata)
    """
    validator = CerebrasSchemaValidator()
    return await validator.validate_job_matches(job_matches, resume_text)