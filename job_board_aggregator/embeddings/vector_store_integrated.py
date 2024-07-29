# Vector store using Pinecone Integrated Embedding (recommended approach).

# This module provides an optimized implementation using Pinecone's integrated embedding
# feature, where Pinecone generates embeddings automatically from structured job data.

# EMBEDDING STRATEGY:
# Instead of embedding raw job descriptions, this implementation creates embeddings from
# structured extracted fields for better matching accuracy:
# - Job Title
# - Experience Details/Requirements  
# - Skills (extracted and validated)
# - Summary Points (5-point structured summary)
# This approach reduces noise and improves semantic matching quality.

# Benefits over custom embedding generation:
# - No need to download/manage large embedding models locally
# - Faster performance with Pinecone's optimized hosted models
# - Cost-effective pay-per-use pricing
# - Simplified architecture and reduced dependencies
# - Automatic consistency between upsert and search embeddings

# Supported Models:
# - llama-text-embed-v2: NVIDIA's state-of-the-art model ($0.16/million tokens)
# - multilingual-e5-large: Microsoft's top-performing model ($0.08/million tokens)
# - pinecone-sparse-english-v0: Sparse model for keyword search ($0.08/million tokens)

# Environment Variables Required:
# - PINECONE_API_KEY: Your Pinecone API key
# - PINECONE_ENVIRONMENT: Pinecone region (default: us-east-1)
# - PINECONE_INDEX_NAME: Index name (default: job-board-index)
# - PINECONE_NAMESPACE: Namespace for jobs (default: jobs)
# - PINECONE_EMBEDDING_MODEL: Model to use (default: llama-text-embed-v2)


import os
from typing import List, Dict, Any, Optional, Tuple
import json
import re
from datetime import datetime
from pinecone import Pinecone

from job_board_aggregator.config import (
    logger, 
    PINECONE_API_KEY, 
    PINECONE_ENVIRONMENT, 
    PINECONE_INDEX_NAME, 
    PINECONE_NAMESPACE
)

# Default embedding model (high-quality NVIDIA model)
DEFAULT_EMBEDDING_MODEL = os.environ.get("PINECONE_EMBEDDING_MODEL", "llama-text-embed-v2")

def _is_date_in_range(job_date: str, start_date: str, end_date: str) -> bool:
    """Check if a job date is within the specified range."""
    try:
        # Handle ISO format with timezone
        if 'T' in job_date:
            job_date = job_date.split('T')[0]
        
        job_dt = datetime.strptime(job_date, '%Y-%m-%d')
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        return start_dt <= job_dt <= end_dt
    except Exception as e:
        logger.warning(f"Could not parse date: {job_date}")
        return False


