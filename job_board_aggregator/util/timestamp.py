"""Timestamp utilities for tracking job fetching operations."""

import os
import json
import datetime
import time
from typing import Dict, Optional

from job_board_aggregator.config import LAST_RUN_FILE, logger


def get_last_fetch_time(company_name: str) -> Optional[str]:
    """
    Get the last fetch time for a specific company.

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


def get_last_fetch_time_today(company_name: str) -> Optional[datetime.datetime]:
    """
    Get the last fetch time for today only. Returns None if no fetch today.
    
    Args:
        company_name: Name of the company
        
    Returns:
        Datetime object of last fetch today, or None if no fetch today
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
                        time.sleep(0.01)
                        continue
                    return None
                data = json.loads(content)
            
            last_fetch_timestamp = data.get('companies', {}).get(company_name)
            if not last_fetch_timestamp:
                return None
                
            last_fetch_dt = datetime.datetime.fromisoformat(last_fetch_timestamp)
            today = datetime.date.today()
            
            # Only return the timestamp if it's from today
            if last_fetch_dt.date() == today:
                return last_fetch_dt
            else:
                return None  # Last fetch was on a different day
                
        except (json.JSONDecodeError, ValueError) as e:
            if attempt < max_retries - 1:
                logger.debug(f"JSON error reading file for today check on attempt {attempt + 1}, retrying: {e}")
                time.sleep(0.01 * (attempt + 1))
                continue
            else:
                logger.debug(f"Error reading last fetch time for today after {max_retries} attempts: {e}")
                return None
        except (FileNotFoundError, KeyError) as e:
            logger.debug(f"Error reading last fetch time for today: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading last fetch time for today: {e}")
            return None
    
    return None


def is_first_fetch_today(company_name: str) -> bool:
    """
    Check if this is the first fetch of the day for the given company.
    
    Args:
        company_name: Name of the company
        
    Returns:
        True if this is the first fetch today, False otherwise
    """
    return get_last_fetch_time_today(company_name) is None


def should_process_job_today(company_name: str, job_date: Optional[str]) -> bool:
    """
    Determine if we should process this job based on today's fetch logic:
    - If first fetch today: process all jobs from today
    - If subsequent fetch today: process jobs from today that are newer than last fetch
    
    Args:
        company_name: Name of the company
        job_date: Job's publish or update date in ISO format
        
    Returns:
        True if the job should be processed, False otherwise
    """
    if not job_date:
        # If job has no date, assume it's new to be safe
        return True
        
    try:
        # Parse job date
        job_datetime = datetime.datetime.fromisoformat(job_date)
        if job_datetime.tzinfo is None:
            job_datetime = job_datetime.replace(tzinfo=datetime.timezone.utc)
            
        today = datetime.date.today()
        job_date_only = job_datetime.date()
        
        # Only process jobs from today
        if job_date_only != today:
            return False
            
        # If this is the first fetch today, process all jobs from today
        if is_first_fetch_today(company_name):
            return True
            
        # If subsequent fetch today, only process jobs newer than last fetch
        last_fetch_time = get_last_fetch_time_today(company_name)
        if last_fetch_time:
            return job_datetime > last_fetch_time
        else:
            # Fallback - should not happen but process to be safe
            return True
            
    except Exception as e:
        logger.error(f"Error parsing job date {job_date}: {e}")
        # If we can't parse date, assume it's new to be safe
        return True


def update_fetch_time(company_name: str) -> None:
    """
    Update the last fetch time for a specific company.

    Args:
        company_name: Name of the company
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Create current timestamp in ISO format
            current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            # Load existing data if available
            data: Dict = {}
            if os.path.exists(LAST_RUN_FILE):
                try:
                    with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:  # Handle BOM
                        content = f.read().strip()
                        if content:  # Only parse if file is not empty
                            data = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"JSON error reading file on attempt {attempt + 1}, retrying: {e}")
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    else:
                        logger.warning(f"File corrupted after {max_retries} attempts, starting fresh: {e}")
                        data = {}
            
            # Initialize companies dictionary if not present
            if 'companies' not in data:
                data['companies'] = {}
                
            # Update the company's timestamp
            data['companies'][company_name] = current_time
            
            # Write to temporary file first (atomic operation)
            temp_file = LAST_RUN_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Atomic move (rename) - this is usually atomic on most filesystems
            if os.path.exists(LAST_RUN_FILE):
                backup_file = LAST_RUN_FILE + '.bak'
                os.rename(LAST_RUN_FILE, backup_file)
                try:
                    os.rename(temp_file, LAST_RUN_FILE)
                    # Remove backup if successful
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                except Exception:
                    # Restore from backup if rename failed
                    if os.path.exists(backup_file):
                        os.rename(backup_file, LAST_RUN_FILE)
                    raise
            else:
                os.rename(temp_file, LAST_RUN_FILE)
                
            logger.info(f"Updated last fetch time for {company_name}: {current_time}")
            return  # Success, exit retry loop
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(f"Error updating last fetch time on attempt {attempt + 1}, retrying: {e}")
                time.sleep(0.01 * (attempt + 1))
            else:
                logger.error(f"Error updating last fetch time after {max_retries} attempts: {e}")
                # Clean up any temporary files
                temp_file = LAST_RUN_FILE + '.tmp'
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass


def update_fetch_time_with_timestamp(company_name: str, timestamp: str) -> None:
    """
    Update the last fetch time for a specific company with a given timestamp.
    This is primarily for testing purposes.

    Args:
        company_name: Name of the company
        timestamp: ISO format timestamp string
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Load existing data if available
            data: Dict = {}
            if os.path.exists(LAST_RUN_FILE):
                try:
                    with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:  # Handle BOM
                        content = f.read().strip()
                        if content:  # Only parse if file is not empty
                            data = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"JSON error reading file on attempt {attempt + 1}, retrying: {e}")
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    else:
                        logger.warning(f"File corrupted after {max_retries} attempts, starting fresh: {e}")
                        data = {}
            
            # Initialize companies dictionary if not present
            if 'companies' not in data:
                data['companies'] = {}
                
            # Update the company's timestamp
            data['companies'][company_name] = timestamp
            
            # Write to temporary file first (atomic operation)
            temp_file = LAST_RUN_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Atomic move (rename) - this is usually atomic on most filesystems
            if os.path.exists(LAST_RUN_FILE):
                os.replace(temp_file, LAST_RUN_FILE)
            else:
                os.rename(temp_file, LAST_RUN_FILE)
            
            logger.info(f"Updated fetch time for {company_name}: {timestamp}")
            return
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(f"Error updating fetch time on attempt {attempt + 1}, retrying: {e}")
                time.sleep(0.01 * (attempt + 1))
            else:
                logger.error(f"Failed to update fetch time after {max_retries} attempts: {e}")
                raise


