"""API routes for job board aggregator."""

import os
import io
import sys
import tempfile
from typing import List, Dict, Any, Optional
from contextlib import redirect_stdout
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import JSONResponse

from job_board_aggregator.config import logger, reload_environment, get_environment_status
from job_board_aggregator.server.models import (
    MatchRequest, MatchResponse, StatsResponse, 
    FetchResponse, ResetResponse, JobMatch, FetchRequest,
    DefaultDateRequest, DefaultDateResponse, MatchResponseWithProcessing,
    ResumeParseResponse, ResumeProcessingInfo
)
from job_board_aggregator.util.resume_parser import parse_resume_file, ResumeParsingError
from job_board_aggregator.util.resume_enhancer import enhance_resume_text, ResumeEnhancementError
from job_board_aggregator.embeddings.vector_store_integrated import VectorStoreIntegrated
from job_board_aggregator.cli import (
    _handle_fetch_command, _handle_reset_command, _handle_match_resume_command,
    _find_jobs_array, _extract_field
)
from job_board_aggregator.util.timestamp_new import (
    set_default_start_date, get_last_fetch_time_today, is_first_fetch_today, 
    should_process_job_today, update_fetch_time, DatabaseConnectionError, CompanyNotFoundError
)
from job_board_aggregator.util.companies import read_companies_data

# Create API router
router = APIRouter()

# Helper class to mock CLI arguments
class MockArgs:
    """Mock CLI arguments for calling CLI handlers."""
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def get_last_n_business_days(n: int = 2) -> tuple[str, str]:
    """Get the date range for the last N business days (excluding weekends).
    
    Args:
        n: Number of business days to go back (default: 2)
        
    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    today = datetime.now().date()
    business_days_found = 0
    current_date = today
    start_date = None
    
    # Go back day by day until we find N business days
    while business_days_found < n:
        # Check if current_date is a weekday (Monday=0, Sunday=6)
        if current_date.weekday() < 5:  # Monday to Friday
            if business_days_found == 0:
                end_date = current_date  # First business day found is our end date
            business_days_found += 1
            start_date = current_date  # Keep updating start date as we go back
        
        # Move to previous day
        current_date = current_date - timedelta(days=1)
    
    # Convert to string format
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    logger.info(f"Default date range (last {n} business days): {start_date_str} to {end_date_str}")
    return start_date_str, end_date_str


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get system statistics."""
    vector_store = VectorStoreIntegrated()
    job_count = vector_store.count_jobs()
    return {
        "job_count": job_count,
        "status": "operational"
    }


