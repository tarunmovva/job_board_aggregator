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
        
        # Available Cerebras models (all 5 tested and verified compatible)
        # Ordered by performance: qwen-3-coder-480b (0.23s) is fastest
        self.available_models = [
            ModelConfig("llama-4-scout-17b-16e-instruct", "Llama 4 Scout"),
            ModelConfig("llama-3.3-70b", "Llama 3.3 70B"),
            ModelConfig("qwen-3-coder-480b", "Qwen 3 Coder 480B"),
            ModelConfig("llama-4-maverick-17b-128e-instruct", "Llama 4 Maverick"),
            ModelConfig("qwen-3-235b-a22b-instruct-2507", "Qwen 3 235B Instruct"),
        ]
        
        # Configuration
        self.max_jobs_per_batch = int(os.getenv('CEREBRAS_MAX_JOBS_PER_BATCH', '290'))
        self.resume_max_chars = int(os.getenv('CEREBRAS_RESUME_MAX_CHARS', '15000'))
        self.require_unanimous = os.getenv('CEREBRAS_REQUIRE_UNANIMOUS', 'true').lower() == 'true'
        
        # JSON Schema for enforcing response format
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
        
        logger.info(f"Initialized CerebrasSchemaValidator with {len(self.available_models)} available models")
    
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
            resume_text: Raw resume text
            
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
                "schema_enforced": True,
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
        available_tokens_for_jobs = 60000  # Conservative estimate within 65K context
        estimated_tokens_per_job = 200  # URL + chunk text
        max_jobs_by_context = available_tokens_for_jobs // estimated_tokens_per_job
        
        # Use the smaller of configured limit or context-based limit
        effective_batch_size = min(self.max_jobs_per_batch, max_jobs_by_context)
        
        logger.info(f"Batch size: {effective_batch_size} jobs per batch")
        
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
        """Validate a batch of jobs with a single Cerebras model using schema enforcement."""
        
        try:
            # Import here to avoid circular imports and ensure it's available
            from cerebras.cloud.sdk import Cerebras
            
            client = Cerebras(api_key=self.api_key)
            
            prompt = self._create_validation_prompt(job_batch, resume_text, model_config.display_name, batch_idx)
            
            # Make API call with strict schema enforcement
            response = client.chat.completions.create(
                model=model_config.name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_completion_tokens=1000,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "false_positive_detection",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
            )
            
            # Parse response - schema guarantees proper format
            content = response.choices[0].message.content
            parsed_result = json.loads(content)
            
            return {
                "model": model_config.name,
                "model_display": model_config.display_name,
                "batch_index": batch_idx,
                "flagged_job_urls": parsed_result["flagged_job_urls"],
                "jobs_processed": len(job_batch),
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Single model validation failed for {model_config.display_name} batch {batch_idx}: {e}")
            return {
                "model": model_config.name,
                "model_display": model_config.display_name,
                "batch_index": batch_idx,
                "flagged_job_urls": [],
                "error": str(e),
                "jobs_processed": len(job_batch),
                "success": False
            }
    
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
        
        logger.info(f"Model 1 flagged: {len(model1_flagged)}, Model 2 flagged: {len(model2_flagged)}, "
                   f"Unanimous: {len(unanimous_false_positives)}")
        
        return list(unanimous_false_positives)
    
    def _truncate_resume(self, resume_text: str) -> str:
        """Truncate resume to fit within token limits."""
        if len(resume_text) <= self.resume_max_chars:
            return resume_text
        
        # Smart truncation at paragraph boundary
        truncated = resume_text[:self.resume_max_chars]
        last_paragraph = truncated.rfind('\n\n')
        if last_paragraph > self.resume_max_chars * 0.8:
            truncated = truncated[:last_paragraph]
        
        return truncated + "\n\n[RESUME TRUNCATED FOR API EFFICIENCY]"
    
    def _create_validation_prompt(self, job_batch: List[Dict], resume_text: str, 
                                 model_name: str, batch_idx: int) -> str:
        """Create validation prompt for schema-enforced false positive detection."""
        
        truncated_resume = self._truncate_resume(resume_text)
        
        # Create job list with minimal data (URL + chunk text only)
        jobs_list = []
        for i, job in enumerate(job_batch):
            jobs_list.append(f"{i + 1}. URL: {job.get('job_link', '')} - Description: {job.get('chunk_text', '')[:300]}...")
        
        jobs_text = "\n".join(jobs_list)
        
        prompt = f"""You are an expert HR recruiter using {model_name} to identify FALSE POSITIVE job matches based on ROLE COMPATIBILITY.

CANDIDATE RESUME:
{truncated_resume}

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

Return ONLY job URLs that represent clear role mismatches. The response will be automatically parsed as JSON."""

        return prompt


# Standalone validation function for easy import
async def validate_jobs_with_cerebras(job_matches: List[Dict], resume_text: str) -> Tuple[List[str], Dict[str, Any]]:
    """
    Convenience function to validate jobs using Cerebras AI.
    
    Args:
        job_matches: List of job dictionaries with job_link and chunk_text
        resume_text: Raw resume text
        
    Returns:
        Tuple of (false_positive_urls, validation_metadata)
    """
    validator = CerebrasSchemaValidator()
    return await validator.validate_job_matches(job_matches, resume_text)