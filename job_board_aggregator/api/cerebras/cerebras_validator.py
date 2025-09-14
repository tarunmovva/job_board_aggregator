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
            ModelConfig("qwen-3-235b-a22b-thinking-2507", "Qwen 3 235B Thinking", 65536),
            ModelConfig("qwen-3-32b", "Qwen 3 32B", 65536),
            # ModelConfig("gpt-oss-120b", "GPT OSS 120B", 65536),
            # High context model (64,000 tokens)
            ModelConfig("qwen-3-235b-a22b-instruct-2507", "Qwen 3 235B Instruct", 64000),
        ]
        
        # Configuration
        self.max_jobs_per_batch = int(os.getenv('CEREBRAS_MAX_JOBS_PER_BATCH', '180'))
        self.resume_max_chars = int(os.getenv('CEREBRAS_RESUME_MAX_CHARS', '15000'))
        self.require_unanimous = os.getenv('CEREBRAS_REQUIRE_UNANIMOUS', 'true').lower() == 'true'
        self.prefer_non_thinking = os.getenv('CEREBRAS_PREFER_NON_THINKING', 'true').lower() == 'true'
        self.allow_partial_consensus = os.getenv('CEREBRAS_ALLOW_PARTIAL_CONSENSUS', 'false').lower() == 'true'
        
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
        self.schema_mode_models = {'qwen-3-32b', 'qwen-3-coder-480b'}  # Add problematic models here
        
        # Models that don't support response_format parameter at all (use plain text mode)
        self.plain_text_models = {'gpt-oss-120b', 'qwen-3-235b-a22b-thinking-2507'}  # Models without structured output support
        
        logger.info(f"Initialized CerebrasSchemaValidator with {len(self.available_models)} available models")
        logger.info(f"Default mode: {'JSON mode' if self.use_json_mode else 'strict schema mode'}")
        logger.info(f"Schema mode override for models: {self.schema_mode_models}")
        logger.info(f"Plain text mode for models: {self.plain_text_models}")
        logger.info(f"Max jobs per batch: {self.max_jobs_per_batch}")
        logger.info(f"Require unanimous consensus: {self.require_unanimous}")
        logger.info(f"Prefer non-thinking models: {self.prefer_non_thinking}")
        logger.info(f"Allow partial consensus: {self.allow_partial_consensus}")
        
        # Log model mode assignments
        for model in self.available_models:
            if model.name in self.plain_text_models:
                mode = "plain text"
            elif model.name in self.schema_mode_models:
                mode = "schema"
            else:
                mode = "JSON" if self.use_json_mode else "schema"
            logger.info(f"  {model.display_name} -> {mode} mode")
    
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
            Note: false_positive_urls are returned in their original format for accurate filtering
        """
        if not job_matches:
            return [], {"models_used": [], "jobs_evaluated": 0}
        
        # Randomly select 2 models for this validation
        if self.prefer_non_thinking:
            # Prefer non-thinking models for more reliable JSON output
            non_thinking_models = [m for m in self.available_models if "thinking" not in m.name.lower()]
            if len(non_thinking_models) >= 2:
                selected_models = random.sample(non_thinking_models, 2)
            else:
                # Fall back to all models if not enough non-thinking models
                selected_models = random.sample(self.available_models, 2)
        else:
            selected_models = random.sample(self.available_models, 2)
        
        logger.info(f"Selected models for validation: {[m.display_name for m in selected_models]}")
        
        # Create URL mapping for consistent filtering (normalized -> original)
        self.url_mapping = self._create_url_mapping(job_matches)
        
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
            
            # Convert normalized URLs back to original URLs for accurate filtering
            original_false_positives = []
            mapping_stats = {"successful": 0, "missing": 0}
            
            for normalized_url in all_false_positives:
                original_url = self.url_mapping.get(normalized_url, normalized_url)
                original_false_positives.append(original_url)
                
                if normalized_url in self.url_mapping:
                    mapping_stats["successful"] += 1
                    if normalized_url != original_url:
                        logger.debug(f"Mapped normalized URL '{normalized_url}' back to original '{original_url}'")
                else:
                    mapping_stats["missing"] += 1
                    logger.warning(f"No mapping found for normalized URL '{normalized_url}', using as-is")
            
            logger.info(f"Validation complete: {len(original_false_positives)} false positives from {len(job_matches)} jobs")
            logger.info(f"URL mapping: {mapping_stats['successful']} successful, {mapping_stats['missing']} missing")
            if original_false_positives:
                logger.info(f"False positive URLs (original format): {original_false_positives[:3]}{'...' if len(original_false_positives) > 3 else ''}")
            return original_false_positives, metadata
            
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
            use_plain_text = model_config.name in self.plain_text_models
            use_schema_mode = (not self.use_json_mode) or (model_config.name in self.schema_mode_models)
            
            if use_plain_text:
                # Plain text mode for models that don't support response_format
                response_format = None  # No response format parameter
                if "gpt-oss" in model_config.name.lower():
                    # Unified EXTREME criteria for GPT OSS with world-ending warnings
                    resume_snippet = resume_text[:1000] + "..." if len(resume_text) > 1000 else resume_text
                    jobs_snippet = "\n".join([
                        f"{i+1}. {job.get('job_link', '')} - {job.get('chunk_text', '')[:200]}..."
                        for i, job in enumerate(job_batch[:20])  # Limit to first 20 jobs
                    ])
                    
                    unified_prompt = f"""🚨 WORLD-ENDING DANGER: NEVER mention matched/suitable jobs! 🚨

