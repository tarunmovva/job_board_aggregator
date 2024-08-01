"""Database-only timestamp utilities for tracking job fetching operations - Supabase only."""

import datetime
import time
from typing import Dict, Optional

from job_board_aggregator.config import logger

def _get_database_client():
    """Get database client if database mode is enabled."""
    if USE_DATABASE:
        try:
            from job_board_aggregator.database import get_supabase_client
            return get_supabase_client()
        except ImportError:
            logger.warning("Supabase client not available, falling back to file operations")
            return None
    return None


def get_last_fetch_time(company_name: str) -> Optional[str]:
    """
    Get the last fetch time for a specific company.
    
    Uses database if available, otherwise falls back to file operations.

    Args:
        company_name: Name of the company

    Returns:
        ISO format datetime string or None if no previous fetch
    """
    # Try database first if enabled
    db_client = _get_database_client()
    if db_client:
        try:
            return db_client.get_last_fetch_time(company_name)
        except Exception as e:
            logger.error(f"Database error getting fetch time for {company_name}, falling back to file: {e}")
    
    # Fallback to file operations
    return _get_last_fetch_time_from_file(company_name)


def _get_last_fetch_time_from_file(company_name: str) -> Optional[str]:
    """
    Get the last fetch time for a specific company from file (legacy method).

    Args:
        company_name: Name of the company

    Returns:
        ISO format datetime string or None if no previous fetch
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if not os.path.exists(LAST_RUN_FILE):
                return None
                
            with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:  # Handle BOM
                content = f.read().strip()
                if not content:  # Empty file
                    if attempt < max_retries - 1:
                        time.sleep(0.01)  # Brief wait for file to be written
                        continue
                    return None
                data = json.loads(content)
                
            # First check if this company has a specific timestamp
            company_timestamp = data.get('companies', {}).get(company_name)
            if company_timestamp:
                return company_timestamp
                
            # If no company-specific timestamp, return the default start date
            return data.get('default_start_date')
            
        except (json.JSONDecodeError, ValueError) as e:
            if attempt < max_retries - 1:
                logger.debug(f"JSON error on attempt {attempt + 1}, retrying: {e}")
                time.sleep(0.01 * (attempt + 1))  # Exponential backoff
                continue
            else:
                logger.error(f"Error reading last fetch time after {max_retries} attempts: {e}")
                return None
        except Exception as e:
            logger.error(f"Error reading last fetch time: {e}")
            return None
    
    return None


def update_fetch_time(company_name: str, timestamp: Optional[str] = None) -> bool:
    """
    Update the last fetch time for a specific company.
    
    Uses database if available, otherwise falls back to file operations.

    Args:
        company_name: Name of the company
        timestamp: ISO format timestamp (uses current time if None)
        
    Returns:
        True if successful, False otherwise
    """
    # Try database first if enabled
    db_client = _get_database_client()
    if db_client:
        try:
            return db_client.update_fetch_time(company_name, timestamp)
        except Exception as e:
            logger.error(f"Database error updating fetch time for {company_name}, falling back to file: {e}")
    
    # Fallback to file operations
    return _update_fetch_time_in_file(company_name, timestamp)


def _update_fetch_time_in_file(company_name: str, timestamp: Optional[str] = None) -> bool:
    """
    Update the last fetch time for a specific company in file (legacy method).

    Args:
        company_name: Name of the company
        timestamp: ISO format timestamp (uses current time if None)
        
    Returns:
        True if successful, False otherwise
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Read existing data
            data = {'companies': {}, 'default_start_date': ''}
            if os.path.exists(LAST_RUN_FILE):
                try:
                    with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:
                        content = f.read().strip()
                        if content:
                            data = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Error reading existing timestamp file on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    # If all attempts fail, start with empty data
                    data = {'companies': {}, 'default_start_date': ''}

            # Update the timestamp for this company
            if 'companies' not in data:
                data['companies'] = {}
            
            data['companies'][company_name] = timestamp
            
            # Write back to file with proper error handling
            temp_file = f"{LAST_RUN_FILE}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Atomic move - rename temp file to actual file
            if os.name == 'nt':  # Windows
                if os.path.exists(LAST_RUN_FILE):
                    os.remove(LAST_RUN_FILE)
            os.rename(temp_file, LAST_RUN_FILE)
            
            logger.debug(f"Successfully updated fetch time for {company_name}: {timestamp}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating fetch time for {company_name} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.01 * (attempt + 1))  # Exponential backoff
                continue
            else:
                logger.error(f"Failed to update fetch time for {company_name} after {max_retries} attempts")
                return False
    
    return False


def set_default_start_date(date: str) -> bool:
    """
    Set the default start date for job fetching.
    
    Uses database if available, otherwise falls back to file operations.

    Args:
        date: ISO format date string
        
    Returns:
        True if successful, False otherwise
    """
    # Try database first if enabled
    db_client = _get_database_client()
    if db_client:
        try:
            return db_client.set_default_start_date(date)
        except Exception as e:
            logger.error(f"Database error setting default start date, falling back to file: {e}")
    
    # Fallback to file operations
    return _set_default_start_date_in_file(date)


def _set_default_start_date_in_file(date: str) -> bool:
    """
    Set the default start date for job fetching in file (legacy method).

    Args:
        date: ISO format date string
        
    Returns:
        True if successful, False otherwise
    """
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Read existing data
            data = {'companies': {}, 'default_start_date': ''}
            if os.path.exists(LAST_RUN_FILE):
                try:
                    with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:
                        content = f.read().strip()
                        if content:
                            data = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Error reading existing timestamp file on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    # If all attempts fail, start with empty data
                    data = {'companies': {}, 'default_start_date': ''}

            # Update the default start date
            data['default_start_date'] = date
            
            # Write back to file with proper error handling
            temp_file = f"{LAST_RUN_FILE}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Atomic move - rename temp file to actual file
            if os.name == 'nt':  # Windows
                if os.path.exists(LAST_RUN_FILE):
                    os.remove(LAST_RUN_FILE)
            os.rename(temp_file, LAST_RUN_FILE)
            
            logger.info(f"Successfully set default start date: {date}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting default start date on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.01 * (attempt + 1))  # Exponential backoff
                continue
            else:
                logger.error(f"Failed to set default start date after {max_retries} attempts")
                return False
    
    return False


# The rest of the file remains the same for backward compatibility
def get_last_fetch_time_today(company_name: str) -> Optional[datetime.datetime]:
    """
    Get the last fetch time for today only. Returns None if no fetch today.
    
    Args:
        company_name: Name of the company
        
    Returns:
        Datetime object of last fetch today, or None if no fetch today
    """
    last_fetch_timestamp = get_last_fetch_time(company_name)
    if not last_fetch_timestamp:
        return None
        
    try:
        last_fetch_dt = datetime.datetime.fromisoformat(last_fetch_timestamp)
        today = datetime.date.today()
        
        # Only return the timestamp if it's from today
        if last_fetch_dt.date() == today:
            return last_fetch_dt
        else:
            return None  # Last fetch was on a different day
            
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing timestamp for {company_name}: {e}")
        return None


def is_first_fetch_today(company_name: str) -> bool:
    """
    Check if this is the first fetch for the company today.
    
    Args:
        company_name: Name of the company
        
    Returns:
        True if this is the first fetch today, False otherwise
    """
    return get_last_fetch_time_today(company_name) is None


def should_process_job_today(company_name: str, job_date: Optional[str]) -> bool:
    """
    Determine if a job should be processed based on today's fetching rules.
    
    Args:
        company_name: Name of the company
        job_date: Job date in ISO format
        
    Returns:
        True if job should be processed, False otherwise
    """
    if not job_date:
        return True  # Process jobs without dates
    
    try:
        job_dt = datetime.datetime.fromisoformat(job_date)
        last_fetch_today = get_last_fetch_time_today(company_name)
        
        if last_fetch_today is None:
            # First fetch today - process all jobs from today
            today = datetime.date.today()
            return job_dt.date() >= today
        else:
            # Subsequent fetch today - only process jobs newer than last fetch
            return job_dt > last_fetch_today
            
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing job date {job_date} for {company_name}: {e}")
        return True  # Process if we can't parse the date


def is_job_newer_than_last_fetch(company_name: str, job_date: Optional[str]) -> bool:
    """
    Check if a job is newer than the last fetch time for a company (ORIGINAL LOGIC).
    
    Args:
        company_name: Name of the company
        job_date: Job date in ISO format
        
    Returns:
        True if job is newer than last fetch, False otherwise
    """
    if not job_date:
        return True  # Process jobs without dates
    
    last_fetch_time = get_last_fetch_time(company_name)
    if not last_fetch_time:
        return True  # No previous fetch, process all jobs
    
    try:
        job_dt = datetime.datetime.fromisoformat(job_date)
        last_fetch_dt = datetime.datetime.fromisoformat(last_fetch_time)
        
        return job_dt > last_fetch_dt
        
    except (ValueError, TypeError) as e:
        logger.error(f"Error comparing dates for {company_name}: job_date={job_date}, last_fetch={last_fetch_time}, error={e}")
        return True  # Process if we can't parse dates