@router.post("/reload-env")
async def reload_env():
    """Reload environment variables from .env file."""
    try:
        if reload_environment():
            status = get_environment_status()
            return {
                "message": "Environment variables reloaded successfully",
                "status": status
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reload environment variables (dotenv not available)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/env-status")
async def get_env_status():
    """Get current environment variable status."""
    try:
        status = get_environment_status()
        return {
            "status": status,
            "message": "Environment status retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch", response_model=FetchResponse)
async def fetch_jobs(request: FetchRequest = Body(default=None)):
    """Fetch jobs using Supabase database only."""
    # Set default request if none provided
    if request is None:
        request = FetchRequest()
    
    try:
        # Read companies from Supabase database only
        companies_list = read_companies_data(limit=request.limit)
        
        # Create mock CLI args for the fetch operation
        args = MockArgs(
            limit=request.limit
        )
        
        logger.info(f"Using Supabase database with {len(companies_list)} companies")
        
    except Exception as e:
        logger.error(f"Failed to read companies from Supabase database: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to read companies from Supabase database: {e}. Make sure your database is properly configured."
        )
    # The CLI fetch command will still respect force_refresh logic internally    # Capture stdout to get job count
    f = io.StringIO()
    jobs_added = 0
    
    try:
        with redirect_stdout(f):
            _handle_fetch_command(args)
        
        # Parse the output to get jobs added
        output = f.getvalue()
        if "Successfully added" in output:
            try:
                jobs_added = int(output.split("Successfully added")[1].split("new")[0].strip())
            except (IndexError, ValueError):
                pass
    
        return {
            "jobs_added": jobs_added,
            "message": output.strip()        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", response_model=ResetResponse)
async def reset_database():
    """Reset the vector database."""
    args = MockArgs()
    
    # Capture stdout
    f = io.StringIO()
    
    try:
        with redirect_stdout(f):
            _handle_reset_command(args)
        
        output = f.getvalue()
        return {"message": output.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match-resume", response_model=MatchResponse)
async def match_resume(request: MatchRequest = Body(...)):
    """DEPRECATED: Match a resume against jobs in the database.
    
    This endpoint is deprecated in favor of /match-resume-upload which provides
    better functionality including automatic resume parsing, text enhancement,
    and skill/experience extraction from uploaded files.
    """
    # Return deprecation notice instead of processing
    logger.warning("Deprecated /match-resume endpoint called. Redirecting to use /match-resume-upload")
    raise HTTPException(
        status_code=410, 
        detail={
            "error": "Endpoint Deprecated",
            "message": "The /match-resume endpoint has been deprecated. Please use /match-resume-upload instead.",
            "recommended_endpoint": "/match-resume-upload",
            "benefits": [
                "Automatic file parsing (PDF, DOCX, TXT)",
                "AI-powered resume enhancement", 
                "Automatic skill and experience extraction",
                "Better matching accuracy"
            ],
            "migration_guide": "Upload your resume file instead of sending text in the request body"
        }
    )


@router.post("/set-default-date", response_model=DefaultDateResponse)
async def set_default_date(request: DefaultDateRequest = Body(...)):
    """Set the default start date for job fetching."""
    try:
        # First validate the date format manually to provide better error messages
        import datetime
        
        if not request.date or not request.date.strip():
            raise HTTPException(status_code=400, detail="Date cannot be empty")
        
        # Try to parse the date to validate format
        try:
            if 'T' in request.date:
                # ISO format with time
                datetime.datetime.fromisoformat(request.date)
            else:
                # YYYY-MM-DD format
                datetime.datetime.strptime(request.date, '%Y-%m-%d')
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format. Expected YYYY-MM-DD format. Error: {str(e)}")
        
        # Now attempt to set the default date
        if set_default_start_date(request.date):
            return {"message": f"Default start date set to {request.date}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to set default start date")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:        # Handle other unexpected errors
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload-environment")
async def reload_env():
    """Reload the environment configuration."""
    try:
        reload_environment()
        return {"message": "Environment reloaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environment-status")
async def env_status():
    """Get the current environment status."""
    try:
        status = get_environment_status()
        return {"status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match-resume-upload", response_model=MatchResponseWithProcessing)
async def match_resume_upload(
    file: UploadFile = File(...),
    user_experience: str = Form(""),
    keywords: str = Form(""),
    location: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    sort_by: str = Form("similarity")
):
    """Match a resume document upload against jobs in the database. 
    
    Returns all matching jobs at once (no pagination).
    If user_experience is not provided or invalid, it will be automatically extracted from the resume.
    If keywords are not provided, skills will be automatically extracted from the resume.
    If start_date and end_date are not provided, defaults to filtering jobs from the last 2 business days.
    """
    try:
        # Convert empty strings to None and validate user_experience
        parsed_user_experience = None
        if user_experience and user_experience.strip():
            try:
                parsed_user_experience = int(user_experience.strip())
            except ValueError:
                # If invalid experience provided, treat as None (will auto-extract later)
                logger.info(f"Invalid user_experience value '{user_experience}' provided, will auto-extract from resume")
                parsed_user_experience = None
        
        # Convert empty strings to None for optional string fields
        parsed_keywords = keywords.strip() if keywords and keywords.strip() else None
        parsed_location = location.strip() if location and location.strip() else None
        parsed_start_date = start_date.strip() if start_date and start_date.strip() else None
        parsed_end_date = end_date.strip() if end_date and end_date.strip() else None
        
        # Read file content
        file_content = await file.read()
        
        # Parse the document
        try:
            parse_result = parse_resume_file(file_content, file.filename or "unknown")
            extracted_text = parse_result['text']
            parsing_info = {
                'parsing_method': parse_result['parsing_method'],
                'filename': parse_result['filename'],
                'original_length': parse_result['original_length']
            }
        except ResumeParsingError as e:
            raise HTTPException(status_code=400, detail=f"Document parsing failed: {str(e)}")
        
        # Log original extracted text
        logger.info("=" * 80)
        logger.info("RESUME PARSING RESULTS")
        logger.info("=" * 80)
        logger.info(f"File: {file.filename}")
        logger.info(f"Original text length: {len(extracted_text)} characters")
        logger.info(f"Parsing method: {parsing_info['parsing_method']}")
        logger.info(f"ORIGINAL EXTRACTED TEXT:")
        logger.info("-" * 60)
        # Show first 500 characters of extracted text
        preview_text = extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
        logger.info(preview_text)
        logger.info("-" * 60)
        
        # Enhance the resume text with Groq
        try:
            logger.info("Starting resume enhancement...")
            enhancement_result = await enhance_resume_text(extracted_text, fallback_on_error=True)
            final_resume_text = enhancement_result['enhanced_text']
            
            # Log enhancement results
            logger.info("RESUME ENHANCEMENT RESULTS")
            logger.info("=" * 80)
            logger.info(f"Enhancement used: {enhancement_result['enhancement_used']}")
            logger.info(f"Enhancement method: {enhancement_result.get('enhancement_method', 'N/A')}")
            logger.info(f"Enhanced text length: {len(final_resume_text)} characters")
            logger.info(f"Length increase: {len(final_resume_text) - len(extracted_text)} characters")
            logger.info(f"ENHANCED RESUME TEXT:")
            logger.info("-" * 60)
            # Show first 500 characters of enhanced text
            enhanced_preview = final_resume_text[:500] + "..." if len(final_resume_text) > 500 else final_resume_text
            logger.info(enhanced_preview)
            logger.info("-" * 60)
            
            # Debug extraction results
            logger.info(f"DEBUG - Raw extracted_experience: {enhancement_result.get('extracted_experience')}")
            logger.info(f"DEBUG - Raw extracted_skills: {enhancement_result.get('extracted_skills')}")
            
            # Use extracted experience if user didn't provide it
            final_user_experience = parsed_user_experience
            if final_user_experience is None and enhancement_result.get('extracted_experience'):
                final_user_experience = enhancement_result['extracted_experience']
                logger.info(f"EXTRACTED EXPERIENCE: {final_user_experience} years")
            elif final_user_experience is None:
                logger.warning("No user experience provided and could not extract from resume, defaulting to 0")
                final_user_experience = 0
            else:
                logger.info(f"USER PROVIDED EXPERIENCE: {final_user_experience} years")
            
            # Use extracted skills if user didn't provide keywords
            final_keywords = parsed_keywords
            if not final_keywords and enhancement_result.get('extracted_skills'):
                # Convert skills list to comma-separated string
                extracted_skills_list = enhancement_result['extracted_skills']
                if extracted_skills_list:
                    final_keywords = ', '.join(extracted_skills_list)
                    logger.info("EXTRACTED SKILLS/KEYWORDS:")
                    logger.info("=" * 80)
                    logger.info(f"Skills count: {len(extracted_skills_list)}")
                    logger.info(f"Skills list: {extracted_skills_list}")
                    logger.info(f"Keywords for search: {final_keywords}")
                    logger.info("=" * 80)
            else:
                if final_keywords:
                    logger.info(f"USER PROVIDED KEYWORDS: {final_keywords}")
                else:
                    logger.info("No keywords provided and none extracted")
                    
            # Create processing info for success path
            processing_info = ResumeProcessingInfo(
                original_length=len(extracted_text),
                enhanced_length=len(final_resume_text),
                enhancement_used=enhancement_result.get('enhancement_used', True),
                parsing_method=parsing_info['parsing_method'],
                enhancement_method=enhancement_result.get('enhancement_method', 'groq'),
                filename=parsing_info['filename']            )
        except ResumeEnhancementError as e:
            logger.warning(f"Resume enhancement failed, using original text: {e}")
            final_resume_text = extracted_text
            final_user_experience = parsed_user_experience or 0
            final_keywords = parsed_keywords
            
            # Set fallback enhancement_result for failed case
            enhancement_result = {
                'extracted_skills': [],
                'extracted_experience': None,
                'enhancement_used': False
            }
            
            processing_info = ResumeProcessingInfo(
                original_length=len(extracted_text),
                enhanced_length=len(extracted_text),
                enhancement_used=False,
                parsing_method=parsing_info['parsing_method'],
                enhancement_method='failed',
                filename=parsing_info['filename']
            )
        
        # Now use the same matching logic as the original endpoint
        large_limit = 1000  # Increased limit since we're returning all results
        
        vector_store = VectorStoreIntegrated()
        job_count = vector_store.count_jobs()
        
        if job_count == 0:
            return MatchResponseWithProcessing(
                matches=[],
                total_matches=0,
                resume_processing=processing_info,
                keywords=final_keywords,
                user_experience=final_user_experience,
                extracted_skills=enhancement_result.get('extracted_skills', [])
            )
        
        logger.info(f"Searching for resume matches (uploaded file: {file.filename}) among {job_count} jobs with user experience: {final_user_experience} years")          # Build filters
        date_range = None
        if parsed_start_date and parsed_end_date:
            # Use user-provided date range
            date_range = (parsed_start_date, parsed_end_date)
            logger.info(f"Using user-provided date range: {parsed_start_date} to {parsed_end_date}")
        else:
            # Apply default date filtering: last 5 business days
            default_start, default_end = get_last_n_business_days(5)
            date_range = (default_start, default_end)
            logger.info(f"No dates provided, applying default filtering: last 5 business days ({default_start} to {default_end})")
        
        keywords_list = None
        if final_keywords:
            keywords_list = [kw.strip() for kw in final_keywords.split(',')]
        
        location_filters = None
        if parsed_location:
            location_filters = [loc.strip() for loc in parsed_location.split(',') if loc.strip()]
        
        # Search using enhanced resume text
        all_results = vector_store.search_with_resume(
            resume_text=final_resume_text,
            user_experience=final_user_experience,
            keywords=keywords_list,
            locations=location_filters,
            limit=large_limit,
            date_range=date_range
        )
        
        logger.info(f"Vector store returned {len(all_results)} results")
        
        # Cerebras AI False Positive Validation
        filtered_results = all_results
        validation_metadata = {}
        
        if len(all_results) > 0 and os.getenv('CEREBRAS_VALIDATION_ENABLED', 'true').lower() == 'true':
            try:
                from job_board_aggregator.api.cerebras.cerebras_validator import validate_jobs_with_cerebras
                
                logger.info(f"Starting Cerebras AI validation for {len(all_results)} jobs")
                
                # Run Cerebras validation with random 2-model consensus
                false_positive_urls, validation_metadata = await validate_jobs_with_cerebras(
                    all_results, extracted_text
                )
                
                # Filter out false positives
                if false_positive_urls:
                    original_count = len(filtered_results)
                    filtered_results = [job for job in filtered_results 
                                      if job.get('job_link') not in false_positive_urls]
                    removed_count = original_count - len(filtered_results)
                    
                    logger.info(f"Cerebras AI removed {removed_count} false positives using models: "
                               f"{validation_metadata.get('models_used', [])}")
                else:
                    logger.info(f"Cerebras AI found no false positives using models: "
                               f"{validation_metadata.get('models_used', [])}")
                    
            except ImportError:
                logger.warning("Cerebras SDK not available, skipping validation. Run: pip install cerebras_cloud_sdk")
                validation_metadata = {"error": "Cerebras SDK not installed"}
            except Exception as e:
                logger.warning(f"Cerebras validation failed, proceeding with original results: {e}")
                validation_metadata = {"error": str(e)}
        else:
            if len(all_results) == 0:
                logger.info("No jobs to validate")
            else:
                logger.info("Cerebras validation disabled")
        
        # Apply sorting to filtered results
        if sort_by and sort_by.lower() == "date":
            filtered_results.sort(
                key=lambda x: x.get('first_published', '') or x.get('last_updated', '') or '',
                reverse=True
            )
        
        # Convert filtered results to response format
        response_matches = []
        for job in filtered_results:
            response_matches.append(JobMatch(
                job_link=job['job_link'],
                company_name=job.get('company_name', ''),
                job_title=job.get('job_title', ''),
                location=job.get('location', ''),
                first_published=job.get('first_published', ''),
                similarity_score=job['similarity_score'],
                chunk_text=job.get('chunk_text', ''),
                min_experience_years=job.get('min_experience_years'),
                experience_details=job.get('experience_details')
            ))
        
        return MatchResponseWithProcessing(
            matches=response_matches,
            total_matches=len(filtered_results),
            resume_processing=processing_info,
            keywords=final_keywords,
            user_experience=final_user_experience,
            extracted_skills=enhancement_result.get('extracted_skills', []),
            validation_info=validation_metadata
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in match_resume_upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-resume", response_model=ResumeParseResponse)
async def parse_resume_only(file: UploadFile = File(...)):
    """Parse and enhance a resume document without job matching."""
    try:
        # Read file content
        file_content = await file.read()
        
        # Parse the document
        try:
            parse_result = parse_resume_file(file_content, file.filename or "unknown")
            extracted_text = parse_result['text']
        except ResumeParsingError as e:            return ResumeParseResponse(
                extracted_text="",
                enhanced_text="",
                processing_info=ResumeProcessingInfo(
                    original_length=0,
                    enhanced_length=0,
                    enhancement_used=False,
                    parsing_method="failed",
                    filename=file.filename
                ),
                success=False,
                message=f"Document parsing failed: {str(e)}",
                extracted_experience=None,
                extracted_skills=[]
            )
        
        # Enhance the resume text
        try:
            enhancement_result = await enhance_resume_text(extracted_text, fallback_on_error=True)
            enhanced_text = enhancement_result['enhanced_text']
            
            processing_info = ResumeProcessingInfo(
                original_length=enhancement_result['original_length'],
                enhanced_length=enhancement_result['enhanced_length'],
                enhancement_used=enhancement_result['enhancement_used'],
                parsing_method=parse_result['parsing_method'],
                enhancement_method=enhancement_result.get('enhancement_method'),
                filename=parse_result['filename']            )
            
            return ResumeParseResponse(
                extracted_text=extracted_text,
                enhanced_text=enhanced_text,
                processing_info=processing_info,
                success=True,
                message="Resume parsed and enhanced successfully",
                extracted_experience=enhancement_result.get('extracted_experience'),
                extracted_skills=enhancement_result.get('extracted_skills', [])
            )
            
        except Exception as e:
            logger.warning(f"Enhancement failed, returning extracted text only: {e}")
            
            processing_info = ResumeProcessingInfo(
                original_length=len(extracted_text),
                enhanced_length=len(extracted_text),
                enhancement_used=False,
                parsing_method=parse_result['parsing_method'],
                enhancement_method="failed",
                filename=parse_result['filename']            )
            
            return ResumeParseResponse(
                extracted_text=extracted_text,
                enhanced_text=extracted_text,
                processing_info=processing_info,
                success=True,
                message="Resume parsed successfully (enhancement failed, using extracted text)",
                extracted_experience=None,
                extracted_skills=[]
            )
    
    except Exception as e:
        logger.error(f"Error in parse_resume_only: {e}")
        raise HTTPException(status_code=500, detail=str(e))