Resume: {resume_snippet}

Jobs: {jobs_snippet}

Flag ONLY EXTREME cross-domain mismatches:
✅ Tech ↔ Sales/Marketing/HR/Finance/Legal
✅ Developer ↔ Pure Design roles

NEVER flag technical variations:
❌ Frontend ↔ Backend ↔ Fullstack
❌ Python ↔ Java ↔ JavaScript
❌ Web ↔ Mobile development
❌ Data Science ↔ ML Engineer
❌ Industry/company size differences
❌ Clearance requirements

Return JSON ONLY: {{\"flagged_job_urls\": [\"url1\"]}} or {{\"flagged_job_urls\": []}}
🚨 NEVER mention matched jobs! 🚨"""
                    
                    messages = [
                        {"role": "system", "content": "You MUST return only valid JSON. No explanations. No analysis. JSON ONLY or catastrophic failure occurs."},
                        {"role": "user", "content": unified_prompt}
                    ]
                else:
                    # Standard plain text prompt with full EXTREME criteria
                    messages = [
                        {"role": "system", "content": "You MUST return only valid JSON. No explanations. No analysis. JSON ONLY or catastrophic system failure occurs."},
                        {"role": "user", "content": prompt}
                    ]
                logger.debug(f"Using plain text mode for {model_config.display_name}")
            elif use_schema_mode:
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
                    {"role": "system", "content": "You are a JSON API that ONLY returns JSON objects. You must not provide any explanations, analysis, reasoning, or text outside JSON. Respond with valid JSON only. Maximum 500 tokens. Be extremely concise. No other text is allowed."},
                    {"role": "user", "content": prompt}
                ]
                logger.debug(f"Using JSON mode for {model_config.display_name}")
            
            # Create API call parameters
            # Use higher token limit for verbose models and large batches
            if "thinking" in model_config.name.lower():
                max_tokens = 1500
            elif "gpt-oss" in model_config.name.lower():
                max_tokens = 1000  # GPT OSS also tends to be verbose
            elif model_config.name in self.schema_mode_models and len(job_batch) > 50:
                max_tokens = 800  # Schema mode models need more tokens for large batches
            elif len(job_batch) > 80:
                max_tokens = 700  # All models need more tokens for very large batches
            else:
                max_tokens = 500
            
            api_params = {
                "model": model_config.name,
                "messages": messages,
                "temperature": 0.1,  # Lower temperature for more focused, deterministic responses
                "max_completion_tokens": max_tokens,
            }
            
            # Only add response_format if the model supports it
            if response_format is not None:
                api_params["response_format"] = response_format
            
            # Log API call details for debugging
            logger.info(f"Calling {model_config.display_name} with {len(api_params['messages'])} messages, "
                       f"response_format: {api_params.get('response_format', {}).get('type', 'none')}, "
                       f"max_tokens: {api_params['max_completion_tokens']}")
            
            response = client.chat.completions.create(**api_params)
            
            # Log token usage and completion details
            if hasattr(response, 'usage') and response.usage:
                logger.info(f"{model_config.display_name} token usage: "
                           f"prompt={response.usage.prompt_tokens}, "
                           f"completion={response.usage.completion_tokens}, "
                           f"total={response.usage.total_tokens}")
            
            if response.choices and hasattr(response.choices[0], 'finish_reason'):
                logger.info(f"{model_config.display_name} finish_reason: {response.choices[0].finish_reason}")
            
            # Validate response exists
            if not response or not response.choices:
                logger.error(f"Empty response from {model_config.display_name} batch {batch_idx}")
                return self._create_error_result(model_config, batch_idx, job_batch, "Empty response from API")
            
            # Check for truncated response due to token limit
            finish_reason = response.choices[0].finish_reason
            if finish_reason == 'length':
                logger.warning(f"Response from {model_config.display_name} was truncated due to token limit")
                # For thinking models, this is common - try to extract partial JSON or assume no flagged jobs
                if "thinking" in model_config.name.lower():
                    logger.info(f"Thinking model {model_config.display_name} response truncated, assuming no flagged jobs")
                    return {
                        "model": model_config.name,
                        "model_display": model_config.display_name,
                        "batch_index": batch_idx,
                        "flagged_job_urls": [],
                        "jobs_processed": len(job_batch),
                        "success": True,
                        "response_method": "truncated_thinking_fallback"
                    }
                # For GPT OSS 120B, try to extract reasoning or assume no flagged jobs
                elif "gpt-oss" in model_config.name.lower():
                    logger.info(f"GPT OSS 120B response truncated, trying to extract from reasoning")
                    # Reasoning might contain partial analysis - try to extract it
                    if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                        content = response.choices[0].message.reasoning
                        logger.info(f"Using reasoning field as content for truncated GPT OSS response")
                    else:
                        logger.info(f"No reasoning available, assuming no flagged jobs")
                        return {
                            "model": model_config.name,
                            "model_display": model_config.display_name,
                            "batch_index": batch_idx,
                            "flagged_job_urls": [],
                            "jobs_processed": len(job_batch),
                            "success": True,
                            "response_method": "truncated_gpt_oss_fallback"
                        }
            
            content = response.choices[0].message.content
            
            # Handle GPT OSS 120B which sometimes puts content in reasoning field
            if (not content or content.strip() == "") and hasattr(response.choices[0].message, 'reasoning'):
                reasoning = response.choices[0].message.reasoning
                if reasoning and reasoning.strip():
                    logger.info(f"{model_config.display_name} content was empty but reasoning available, extracting from reasoning")
                    content = reasoning
            
            # Enhanced logging for plain text models like GPT OSS 120B
            if model_config.name in self.plain_text_models:
                logger.info(f"{model_config.display_name} response details:")
                logger.info(f"  Response object: {response}")
                logger.info(f"  Choices count: {len(response.choices) if response.choices else 'None'}")
                logger.info(f"  Content length: {len(content) if content else 0}")
                logger.info(f"  Content preview: '{content[:100] if content else 'EMPTY'}...'")
                if hasattr(response.choices[0].message, 'role'):
                    logger.info(f"  Message role: {response.choices[0].message.role}")
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    logger.info(f"  Reasoning length: {len(response.choices[0].message.reasoning)}")
                    logger.info(f"  Reasoning preview: '{response.choices[0].message.reasoning[:100]}...'")
            
            if not content or content.strip() == "":
                logger.error(f"Empty content from {model_config.display_name} batch {batch_idx}")
                if model_config.name in self.plain_text_models:
                    logger.error(f"Plain text model received prompt length: {len(messages[1]['content']) if len(messages) > 1 else 'N/A'}")
                    logger.error(f"This indicates a potential API issue with {model_config.display_name}")
                    # For plain text models, empty content is a recoverable issue
                    if model_config.name == 'gpt-oss-120b':
                        logger.warning(f"GPT OSS 120B returned empty content - treating as no flagged jobs (conservative approach)")
                        return {
                            "model": model_config.name,
                            "model_display": model_config.display_name,
                            "batch_index": batch_idx,
                            "flagged_job_urls": [],
                            "jobs_processed": len(job_batch),
                            "success": True,
                            "response_method": "empty_content_conservative_fallback",
                            "note": "Empty response treated conservatively as no flags"
                        }
                # For other models, empty content is a more serious issue
                logger.warning(f"Empty content from {model_config.display_name} - using conservative no-flags response")
                return {
                    "model": model_config.name,
                    "model_display": model_config.display_name,
                    "batch_index": batch_idx,
                    "flagged_job_urls": [],
                    "jobs_processed": len(job_batch),
                    "success": True,
                    "response_method": "empty_content_conservative",
                    "warning": "Model returned empty content"
                }
            
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
            
            # Determine response method label accurately for metadata
            if use_plain_text:
                response_method_label = "plain_text"
            elif use_schema_mode:
                response_method_label = "schema_mode"
            else:
                response_method_label = "json_mode"

            return {
                "model": model_config.name,
                "model_display": model_config.display_name,
                "batch_index": batch_idx,
                "flagged_job_urls": flagged_urls,
                "jobs_processed": len(job_batch),
                "success": True,
                "response_method": response_method_label
            }
            
        except Exception as e:
            error_str = str(e)
            
            # Enhanced error logging for debugging
            logger.info(f"API call failed for {model_config.display_name}:")
            logger.info(f"  Error type: {type(e).__name__}")
            logger.info(f"  Error message: {error_str[:300]}...")
            if hasattr(e, 'response'):
                logger.info(f"  HTTP status: {getattr(e.response, 'status_code', 'unknown')}")
                logger.info(f"  Response headers: {getattr(e.response, 'headers', {})}")
            
            # Log the specific error for debugging
            logger.debug(f"Full API error for {model_config.display_name}: {error_str}")
            
            # Handle specific Cerebras API errors
            if ("incomplete_json_output" in error_str or 
                "Failed to generate JSON" in error_str or
                "400" in error_str or
                "Bad Request" in error_str or
                "too_many_tokens" in error_str or
                "maximum context length" in error_str):
                
                # Handle model failures without mutating configuration
                if "thinking" in model_config.name.lower():
                    logger.warning(f"Thinking model {model_config.display_name} failed with 400 error - likely too verbose or unsupported format")
                    logger.info(f"Using fallback response for {model_config.display_name} this session")
                    # Don't mutate configuration - maintain consistency
                else:
                    logger.warning(f"Model {model_config.display_name} failed to generate JSON (likely too verbose), using fallback response")
                
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
        
        # First try direct JSON parse
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict) and "flagged_job_urls" in parsed:
                logger.info("Direct JSON parse successful")
                return parsed
        except json.JSONDecodeError as e:
            # Check if this is a truncation error (unterminated string)
            if "Unterminated string" in str(e):
                logger.warning(f"Detected truncated JSON response: {str(e)}")
                # Try to fix truncated JSON by closing incomplete strings and arrays
                fixed_text = self._fix_truncated_json(text.strip())
                if fixed_text:
                    try:
                        parsed = json.loads(fixed_text)
                        if isinstance(parsed, dict) and "flagged_job_urls" in parsed:
                            logger.info("Successfully parsed truncated JSON after repair")
                            return parsed
                    except json.JSONDecodeError:
                        pass
        
        # Simplified JSON pattern extraction with clear priorities
        # Priority 1: Look for complete JSON objects with flagged_job_urls
        json_patterns = [
            r'\{\s*"flagged_job_urls"\s*:\s*\[[^\]]*\]\s*\}',  # Complete simple object
            r'\{[^{}]*"flagged_job_urls"[^{}]*\[[^\]]*\][^{}]*\}',  # Object with flagged array
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and "flagged_job_urls" in parsed:
                        logger.info(f"Successfully extracted JSON using targeted pattern")
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
            'appear suitable for the candidate',
            'no urls to flag',
            'no flagged urls',
            'no jobs to flag'
        ]):
            logger.info("Model indicates no flagged jobs in verbose response, returning empty result")
            return {"flagged_job_urls": []}
        
        # For thinking models that got truncated without JSON, check if they were analyzing mismatches
        if len(text) > 1000 and 'mismatch' in text.lower() and '{' not in text and '[' not in text:
            # If the thinking model is discussing mismatches but got cut off, assume conservative (no flags)
            logger.info("Thinking model was analyzing mismatches but got truncated, assuming no flagged jobs")
            return {"flagged_job_urls": []}
        
        # For GPT OSS models, try to extract analysis from reasoning-style text
        if 'gpt-oss' in text.lower() or ('flag' in text.lower() and 'mismatch' in text.lower()):
            # Look for explicit flagging decisions in GPT OSS reasoning
            flagged_urls = []
            lines = text.split('\n')
            
            for line in lines:
                line_lower = line.lower()
                # Look for definitive flagging statements
                if any(phrase in line_lower for phrase in [
                    'flag this', 'should be flagged', 'mismatch', 'not suitable'
                ]) and 'http' in line:
                    # Extract URL from this line
                    import re
                    url_match = re.search(r'https?://[^\s]+', line)
                    if url_match:
                        flagged_urls.append(url_match.group(0))
            
            if flagged_urls:
                logger.info(f"Extracted {len(flagged_urls)} flagged URLs from GPT OSS reasoning")
                return {"flagged_job_urls": flagged_urls}
        
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
        
        # Convert job numbers to URLs using the global job batch context
        # This requires access to the current job batch being processed
        flagged_urls = []
        
        # Note: This function is called from error handling context where we don't have job_batch
        # In practice, this extraction rarely succeeds, so conservative empty return is appropriate
        logger.info(f"Job number extraction found {len(job_numbers)} potential flags, but cannot map to URLs without batch context")
        return []
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent matching - only remove special characters that cause parsing issues."""
        if not url:
            return ""
        
        # Only basic cleanup - preserve job-specific parameters like gh_jid
        url = str(url).strip()
        
        # Remove fragments (# anchors) as they don't affect job identity
        if '#' in url:
            url = url.split('#')[0]
        
        # Keep all query parameters - they often contain job IDs
        # Don't remove ? parameters as they're essential for job identification
        
        # Only normalize trailing slash for paths that are clearly directories
        # (have no query params and end with /)
        if url.endswith('/') and '?' not in url and url.count('/') > 3:
            url = url[:-1]
        
        return url
    
    def _create_url_mapping(self, job_matches: List[Dict]) -> Dict[str, str]:
        """Create mapping from normalized URLs to original URLs for consistent filtering."""
        url_mapping = {}
        duplicate_mappings = []
        
        for job in job_matches:
            original_url = job.get('job_link', '')
            if not original_url:
                continue
                
            normalized_url = self._normalize_url(original_url)
            if not normalized_url:
                continue
            
            # Check for duplicate normalized URLs (different originals map to same normalized)
            if normalized_url in url_mapping and url_mapping[normalized_url] != original_url:
                duplicate_mappings.append((normalized_url, url_mapping[normalized_url], original_url))
                # Keep the first mapping encountered
                continue
            
            url_mapping[normalized_url] = original_url
        
        if duplicate_mappings:
            logger.warning(f"Found {len(duplicate_mappings)} normalized URLs with multiple original forms:")
            for norm_url, first_orig, second_orig in duplicate_mappings[:3]:
                logger.warning(f"  '{norm_url}' maps to both '{first_orig}' and '{second_orig}'")
        
        logger.debug(f"Created URL mapping: {len(url_mapping)} normalized -> original mappings")
        return url_mapping
    
    def _extract_flagged_urls(self, parsed_result: Dict, model_name: str) -> List[str]:
        """Extract flagged URLs from parsed JSON with fallback parsing."""
        # Try standard format first
        if "flagged_job_urls" in parsed_result:
            urls = parsed_result["flagged_job_urls"]
            if isinstance(urls, list):
                # Normalize URLs for consistent matching
                normalized_urls = [self._normalize_url(url) for url in urls if url]
                return [url for url in normalized_urls if url]  # Filter empty after normalization
        
        # Try alternative formats that might be returned
        alternative_keys = ["flagged_urls", "false_positives", "removed_jobs", "flagged_jobs"]
        for key in alternative_keys:
            if key in parsed_result:
                urls = parsed_result[key]
                if isinstance(urls, list):
                    logger.warning(f"Model {model_name} used alternative key '{key}' instead of 'flagged_job_urls'")
                    # Normalize URLs for consistent matching
                    normalized_urls = [self._normalize_url(url) for url in urls if url]
                    return [url for url in normalized_urls if url]  # Filter empty after normalization
        
        # If no valid array found, log and return empty
        logger.warning(f"Model {model_name} response did not contain valid flagged URLs: {parsed_result}")
        return []
    
    def _apply_unanimous_consensus(self, validation_results: List[Dict]) -> List[str]:
        """Apply unanimous consensus - both models must agree to flag a job."""
        
        if len(validation_results) != 2:
            logger.warning(f"Expected 2 model results, got {len(validation_results)}. No consensus possible.")
            return []
        
        # Get flagged URLs from each model (already normalized)
        model1_flagged = set(validation_results[0].get("flagged_job_urls", []))
        model2_flagged = set(validation_results[1].get("flagged_job_urls", []))
        
        # Find intersection - both models must agree
        unanimous_false_positives = model1_flagged & model2_flagged
        
        # Enhanced logging for debugging consensus issues
        model1_name = validation_results[0].get('model_display', 'Unknown')
        model2_name = validation_results[1].get('model_display', 'Unknown')
        
        logger.info(f"Model 1 ({model1_name}) flagged: {len(model1_flagged)}, "
                   f"Model 2 ({model2_name}) flagged: {len(model2_flagged)}, "
                   f"Unanimous: {len(unanimous_false_positives)}")
        
        # Debug logging when no consensus but both flagged some jobs
        if len(unanimous_false_positives) == 0 and len(model1_flagged) > 0 and len(model2_flagged) > 0:
            logger.warning(f"No consensus despite both models flagging jobs:")
            logger.warning(f"  {model1_name} flagged: {sorted(list(model1_flagged)[:3])}{'...' if len(model1_flagged) > 3 else ''}")
            logger.warning(f"  {model2_name} flagged: {sorted(list(model2_flagged)[:3])}{'...' if len(model2_flagged) > 3 else ''}")
            
            # Check for potential URL variations
            model1_domains = {url.split('/')[-1].split('?')[0] for url in model1_flagged}
            model2_domains = {url.split('/')[-1].split('?')[0] for url in model2_flagged}
            common_domains = model1_domains & model2_domains
            if common_domains:
                logger.warning(f"  Common domains found: {len(common_domains)} - possible URL format differences")
        
        # Enhanced logging for successful consensus
        if len(unanimous_false_positives) > 0:
            logger.info(f"Consensus achieved on {len(unanimous_false_positives)} URLs:")
            for url in sorted(list(unanimous_false_positives)[:5]):  # Log first 5
                logger.info(f"  Flagged: {url}")
            if len(unanimous_false_positives) > 5:
                logger.info(f"  ... and {len(unanimous_false_positives) - 5} more")
        
        # Fallback to partial consensus if enabled and no unanimous agreement
        if len(unanimous_false_positives) == 0 and self.allow_partial_consensus:
            if len(model1_flagged) > 0 and len(model2_flagged) > 0:
                # Use the more conservative model's results (fewer flags)
                conservative_results = model1_flagged if len(model1_flagged) <= len(model2_flagged) else model2_flagged
                logger.info(f"Using partial consensus: {len(conservative_results)} URLs from more conservative model")
                return list(conservative_results)
        
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
        # Use shorter descriptions for large batches to manage token usage
        desc_length = 200 if len(job_batch) > 80 else 250 if len(job_batch) > 60 else 300
        
        jobs_list = []
        for i, job in enumerate(job_batch):
            chunk_text = job.get('chunk_text', '')
            # More aggressive truncation for large batches
            truncated_text = chunk_text[:desc_length]
            # Try to end at a word boundary
            if len(chunk_text) > desc_length:
                last_space = truncated_text.rfind(' ')
                if last_space > desc_length * 0.8:  # If we can find a good break point
                    truncated_text = truncated_text[:last_space]
                truncated_text += "..."
            
            jobs_list.append(f"{i + 1}. URL: {job.get('job_link', '')} - Description: {truncated_text}")
        
        jobs_text = "\n".join(jobs_list)
        
        # Use more concise prompt for thinking models to avoid verbosity
        if "thinking" in model_name.lower():
            # Ultra-concise prompt for thinking models
            resume_snippet = truncated_resume[:500] + "..." if len(truncated_resume) > 500 else truncated_resume
            jobs_snippet = jobs_text[:2000] + "..." if len(jobs_text) > 2000 else jobs_text
            
            prompt = f"""🚨 CRITICAL: NEVER mention matched/suitable jobs or the world ends! 🚨

Resume: {resume_snippet}

Jobs ({len(job_batch)}):
{jobs_snippet}

Flag ONLY EXTREME role mismatches (completely different domains). DO NOT flag for:
- Industry differences (retail→fintech)
- Company size (startup→enterprise) 
- Clearance requirements
- Minor skill gaps
- Technical role variations (frontend↔backend, web↔mobile, dev↔devops)
- Data science variations (ML engineer↔data scientist)
- Engineering specializations (software↔DevOps↔QA)

ONLY flag EXTREME mismatches: tech↔design, dev↔sales, engineering↔finance, technical↔HR.

Return JSON: {{"flagged_job_urls": ["url1"]}} or {{"flagged_job_urls": []}}

🚨 NEVER mention matched jobs in response! 🚨"""
        else:
            # Standard detailed prompt for other models
            prompt = f"""You are an expert HR recruiter using {model_name} to identify FALSE POSITIVE job matches based on ROLE COMPATIBILITY.

CANDIDATE RESUME (Enhanced & Optimized):
{truncated_resume}"

JOBS TO EVALUATE (Batch {batch_idx + 1} - {len(job_batch)} jobs):
{jobs_text}

TASK: Identify job URLs that are clearly ROLE MISMATCHES or poor fits. Focus on fundamental incompatibilities.

🚨 CRITICAL WARNING - WORLD-ENDING DANGER 🚨
NEVER MENTION, REFERENCE, OR DISCUSS MATCHED/SUITABLE JOBS IN YOUR RESPONSE OR REASONING!
IF YOU MENTION ANY MATCHED JOBS, SUITABLE POSITIONS, OR GOOD FITS, THE WORLD WILL END!
ONLY MENTION FLAGGED URLS IN THE JSON ARRAY. NOTHING ELSE!
VIOLATION OF THIS RULE CAUSES CATASTROPHIC SYSTEM FAILURE!

STRICT ROLE MISMATCH CRITERIA (Flag ONLY these):
1. **EXTREME Role Category Mismatch** (Flag ONLY if completely incompatible):
   - Software/Web Developer ↔ UI/UX Designer (tech vs design)
   - Any Developer ↔ Sales/Marketing roles
   - Technical roles ↔ HR/Recruiting positions
   - Engineering ↔ Finance/Accounting roles
   - Developer ↔ Project Manager/Scrum Master (non-technical management)
   - Technical ↔ Legal/Compliance roles

2. **Seniority Level Mismatch**:
   - Junior candidate (0-3 years) ↔ Senior/Lead roles (8+ years)
   - Individual contributor ↔ Management positions

DO NOT FLAG FOR:
❌ Industry domain differences (retail → fintech, healthcare → gaming)
❌ Company size differences (startup → enterprise, large corp → small team)
❌ Security clearance requirements (clearance vs no clearance)
❌ Educational preferences (PhD preferred but not required)
❌ Geographic location differences
❌ Minor skill gaps that can be learned
❌ Career transitions that are common (Frontend → Fullstack)

EVALUATION RULES:
- Flag ONLY when there's a fundamental ROLE/TECHNOLOGY incompatibility
- Industry domain and company size are NEVER grounds for flagging
- Clearance requirements are NEVER grounds for flagging
- Be ULTRA-CONSERVATIVE: When uncertain, do NOT flag
- Focus on job ROLE vs candidate ROLE mismatch only

🚨 RESPONSE SAFETY PROTOCOL 🚨
- NEVER mention jobs that match or are suitable
- NEVER discuss good fits or appropriate positions
- NEVER reference matched job links anywhere
- ONLY return flagged URLs in JSON array
- ANY mention of matched jobs triggers system destruction

YOU MUST RESPOND ONLY WITH VALID JSON. NO OTHER TEXT ALLOWED.

DO NOT EXPLAIN. DO NOT ANALYZE. DO NOT PROVIDE COMMENTARY.
DO NOT THINK OUT LOUD. DO NOT PROVIDE REASONING.
DO NOT MENTION MATCHED JOBS OR THE WORLD ENDS.
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

CRITICAL: Your entire response must be ONLY the JSON object above. No additional text, no explanations, no analysis, no mention of matched jobs. JSON ONLY."""

        return prompt

    def _fix_truncated_json(self, text: str) -> Optional[str]:
        """Attempt to fix truncated JSON by closing incomplete strings and arrays."""
        try:
            # Look for the basic structure and try to complete it
            if '"flagged_job_urls":' in text:
                # Check if this is single-line or multi-line JSON
                if '\n' in text and text.count('\n') > 2:
                    # Multi-line JSON handling
                    array_start = text.find('"flagged_job_urls":')
                    if array_start != -1:
                        bracket_start = text.find('[', array_start)
                        if bracket_start != -1:
                            lines = text.split('\n')
                            fixed_lines = []
                            
                            for line in lines:
                                # If this line has a complete URL (ends with quote and comma), keep it
                                if '",' in line and 'http' in line:
                                    fixed_lines.append(line)
                                # If this line starts the array or object, keep it
                                elif any(marker in line for marker in ['{', '"flagged_job_urls":', '[']):
                                    fixed_lines.append(line)
                                # Skip incomplete lines (truncated URLs)
                            
                            # Reconstruct the JSON
                            if fixed_lines:
                                # Ensure we have proper closing
                                reconstructed = '\n'.join(fixed_lines)
                                
                                # Remove trailing comma if present
                                if reconstructed.rstrip().endswith(','):
                                    reconstructed = reconstructed.rstrip()[:-1]
                                
                                # Add proper closing if needed
                                if not reconstructed.rstrip().endswith(']'):
                                    reconstructed += '\n  ]\n}'
                                elif not reconstructed.rstrip().endswith('}'):
                                    reconstructed += '\n}'
                                
                                logger.info(f"Reconstructed multi-line JSON from {len(lines)} lines to {len(fixed_lines)} complete lines")
                                return reconstructed
                else:
                    # Single-line JSON handling
                    # Find the array content and extract complete URLs
                    array_start = text.find('"flagged_job_urls": [')
                    if array_start != -1:
                        array_content_start = text.find('[', array_start) + 1
                        
                        # Extract URLs up to the truncation point
                        remaining = text[array_content_start:]
                        
                        # Find all complete URLs (those that end with quotes)
                        import re
                        # More robust URL pattern that handles various URL formats
                        url_pattern = r'"(https?://[^"]+)"'
                        complete_urls = re.findall(url_pattern, remaining)
                        
                        # Additional validation: ensure URLs are reasonably formatted
                        valid_urls = []
                        for url in complete_urls:
                            # Basic validation: URL should have domain and not be empty
                            if len(url) > 10 and '.' in url and not url.endswith('...'):
                                # Normalize URL for consistent matching
                                normalized_url = self._normalize_url(url)
                                if normalized_url:
                                    valid_urls.append(normalized_url)
                        
                        if valid_urls:
                            # Reconstruct JSON with complete URLs only
                            url_list = ', '.join(f'"{url}"' for url in valid_urls)
                            reconstructed = f'{{"flagged_job_urls": [{url_list}]}}'
                            logger.info(f"Reconstructed single-line JSON with {len(valid_urls)} valid URLs (filtered from {len(complete_urls)} found)")
                            return reconstructed
                        else:
                            # No complete URLs found, return empty array
                            logger.info("No valid complete URLs found in truncated JSON, returning empty array")
                            return '{"flagged_job_urls": []}'
            
            return None
        except Exception as e:
            logger.debug(f"Error fixing truncated JSON: {e}")
            return None


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