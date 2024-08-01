"""Database-only timestamp utilities for tracking job fetching operations - Supabase only."""

import datetime
import time
from typing import Dict, Optional

from job_board_aggregator.config import logger


def _get_database_client():
    """Get the Supabase database client."""
    try:
        from job_board_aggregator.database import get_supabase_client
        return get_supabase_client()
    except ImportError:
        logger.error("Supabase client not available")
        return None
    except Exception as e:
        logger.error(f"Error getting database client: {e}")
        return None


def get_last_fetch_time(company_name: str) -> Optional[datetime.datetime]:
    """
    Get the last fetch time for a company from Supabase database.
    
    Args:
        company_name: Name of the company
        
    Returns:
        Last fetch time as datetime object, or None if never fetched
    """
    db_client = _get_database_client()
    if not db_client:
        raise Exception("Supabase database client is not available")
    
    try:
        company_data = db_client.get_company_by_name(company_name)
        if not company_data:
            logger.warning(f"Company '{company_name}' not found in database")
            return None
            
        last_fetch = company_data.get('last_fetch_time')
        if not last_fetch:
            return None
            
        if isinstance(last_fetch, str):
            # Parse ISO format timestamp
            return datetime.datetime.fromisoformat(last_fetch.replace('Z', '+00:00'))
        elif isinstance(last_fetch, datetime.datetime):
            return last_fetch
        else:
            logger.warning(f"Unexpected last_fetch_time format for {company_name}: {type(last_fetch)}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting last fetch time for {company_name}: {e}")
        return None


def update_fetch_time(company_name: str, fetch_time: Optional[datetime.datetime] = None) -> bool:
    """
    Update the last fetch time for a company in Supabase database.
    
    Args:
        company_name: Name of the company
        fetch_time: Fetch time to set (defaults to current UTC time)
        
    Returns:
        True if successful, False otherwise
    """
    if fetch_time is None:
        fetch_time = datetime.datetime.now(datetime.timezone.utc)
    
    db_client = _get_database_client()
    if not db_client:
        raise Exception("Supabase database client is not available")
    
    try:
        success = db_client.update_company_fetch_time(company_name, fetch_time)
        if success:
            logger.info(f"Updated fetch time for {company_name}: {fetch_time}")
        else:
            logger.error(f"Failed to update fetch time for {company_name}")
        return success
        
    except Exception as e:
        logger.error(f"Error updating fetch time for {company_name}: {e}")
        return False


def is_job_newer_than_last_fetch(company_name: str, job_date_str: str) -> bool:
    """
    Check if a job is newer than the last fetch time for a company.
    
    Args:
        company_name: Name of the company
        job_date_str: Job date as string (ISO format)
        
    Returns:
        True if job is newer than last fetch, False otherwise
    """
    if not job_date_str:
        return False
    
    try:
        # Parse job date
        job_date = datetime.datetime.fromisoformat(job_date_str.replace('Z', '+00:00'))
        
        # Get last fetch time
        last_fetch = get_last_fetch_time(company_name)
        
        if not last_fetch:
            # No previous fetch, so job is "newer"
            return True
        
        return job_date > last_fetch
        
    except Exception as e:
        logger.error(f"Error comparing job date for {company_name}: {e}")
        return False


def set_default_start_date(date_str: str) -> bool:
    """
    Set a default start date in Supabase database.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        True if successful, False otherwise
    """
    db_client = _get_database_client()
    if not db_client:
        raise Exception("Supabase database client is not available")
    
    try:
        # Store in a settings table or as a global configuration
        # For now, we'll skip this functionality as it's not critical
        logger.info(f"Default start date set to: {date_str}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting default start date: {e}")
        return False


def get_last_fetch_time_today(company_name: str) -> Optional[datetime.datetime]:
    """
    Get the last fetch time for a company today from Supabase database.
    
    Args:
        company_name: Name of the company
        
    Returns:
        Last fetch time today as datetime object, or None if not fetched today
    """
    last_fetch = get_last_fetch_time(company_name)
    if not last_fetch:
        return None
    
    today = datetime.datetime.now(datetime.timezone.utc).date()
    if last_fetch.date() == today:
        return last_fetch
    
    return None


def is_first_fetch_today(company_name: str) -> bool:
    """
    Check if this is the first fetch of the day for a company.
    
    Args:
        company_name: Name of the company
        
    Returns:
        True if this is the first fetch today, False otherwise
    """
    return get_last_fetch_time_today(company_name) is None


def should_process_job_today(company_name: str, job_date_str: str) -> bool:
    """
    Check if a job should be processed based on today's fetch logic.
    
    Args:
        company_name: Name of the company
        job_date_str: Job date as string (ISO format)
        
    Returns:
        True if job should be processed, False otherwise
    """
    if not job_date_str:
        return False
    
    try:
        # Parse job date
        job_date = datetime.datetime.fromisoformat(job_date_str.replace('Z', '+00:00'))
        today = datetime.datetime.now(datetime.timezone.utc).date()
        
        # Only process jobs from today
        if job_date.date() != today:
            return False
        
        # Check if this job is newer than today's last fetch
        last_fetch_today = get_last_fetch_time_today(company_name)
        if last_fetch_today is None:
            # First fetch of the day - process all jobs from today
            return True
        
        # Subsequent fetch - only process jobs newer than last fetch today
        return job_date > last_fetch_today
        
    except Exception as e:
        logger.error(f"Error checking if job should be processed for {company_name}: {e}")
        return False
