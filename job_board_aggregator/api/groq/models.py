"""
Data models and type definitions for the Groq LLM client.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class ExperienceType(Enum):
    """Types of experience requirements."""
    TOTAL = "total"
    RELEVANT = "relevant" 
    PREFERRED = "preferred"
    MINIMUM = "minimum"


class SkillCategory(Enum):
    """Categories for classifying extracted skills."""
    PROGRAMMING_LANGUAGE = "programming_language"
    FRAMEWORK_LIBRARY = "framework_library"
    DATABASE = "database"
    CLOUD_PLATFORM = "cloud_platform" 
    TOOL_TECHNOLOGY = "tool_technology"
    SOFT_SKILL = "soft_skill"
    TECHNICAL_SKILL = "technical_skill"


@dataclass
class ExperienceData:
    """Structured data for extracted experience requirements."""
    min_experience_years: int
    experience_type: str
    experience_details: str
    experience_extracted: bool
    extraction_confidence: float


@dataclass 
class SkillsData:
    """Structured data for extracted skills."""
    skills: List[str]  # Consolidated list of all skills (max 25)
    skills_extracted: bool
    extraction_confidence: float


@dataclass
class JobSummaryData:
    """Structured data for extracted 5-point job summary."""
    summary_points: List[str]  # Exactly 5 key points summarizing the job
    summary_extracted: bool
    extraction_confidence: float


@dataclass
class CombinedJobData:
    """Combined structured data for all job extractions in a single API call."""
    # Experience data
    min_experience_years: int
    experience_type: str
    experience_details: str
    experience_extracted: bool
    experience_confidence: float
    
    # Skills data
    skills: List[str]  # Consolidated list of all skills (max 25)
    skills_extracted: bool
    skills_confidence: float
    
    # Summary data
    summary_points: List[str]  # Exactly 5 key points summarizing the job
    summary_extracted: bool
    summary_confidence: float
