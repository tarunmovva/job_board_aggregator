"""Data models for the server."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class JobMatch(BaseModel):
    """Job match result model."""
    
    job_link: str
    company_name: str
    job_title: str
    location: Optional[str] = None
    first_published: Optional[str] = None
    similarity_score: float
    chunk_text: Optional[str] = None  # Job description text
    min_experience_years: Optional[int] = None  # Minimum experience required for the job
    experience_details: Optional[str] = None  # Experience requirements description


class MatchRequest(BaseModel):
    """Resume matching request model."""
    
    resume_text: str = Field(..., description="Resume text content")
    user_experience: int = Field(..., description="User's years of experience (matches jobs requiring -2 to +1 years of user's experience)")
    keywords: Optional[str] = Field(None, description="Comma-separated keywords")
    location: Optional[str] = Field(None, description="Location filter - single location or comma-separated multiple locations (e.g., 'Remote' or 'Remote,San Francisco,New York')")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    sort_by: str = Field("similarity", description="Sort results by: 'similarity' or 'date'")


class ResumeProcessingInfo(BaseModel):
    """Resume processing information model."""
    
    original_length: int
    enhanced_length: int
    enhancement_used: bool
    parsing_method: Optional[str] = None
    enhancement_method: Optional[str] = None
    filename: Optional[str] = None


class MatchResponseWithProcessing(BaseModel):
    """Enhanced resume match response model with processing info."""
    
    matches: List[JobMatch]
    total_matches: int
    resume_processing: Optional[ResumeProcessingInfo] = None
    # Add extracted information to response
    keywords: Optional[str] = Field(None, description="Keywords used for search (extracted or provided)")
    user_experience: Optional[int] = Field(None, description="Years of experience (extracted or provided)")
    extracted_skills: List[str] = Field(default_factory=list, description="Skills extracted from resume")
    # Cerebras validation metadata
    validation_info: Optional[Dict[str, Any]] = Field(None, description="Cerebras AI validation metadata")


class ResumeParseResponse(BaseModel):
    """Resume parsing response model."""
    
    extracted_text: str
    enhanced_text: str
    processing_info: ResumeProcessingInfo
    success: bool
    message: str
    extracted_experience: Optional[int] = Field(None, description="Extracted years of experience")
    extracted_skills: List[str] = Field(default_factory=list, description="Extracted skills list")


class FetchRequest(BaseModel):
    """Job fetch request model."""
    
    force_refresh: bool = Field(False, description="If True, ignore last fetch time and fetch all jobs")
    limit: Optional[int] = Field(None, description="Limit the number of companies to process")


class DefaultDateRequest(BaseModel):
    """Default date request model."""
    
    date: str = Field(..., description="Default start date in YYYY-MM-DD format")


class MatchResponse(BaseModel):
    """Resume match response model."""
    
    matches: List[JobMatch]
    total_matches: int


class StatsResponse(BaseModel):
    """System statistics response model."""
    
    job_count: int
    status: str


class FetchResponse(BaseModel):
    """Fetch jobs response model."""
    
    jobs_added: int
    message: str


class ResetResponse(BaseModel):
    """Reset database response model."""
    
    message: str


class DefaultDateResponse(BaseModel):
    """Default date response model."""
    
    message: str