def set_default_start_date(date_str: str) -> bool:
    """
    Set a default start date for all companies without specific timestamps.
    
    Args:
        date_str: Date string in YYYY-MM-DD format or ISO format
        
    Returns:
        True if successful, False otherwise
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Parse the date string
            if 'T' in date_str:
                # ISO format with time
                default_date = datetime.datetime.fromisoformat(date_str)
            else:
                # YYYY-MM-DD format
                default_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                
            # Add UTC timezone if not present
            if default_date.tzinfo is None:
                default_date = default_date.replace(tzinfo=datetime.timezone.utc)
                
            # Convert to ISO format
            iso_date = default_date.isoformat()
            
            # Load existing data if available
            data: Dict = {}
            if os.path.exists(LAST_RUN_FILE):
                try:
                    with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:  # Handle BOM
                        content = f.read().strip()
                        if content:  # Only parse if file is not empty
                            data = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"JSON error reading file for default date on attempt {attempt + 1}, retrying: {e}")
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    else:
                        logger.warning(f"File corrupted after {max_retries} attempts, starting fresh: {e}")
                        data = {}
            
            # Ensure companies dict exists to preserve existing data
            if 'companies' not in data:
                data['companies'] = {}
                
            # Set default start date
            data['default_start_date'] = iso_date
            
            # Write to temporary file first (atomic operation)
            temp_file = LAST_RUN_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Atomic move (rename) - this is usually atomic on most filesystems
            if os.path.exists(LAST_RUN_FILE):
                backup_file = LAST_RUN_FILE + '.bak'
                os.rename(LAST_RUN_FILE, backup_file)
                try:
                    os.rename(temp_file, LAST_RUN_FILE)
                    # Remove backup if successful
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                except Exception:
                    # Restore from backup if rename failed
                    if os.path.exists(backup_file):
                        os.rename(backup_file, LAST_RUN_FILE)
                    raise
            else:
                os.rename(temp_file, LAST_RUN_FILE)
                
            logger.info(f"Set default start date: {iso_date}")
            return True  # Success, exit retry loop
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(f"Error setting default start date on attempt {attempt + 1}, retrying: {e}")
                time.sleep(0.01 * (attempt + 1))
            else:
                logger.error(f"Error setting default start date after {max_retries} attempts: {e}")
                # Clean up any temporary files
                temp_file = LAST_RUN_FILE + '.tmp'
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                return False
    
    return False


def is_job_newer_than_last_fetch(company_name: str, job_date: Optional[str]) -> bool:
    """
    Check if a job is newer than the last fetch for the given company.
    
    Args:
        company_name: Name of the company
        job_date: Job's publish or update date in ISO format
        
    Returns:
        True if the job is newer than the last fetch or if there's no last fetch time
    """
    if not job_date:
        # If job has no date, assume it's new to be safe
        return True
        
    last_fetch = get_last_fetch_time(company_name)
    if not last_fetch:
        # If no last fetch, consider all jobs as new
        return True
    
    try:
        # Parse dates for comparison
        # Handle dates with and without timezone info
        try:
            job_datetime = datetime.datetime.fromisoformat(job_date)
        except ValueError:
            # Fall back to basic parsing without timezone
            if 'T' in job_date:
                date_part = job_date.split('T')[0]
                job_datetime = datetime.datetime.strptime(date_part, '%Y-%m-%d')
            else:
                job_datetime = datetime.datetime.strptime(job_date, '%Y-%m-%d')
        
        # Parse last fetch time
        last_fetch_datetime = datetime.datetime.fromisoformat(last_fetch)
        
        # Add UTC timezone if job_datetime doesn't have one
        if job_datetime.tzinfo is None:
            job_datetime = job_datetime.replace(tzinfo=datetime.timezone.utc)
            
        # Is the job newer?
        return job_datetime > last_fetch_datetime
    except Exception as e:
        logger.error(f"Error comparing job date {job_date} with last fetch: {e}")
        # If we can't parse dates, assume it's new to be safe
        return True