class VectorStoreIntegrated:
    """Vector database using Pinecone's integrated embedding feature."""
    
    def __init__(self, index_name: str = None, namespace: str = None, embedding_model: str = None):
        """Initialize the Pinecone vector store with integrated embedding."""
        self.index_name = index_name or PINECONE_INDEX_NAME
        self.namespace = namespace or PINECONE_NAMESPACE
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
        
        # Check for API key
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY environment variable is required")
        
        self._client = None
        self._index = None
        
        # Initialize immediately
        self._initialize()
    
    def _initialize(self):
        """Initialize the Pinecone client and index with integrated embedding."""
        try:
            # Initialize Pinecone client
            self._client = Pinecone(api_key=PINECONE_API_KEY)
            logger.info(f"Pinecone client initialized")              # Check if index exists, create if it doesn't
            existing_indexes = [idx['name'] for idx in self._client.list_indexes()]
            if self.index_name not in existing_indexes:
                logger.info(f"Index {self.index_name} not found, creating new index with integrated embedding")
                
                # Create index with integrated embedding (using create_index_for_model)
                self._client.create_index_for_model(
                    name=self.index_name,
                    cloud="aws",
                    region="us-east-1",
                    embed={
                        "model": DEFAULT_EMBEDDING_MODEL,  # llama-text-embed-v2
                        "field_map": {"text": "chunk_text"}  # Map our 'text' field to embedding
                    }
                )
                logger.info(f"Created new Pinecone index with integrated embedding: {self.index_name}")
            else:
                logger.info(f"Using existing Pinecone index: {self.index_name}")
            
            # Get reference to the index
            self._index = self._client.Index(self.index_name)
            
        except Exception as e:
            logger.error(f"Error initializing Pinecone: {e}")
            raise
    
    @property
    def client(self):
        """Get the Pinecone client."""
        if self._client is None:
            self._initialize()
        return self._client
    
    @property
    def index(self):
        """Get the Pinecone index."""
        if self._index is None:
            self._initialize()
        return self._index
    
    def _validate_job_data(self, job_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate job data to ensure all required fields are present before adding to database.
        
        Args:
            job_data: Dictionary containing job information
            
        Returns:
            Tuple of (is_valid, list_of_missing_fields)
        """
        required_core_fields = [
            'job_title',
            'company_name', 
            'job_description'
        ]
        
        required_extraction_fields = [
            # Experience fields
            'min_experience_years',
            'experience_type',
            'experience_details',
            'experience_extracted',
            'experience_confidence',
            
            # Skills fields
            'skills',
            'skills_extracted', 
            'skills_confidence',
            
            # Summary fields
            'summary_points',
            'summary_extracted',
            'summary_confidence'
        ]
        
        missing_fields = []
        
        # Check core fields
        for field in required_core_fields:
            if field not in job_data or not job_data[field]:
                missing_fields.append(f"core.{field}")
        
        # Check extraction fields
        for field in required_extraction_fields:
            if field not in job_data:
                missing_fields.append(f"extraction.{field}")
        
        # Validate data types and content
        if 'skills' in job_data:
            if not isinstance(job_data['skills'], list):
                missing_fields.append("extraction.skills (must be list)")
            elif len(job_data['skills']) == 0:
                missing_fields.append("extraction.skills (empty list)")
        
        if 'summary_points' in job_data:
            if not isinstance(job_data['summary_points'], list):
                missing_fields.append("extraction.summary_points (must be list)")
            elif len(job_data['summary_points']) != 5:
                missing_fields.append(f"extraction.summary_points (must have exactly 5 points, found {len(job_data.get('summary_points', []))})")
        
        if 'min_experience_years' in job_data:
            if not isinstance(job_data['min_experience_years'], (int, float)):
                missing_fields.append("extraction.min_experience_years (must be number)")
        
        # Validate confidence scores
        confidence_fields = ['experience_confidence', 'skills_confidence', 'summary_confidence']
        for field in confidence_fields:
            if field in job_data:
                confidence = job_data[field]
                if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                    missing_fields.append(f"extraction.{field} (must be number between 0.0 and 1.0)")
        
        is_valid = len(missing_fields) == 0
        return is_valid, missing_fields
    
    def add_job(self, job_link: str, job_data: Dict[str, Any]) -> None:
        """Add a job with its text data - Pinecone will generate embeddings automatically."""
        # Validate job data before processing
        is_valid, missing_fields = self._validate_job_data(job_data)
        if not is_valid:
            logger.error(f"Skipping job {job_link} - validation failed. Missing fields: {', '.join(missing_fields)}")
            return
        
        # Create structured embedding text from extracted fields
        embedding_text_parts = []
        
        # Add job title
        if 'job_title' in job_data and job_data['job_title']:
            embedding_text_parts.append(f"Job Title: {job_data['job_title']}")
        
        # Add experience details
        if 'experience_details' in job_data and job_data['experience_details']:
            embedding_text_parts.append(f"Experience Required: {job_data['experience_details']}")
        if 'min_experience_years' in job_data:
            exp_years = job_data['min_experience_years']
            embedding_text_parts.append(f"Experience Required: {exp_years} years of experience required")
        
        # Add skills
        if 'skills' in job_data and isinstance(job_data['skills'], list) and job_data['skills']:
            skills_text = ', '.join(job_data['skills'][:25])  # Limit to first 25 skills
            embedding_text_parts.append(f"Required Skills: {skills_text}")
        
        # Add summary points
        if 'summary_points' in job_data and isinstance(job_data['summary_points'], list) and job_data['summary_points']:
            summary_text = ' '.join(job_data['summary_points'])
            embedding_text_parts.append(f"Job Summary: {summary_text}")
        
        # Combine all parts
        structured_text = '\n'.join(embedding_text_parts)
        
        # If no structured data available, fall back to job description
        if not structured_text.strip():
            job_description = job_data.get('job_description', '')
            if not job_description:
                logger.warning(f"Skipping job {job_link} - no structured data or job description available")
                return
            structured_text = job_description
        
        # Ensure we don't exceed embedding text limits
        max_embedding_length = 30000  # Leave room for metadata and JSON structure
        if len(structured_text.encode('utf-8')) > max_embedding_length:
            # Truncate and add ellipsis
            structured_text = structured_text[:max_embedding_length] + "...[truncated]"
            logger.info(f"Truncated structured embedding text for {job_link} to fit within size limits")
        
        logger.info(f"Created structured embedding text for {job_link} ({len(structured_text)} chars)")
        
        # Prepare minimal metadata to ensure we stay well under 40KB limit
        # Only keep absolutely essential fields with strict size limits
        metadata = {}
        
        # Essential identifiers (with strict limits)
        if 'job_title' in job_data and job_data['job_title']:
            title = str(job_data['job_title'])[:200]  # Limit to 200 chars
            metadata['job_title'] = title
            
        if 'company_name' in job_data and job_data['company_name']:
            company = str(job_data['company_name'])[:100]  # Limit to 100 chars
            metadata['company_name'] = company
            
        if 'location' in job_data and job_data['location']:
            location = str(job_data['location'])[:100]  # Limit to 100 chars
            metadata['location'] = location
            
        # Add job_link as metadata for easy retrieval
        metadata['job_link'] = job_link
        
        # Add timestamps if available (these are typically small)
        if 'first_published' in job_data and job_data['first_published']:
            metadata['first_published'] = str(job_data['first_published'])[:50]
        if 'last_updated' in job_data and job_data['last_updated']:
            metadata['last_updated'] = str(job_data['last_updated'])[:50]
            
        # Add experience data from GROQ extraction (NEW)
        if 'min_experience_years' in job_data:
            metadata['min_experience_years'] = job_data['min_experience_years']
        if 'experience_type' in job_data and job_data['experience_type']:
            metadata['experience_type'] = str(job_data['experience_type'])[:20]  # Limit to 20 chars        if 'experience_details' in job_data and job_data['experience_details']:
            metadata['experience_details'] = str(job_data['experience_details'])[:100]  # Limit to 100 chars        if 'experience_extracted' in job_data:
            metadata['experience_extracted'] = bool(job_data['experience_extracted'])
        if 'experience_confidence' in job_data:
            metadata['experience_confidence'] = float(job_data['experience_confidence'])
              # Add skills data from GROQ extraction (NEW)
        if 'skills_extracted' in job_data:
            metadata['skills_extracted'] = bool(job_data['skills_extracted'])
        if 'skills_confidence' in job_data:
            metadata['skills_confidence'] = float(job_data['skills_confidence'])
              # Add consolidated skills list (as JSON string to save space and maintain structure)
        if 'skills' in job_data and isinstance(job_data['skills'], list) and job_data['skills']:
            # Convert to JSON string and limit size
            skills_json = json.dumps(job_data['skills'][:25])  # Limit to first 25 skills
            if len(skills_json.encode('utf-8')) <= 1000:  # Limit skills field to 1000 bytes
                metadata['skills'] = skills_json
            else:
                # If too long, take fewer skills
                truncated_skills = job_data['skills'][:15]  # Limit to first 15 skills
                metadata['skills'] = json.dumps(truncated_skills)
                
        # Add job summary data from GROQ extraction (NEW)
        if 'summary_extracted' in job_data:
            metadata['summary_extracted'] = bool(job_data['summary_extracted'])
        if 'summary_confidence' in job_data:
            metadata['summary_confidence'] = float(job_data['summary_confidence'])
            
        # Add job summary points (as JSON string to maintain structure)
        if 'summary_points' in job_data and isinstance(job_data['summary_points'], list) and job_data['summary_points']:
            # Convert to JSON string and limit size
            summary_json = json.dumps(job_data['summary_points'][:5])  # Limit to 5 points
            if len(summary_json.encode('utf-8')) <= 1500:  # Limit summary field to 1500 bytes
                metadata['summary_points'] = summary_json
            else:
                # If too long, truncate each point
                truncated_points = []
                for point in job_data['summary_points'][:5]:
                    truncated_point = str(point)[:200] + "..." if len(str(point)) > 200 else str(point)
                    truncated_points.append(truncated_point)
                metadata['summary_points'] = json.dumps(truncated_points)
          
        # Prepare record for Pinecone (using structured text for embedding)
        record = {
            "_id": job_link,
            "chunk_text": structured_text,  # This structured text will be embedded by Pinecone
            **metadata  # Add our minimal metadata
        }
        
        try:
            # Debug: Check final metadata size
            record_json = json.dumps(record)
            record_size = len(record_json.encode('utf-8'))
            logger.info(f"Final record size: {record_size} bytes (limit: 40960 bytes)")
            
            # Final safety check - if still too large, reduce further
            if record_size > 30000:  # Use 30KB as safety margin
                logger.warning(f"Record size {record_size} approaching limit, reducing metadata further")
                  # Keep only the most essential fields
                minimal_record = {
                    "_id": job_link,
                    "chunk_text": job_description,
                    "job_title": metadata.get('job_title', '')[:100],  # Further truncate
                    "company_name": metadata.get('company_name', '')[:50],  # Further truncate
                    "job_link": job_link
                }
                
                record = minimal_record
                record_json = json.dumps(record)
                record_size = len(record_json.encode('utf-8'))
                logger.info(f"Minimal record size: {record_size} bytes")
            
            # Upsert to Pinecone (it will generate embeddings automatically)
            self.index.upsert_records(
                namespace=self.namespace,
                records=[record]
            )
            logger.info(f"Added job to Pinecone: {job_data.get('job_title', 'Unknown')} at {job_data.get('company_name', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error adding job to Pinecone: {e}")
            # Try to reinitialize in case there was a connection issue
            self._initialize()
            try:
                self.index.upsert_records(
                    namespace=self.namespace,
                    records=[record]
                )
                logger.info(f"Added job after reinitialization")
            except Exception as e2:
                logger.error(f"Failed to add job after reinitialization: {e2}")
                raise
    
    def add_jobs_batch(self, jobs_data: List[Dict[str, Any]], batch_size: int = 96) -> int:
        """Add multiple jobs in batches - Pinecone will generate embeddings automatically.
        
        Note: For integrated embedding, max batch size is 96 records.
        
        Args:
            jobs_data: List of dictionaries containing job_link and job_data
            batch_size: Number of jobs to upsert in each batch (max 96 for text)
            
        Returns:
            Number of jobs successfully added
        """
        if not jobs_data:
            return 0
        
        # Ensure batch_size doesn't exceed Pinecone's limit for text embedding
        batch_size = min(batch_size, 96)
        total_added = 0
          # Process jobs in batches
        for i in range(0, len(jobs_data), batch_size):
            batch = jobs_data[i:i + batch_size]
            records_to_upsert = []
            
            for job_item in batch:
                job_link = job_item.get('job_link')
                job_data = job_item.get('job_data', {})
                
                if not job_link:
                    logger.warning(f"Skipping job - missing job_link")
                    continue
                
                # Validate job data before processing
                is_valid, missing_fields = self._validate_job_data(job_data)
                if not is_valid:
                    logger.error(f"Skipping job {job_link} in batch - validation failed. Missing fields: {', '.join(missing_fields)}")
                    continue                
                # Create structured embedding text from extracted fields
                embedding_text_parts = []
                
                # Add job title
                if 'job_title' in job_data and job_data['job_title']:
                    embedding_text_parts.append(f"Job Title: {job_data['job_title']}")
                  # Add experience details
                if 'experience_details' in job_data and job_data['experience_details']:
                    embedding_text_parts.append(f"Experience Required: {job_data['experience_details']}")
                elif 'min_experience_years' in job_data:
                    exp_years = job_data['min_experience_years']
                    embedding_text_parts.append(f"Experience Required: {exp_years} years of experience required")
                
                # Add skills
                if 'skills' in job_data and isinstance(job_data['skills'], list) and job_data['skills']:
                    skills_text = ', '.join(job_data['skills'][:25])  # Limit to first 25 skills
                    embedding_text_parts.append(f"Required Skills: {skills_text}")
                
                # Add summary points
                if 'summary_points' in job_data and isinstance(job_data['summary_points'], list) and job_data['summary_points']:
                    summary_text = ' '.join(job_data['summary_points'])
                    embedding_text_parts.append(f"Job Summary: {summary_text}")
                
                # Combine all parts
                structured_text = '\n'.join(embedding_text_parts)
                
                # If no structured data available, fall back to job description
                job_description = job_data.get('job_description', '')
                if not structured_text.strip():
                    if not job_description:
                        logger.warning(f"Skipping job {job_link} - no structured data or job description available")
                        continue
                    structured_text = job_description
                
                # Ensure we don't exceed embedding text limits
                max_embedding_length = 30000  # Leave room for metadata and JSON structure
                if len(structured_text.encode('utf-8')) > max_embedding_length:
                    # Truncate and add ellipsis
                    structured_text = structured_text[:max_embedding_length] + "...[truncated]"
                
                # Prepare minimal metadata to ensure we stay well under 40KB limit
                metadata = {}
                
                # Essential identifiers (with strict limits)
                if 'job_title' in job_data and job_data['job_title']:
                    title = str(job_data['job_title'])[:200]  # Limit to 200 chars
                    metadata['job_title'] = title
                    
                if 'company_name' in job_data and job_data['company_name']:
                    company = str(job_data['company_name'])[:100]  # Limit to 100 chars
                    metadata['company_name'] = company
                    
                if 'location' in job_data and job_data['location']:
                    location = str(job_data['location'])[:100]  # Limit to 100 chars
                    metadata['location'] = location
                    
                # Add job_link as metadata for easy retrieval
                metadata['job_link'] = job_link
                
                # Add timestamps if available (these are typically small)
                if 'first_published' in job_data and job_data['first_published']:
                    metadata['first_published'] = str(job_data['first_published'])[:50]
                if 'last_updated' in job_data and job_data['last_updated']:
                    metadata['last_updated'] = str(job_data['last_updated'])[:50]
                
                # Add experience data from GROQ extraction (NEW)
                if 'min_experience_years' in job_data:
                    metadata['min_experience_years'] = job_data['min_experience_years']
                if 'experience_type' in job_data and job_data['experience_type']:
                    metadata['experience_type'] = str(job_data['experience_type'])[:20]  # Limit to 20 chars
                if 'experience_details' in job_data and job_data['experience_details']:
                    metadata['experience_details'] = str(job_data['experience_details'])[:100]  # Limit to 100 chars                if 'experience_extracted' in job_data:
                    metadata['experience_extracted'] = bool(job_data['experience_extracted'])
                if 'experience_confidence' in job_data:
                    metadata['experience_confidence'] = float(job_data['experience_confidence'])
                      # Add skills data from GROQ extraction (NEW)
                if 'skills_extracted' in job_data:
                    metadata['skills_extracted'] = bool(job_data['skills_extracted'])
                if 'skills_confidence' in job_data:
                    metadata['skills_confidence'] = float(job_data['skills_confidence'])
                    
                # Add skills lists (as JSON strings to save space and maintain structure)
                skills_fields = [
                    'required_skills', 'preferred_skills', 'technical_skills', 'soft_skills',
                    'tools_technologies', 'programming_languages', 'frameworks_libraries',
                    'databases', 'cloud_platforms'
                ]
                
                for field in skills_fields:
                    if field in job_data and isinstance(job_data[field], list) and job_data[field]:                        # Convert to JSON string and limit size
                        skills_json = json.dumps(job_data[field][:10])  # Limit to first 10 skills per category
                        if len(skills_json.encode('utf-8')) <= 500:  # Limit each skills field to 500 bytes
                            metadata[field] = skills_json
                        else:
                            # If too long, take fewer skills
                            truncated_skills = job_data[field][:5]  # Limit to first 5 skills
                            metadata[field] = json.dumps(truncated_skills)
            
                # Prepare record for Pinecone (using structured text for embedding)
                record = {
                    "_id": job_link,
                    "chunk_text": structured_text,  # This structured text will be embedded by Pinecone
                    **metadata  # Add our minimal metadata
                }
                
                records_to_upsert.append(record)
            
            if records_to_upsert:
                try:
                    # Batch upsert to Pinecone
                    self.index.upsert_records(
                        namespace=self.namespace,
                        records=records_to_upsert
                    )
                    total_added += len(records_to_upsert)
                    logger.info(f"Batch upserted {len(records_to_upsert)} jobs to Pinecone (total: {total_added})")
                except Exception as e:
                    logger.error(f"Error in batch upsert: {e}")
                    # Try individual upserts as fallback
                    for record in records_to_upsert:
                        try:
                            self.index.upsert_records(
                                namespace=self.namespace,
                                records=[record]
                            )
                            total_added += 1
                        except Exception as e2:
                            logger.error(f"Failed to upsert job {record['_id']}: {e2}")
        return total_added
    
    def search_similar(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for jobs with similar content using Pinecone's text search."""
        try:
            # Query Pinecone with text (it will generate embedding automatically)
            results = self.index.search(
                namespace=self.namespace,
                query={
                    "top_k": limit,  # Number of results to return
                    "inputs": {"text": query_text}  # Text input that Pinecone will embed
                },
                fields=["*"]  # Include all fields
            )
            
            # Process results
            job_results = []
            # Extract the actual results from the response
            result_dict = results.to_dict() if hasattr(results, 'to_dict') else {}
            hits = result_dict.get('result', {}).get('hits', [])
            
            for i, hit in enumerate(hits[:limit]):
                # Get similarity score and record data
                similarity_score = hit.get('_score', 0.0)
                record_id = hit.get('_id', '')
                  # Get fields (metadata + text)
                fields = hit.get('fields', {})
                job_description = fields.get('chunk_text', '')
                
                if i < 5:  # Only log the first 5 matches
                    logger.info(f"Match {i+1}: {similarity_score:.4f} - {fields.get('job_title', 'Unknown')} at {fields.get('company_name', 'Unknown')}")
                  # Create job result
                job_result = {
                    'job_link': record_id,
                    'similarity_score': similarity_score,
                    'job_description': job_description
                }
                job_result.update(fields)
                job_results.append(job_result)
            
            return job_results
        except Exception as e:
            logger.error(f"Error searching similar jobs: {e}")
            return []
    
    def search_with_resume(self, resume_text: str, user_experience: int = None, keywords: List[str] = None,
                          locations: List[str] = None, limit: int = 50, date_range: Tuple[str, str] = None) -> List[Dict[str, Any]]:
        """Search for jobs matching a resume using Pinecone's text search."""
        try:
            # Build filter for metadata if needed
            filter_dict = {}
            if date_range:
                start_date, end_date = date_range
                # Add date filtering logic here if needed
                pass
            
            # Query Pinecone with resume text
            results = self.index.search(
                namespace=self.namespace,
                query={
                    "top_k": limit,  # Number of results to return
                    "inputs": {"text": resume_text}  # Text input that Pinecone will embed
                },
                fields=["*"]  # Include all fields
            )
              # Process results
            job_results = []
            # Extract the actual results from the response
            result_dict = results.to_dict() if hasattr(results, 'to_dict') else {}
            hits = result_dict.get('result', {}).get('hits', [])
            
            for hit in hits[:limit]:
                # Get record data
                record_id = hit.get('_id', '')
                fields = hit.get('fields', {})
                score = hit.get('_score', 0.0)
                job_description = fields.get('chunk_text', '')
                
                # Apply keyword filtering if specified
                if keywords:
                    # Search in the structured embedding text (chunk_text)
                    # This contains: Job Title + Skills + Experience + Summary
                    chunk_text = fields.get('chunk_text', '').lower()
                    
                    # Check if any keyword matches
                    keyword_match = any(keyword.lower() in chunk_text for keyword in keywords)
                    if not keyword_match:
                        continue
                
                # Apply location filtering if specified
                if locations:
                    job_location = fields.get('location', '').lower()
                    
                    # Use safer location matching to avoid false positives
                    location_match = False
                    for location_search in locations:
                        search_lower = location_search.lower().strip()
                        
                        # For very short terms, require word boundary matching
                        if len(search_lower) <= 3:
                            pattern = r'\b' + re.escape(search_lower) + r'\b'
                            if re.search(pattern, job_location):
                                location_match = True
                                break
                        else:
                            # For longer terms, substring matching is safer
                            if search_lower in job_location:
                                location_match = True
                                break
                    
                    if not location_match:
                        continue
                  # Apply date filtering
                if date_range:
                    start_date, end_date = date_range
                    job_date = fields.get('first_published', '') or fields.get('last_updated', '')
                    if job_date and not _is_date_in_range(job_date, start_date, end_date):
                        continue
                  # Apply experience filtering if user experience is provided
                if user_experience is not None:
                    job_min_experience = fields.get('min_experience_years')
                    if job_min_experience is not None:
                        try:
                            job_min_exp_int = int(job_min_experience)
                            # Allow jobs within -2 to +0 years of user's experience
                            # For example: if user has 5 years, match jobs requiring 3-5 years
                            min_allowed = user_experience - 2
                            max_allowed = user_experience
                            
                            # Only include jobs within the experience range
                            if job_min_exp_int < min_allowed or job_min_exp_int > max_allowed:
                                continue
                        except (ValueError, TypeError):
                            # If experience data is invalid, skip this filtering
                            pass
                
                job_result = {
                    'job_link': record_id,
                    'similarity_score': score,
                    'job_description': job_description
                }
                job_result.update(fields)
                job_results.append(job_result)
            
            return job_results
            
        except Exception as e:
            logger.error(f"Error in resume search: {e}")
            return []
    
    def get_job(self, job_link: str) -> Optional[Dict[str, Any]]:
        """Get a job from the vector store."""
        try:
            # Fetch from Pinecone
            result = self.index.fetch(
                ids=[job_link],
                namespace=self.namespace            )
            
            if job_link in result.vectors:
                vector_data = result.vectors[job_link]
                metadata = getattr(vector_data, 'metadata', {}) or {}
                
                job_data = {
                    'job_link': job_link,
                    'job_description': metadata.get('job_description', '')
                }
                job_data.update(metadata)
                
                return job_data
            return None
        except Exception as e:
            logger.error(f"Error getting job: {e}")
            return None
    
    def count_jobs(self) -> int:
        """Count the number of jobs in the vector store."""
        try:
            # Get index stats from Pinecone
            stats = self.index.describe_index_stats()
            namespace_stats = stats.get('namespaces', {})
            
            if self.namespace in namespace_stats:
                return namespace_stats[self.namespace]['vector_count']
            else:
                return 0
        except Exception as e:
            logger.error(f"Error counting jobs: {e}")
            return 0
    
    def delete_job(self, job_link: str) -> bool:
        """Delete a job from the vector store."""
        try:
            self.index.delete(
                ids=[job_link],
                namespace=self.namespace            )
            logger.info(f"Deleted job: {job_link}")
            return True
        except Exception as e:
            logger.error(f"Error deleting job: {e}")
            return False
    
    def reset(self) -> bool:
        """Reset the vector store by deleting all jobs."""
        try:
            # Delete all vectors in the namespace
            self.index.delete(delete_all=True, namespace=self.namespace)
            logger.info(f"Reset vector store: deleted all jobs in namespace {self.namespace}")
            return True
        except Exception as e:
            logger.error(f"Error resetting vector store: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the job database."""
        try:
            # Get index stats
            stats = self.index.describe_index_stats()
            
            # Get total vector count from namespace stats
            total_jobs = 0
            namespaces = stats.get('namespaces', {})
            if self.namespace in namespaces:
                total_jobs = namespaces[self.namespace].get('vector_count', 0)
            
            result = {
                'total_jobs': total_jobs,
                'index_name': self.index_name,
                'namespace': self.namespace,
                'total_namespaces': len(namespaces)
            }
            
            # Try to get company breakdown by fetching some sample jobs
            try:
                # Fetch a sample of jobs to get company info
                sample_response = self.index.query(
                    namespace=self.namespace,
                    top_k=min(1000, total_jobs) if total_jobs > 0 else 100,
                    include_metadata=True,
                    vector=[0.0] * 1536  # dummy vector for sampling
                )
                
                # Count jobs by company
                companies = {}
                matches = getattr(sample_response, 'matches', [])
                for match in matches:
                    metadata = getattr(match, 'metadata', {})
                    company = metadata.get('company_name', 'Unknown')
                    companies[company] = companies.get(company, 0) + 1
                
                if companies:
                    result['companies'] = companies
                    
            except Exception as e:
                logger.warning(f"Could not get company breakdown: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                'total_jobs': 0,
                'index_name': self.index_name,
                'namespace': self.namespace,
                'error': str(e)
            }
    
    def list_all_job_links(self) -> List[str]:
        """Get all job links in the database for deduplication."""
        try:
            # Query to get all job IDs (which are job links)
            response = self.index.query(
                namespace=self.namespace,
                top_k=10000,  # Pinecone's max
                include_metadata=False,  # We only need IDs
                vector=[0.0] * 1536  # dummy vector
            )
            
            # Access matches through attribute, not dictionary
            matches = getattr(response, 'matches', [])
            job_links = [match.id for match in matches]
            logger.info(f"Found {len(job_links)} existing job links")
            return job_links
            
        except Exception as e:
            logger.error(f"Error listing job links: {e}")
            return []

    # Legacy method compatibility
    def adaptive_keyword_search(self, keyword_embedding: List[float], resume_embedding: List[float], 
                               keywords: List[str], batch_size: int = 10, 
                               max_batches: int = 50, date_range: Tuple[str, str] = None) -> List[Dict[str, Any]]:
        """Legacy compatibility method - converts to text-based search."""
        logger.warning("adaptive_keyword_search called with embeddings - using simplified text search instead")
        # Convert keywords to search text
        search_text = " ".join(keywords) if keywords else ""
        return self.search_with_resume(search_text, keywords, limit=batch_size * max_batches, date_range=date_range)
