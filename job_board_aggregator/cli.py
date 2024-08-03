"""Command line interface for job board aggregator."""

import argparse
import sys
import os
import csv
from datetime import datetime
from typing import List, Dict, Any, Tuple

from rich.console import Console
from rich.table import Table

from job_board_aggregator.config import logger
from job_board_aggregator.api.client import JobAPIClient
from job_board_aggregator.api.groq_client import GroqLLMClient
from job_board_aggregator.embeddings.vector_store_integrated import VectorStoreIntegrated
from job_board_aggregator.util.resume_parser import parse_resume_file, ResumeParsingError
from job_board_aggregator.util.timestamp_new import (
    get_last_fetch_time, update_fetch_time, is_job_newer_than_last_fetch, 
    set_default_start_date, get_last_fetch_time_today, is_first_fetch_today, 
    should_process_job_today, DatabaseConnectionError, CompanyNotFoundError
)
from job_board_aggregator.util.companies import read_companies_data


def main():
    """Main entry point for the command line interface."""
    parser = argparse.ArgumentParser(description='Job board aggregator tool')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
      # Add the 'fetch' command
    fetch_parser = subparsers.add_parser('fetch', help='Fetch jobs from APIs using Supabase database')
    fetch_parser.add_argument('--limit', type=int, default=None, help='Limit the number of companies to process')
    
    # Add the 'reset' command
    reset_parser = subparsers.add_parser('reset', help='Reset the vector database by deleting all jobs')    # Add the 'match-resume' command
    match_parser = subparsers.add_parser('match-resume', help='Find jobs matching a resume')
    match_parser.add_argument('resume_file', help='Path to the resume file (PDF, DOCX, or TXT)')
    match_parser.add_argument('--user-experience', dest='user_experience', type=int, required=True,
                              help='Your years of experience (matches jobs requiring -2 to +1 years of your experience)')
    match_parser.add_argument('--limit', type=int, default=10, help='Maximum number of results to return')
    match_parser.add_argument('--output', dest='output', default=None, help='Output file path for the results (optional)')
    match_parser.add_argument('--keywords', dest='keywords', default=None, 
                              help='Comma-separated keywords to filter job titles (e.g., "engineer,python,senior")')
    match_parser.add_argument('--start-date', dest='start_date', default=None,
                         help='Start date for filtering (YYYY-MM-DD format)')
    match_parser.add_argument('--end-date', dest='end_date', default=None,
                         help='End date for filtering (YYYY-MM-DD format)')
      # Add the 'set-default-date' command
    default_date_parser = subparsers.add_parser('set-default-date', 
                                              help='Set a default start date for fetching jobs')
    default_date_parser.add_argument('date', help='Default start date (YYYY-MM-DD format)')
    
    # Add the 'stats' command
    stats_parser = subparsers.add_parser('stats', help='Show statistics about the job database')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check if a command was provided
    if not args.command:
        parser.print_help()
        sys.exit(1)
      # Handle commands
    if args.command == 'fetch':
        _handle_fetch_command(args)
    elif args.command == 'reset':
        _handle_reset_command(args)
    elif args.command == 'match-resume':
        _handle_match_resume_command(args)
    elif args.command == 'set-default-date':
        _handle_set_default_date_command(args)
    elif args.command == 'stats':
        _handle_stats_command(args)
    else:
        parser.print_help()
        sys.exit(1)


def _handle_fetch_command(args):
    """Handle the 'fetch' command using Supabase database only."""
    # Initialize components
    vector_store = VectorStoreIntegrated()
    api_client = JobAPIClient()
    
    # Initialize Groq API client
    try:
        groq_client = GroqLLMClient()
        logger.info("Groq API client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Groq API client: {e}")
        print(f"Error: Failed to initialize Groq API client. Please check your API key in .env file.")
        sys.exit(1)
    
    # Read companies from Supabase database only
    try:
        companies = read_companies_data(limit=args.limit)
        logger.info(f"Read {len(companies)} companies from Supabase database")
    except Exception as e:
        logger.error(f"Error reading companies from database: {e}")
        print(f"Error: Failed to read companies from Supabase database. {e}")
        print("Make sure your Supabase database is properly configured and accessible.")
        sys.exit(1)
    
    jobs_added = 0
    for company_name, api_endpoint in companies:
        # Fetch jobs from the API
        api_response = api_client.fetch_jobs(company_name, api_endpoint)
        
        if not api_response:
            continue
          # Find the jobs array in the response
        jobs_array = _find_jobs_array(api_response)
        logger.info(f"Found {len(jobs_array)} jobs for {company_name}")
        
        # Get last fetch time for this company with improved error handling
        try:
            last_fetch_time = get_last_fetch_time(company_name)
            if last_fetch_time:
                logger.info(f"Last fetch for {company_name} was at {last_fetch_time}")
            else:
                logger.info(f"No previous fetch record for {company_name}")
        except CompanyNotFoundError as e:
            logger.warning(f"Skipping {company_name}: {e}")
            continue
        except DatabaseConnectionError as e:
            logger.error(f"Skipping {company_name} due to database connectivity issues: {e}")
            continue
        
        # Process each job
        new_jobs_processed = 0
        for job in jobs_array:            # Extract job link
            job_link = _extract_field(job, ['absolute_url', 'url', 'link', 'job_url', 'apply_url'])
            
            if not job_link:
                logger.warning(f"Skipping job from {company_name} because no job link was found")
                continue
            
            # Extract other fields
            job_title = _extract_field(job, ['title', 'job_title', 'position', 'name'])
            company = job.get('company_name', company_name)
            
            # Handle nested location field
            location = ""
            if "location" in job and isinstance(job["location"], dict) and "name" in job["location"]:
                location = job["location"]["name"]
            else:
                location = _extract_field(job, ['location', 'job_location', 'city'])
            
            # Extract dates
            first_published = _extract_field(job, ['first_published'])
            last_updated = _extract_field(job, ['updated_at', 'last_updated'])
              # ORIGINAL LOGIC: Skip if job is older than last fetch time
            job_date = first_published or last_updated
            if last_fetch_time and not is_job_newer_than_last_fetch(last_fetch_time, job_date):
                logger.info(f"Skipping job {job_title} from {company} because it's not newer than the last fetch")
                continue
              # Extract job description
            job_description = _extract_field(job, ['content', 'description', 'summary', 'job_description'])
            
            if not job_description:
                logger.warning(f"Skipping job {job_title} from {company} because no job description was found")
                continue
            
            # Extract all job data (experience, skills, summary) using Groq in single API call
            logger.info(f"Extracting job data (experience, skills, summary) for: {job_title}")
            job_extraction_data = groq_client.extract_all_job_data(job_description, job_title)
            
            # Log extraction results
            experience_years = job_extraction_data.get('min_experience_years', 'N/A')
            skills_count = len(job_extraction_data.get('skills', [])) if isinstance(job_extraction_data.get('skills'), list) else 0
            summary_points_count = len(job_extraction_data.get('summary_points', [])) if isinstance(job_extraction_data.get('summary_points'), list) else 0
            logger.info(f"Job data extraction completed for {job_title}: {experience_years} years experience, {skills_count} skills, {summary_points_count} summary points")
            
            # Prepare job data (no local embedding generation needed - Pinecone does it)
            job_data = {
                'job_link': job_link,
                'job_title': job_title,
                'company_name': company,
                'location': location,
                'first_published': first_published,
                'last_updated': last_updated,
                'job_description': job_description            }
            
            # Add all extracted data from Groq (experience, skills, summary)
            job_data.update(job_extraction_data)
            
            # Store in vector database (Pinecone will generate embeddings from job_description)
            try:
                vector_store.add_job(job_link, job_data)
                jobs_added += 1
                new_jobs_processed += 1
            except Exception as e:
                logger.error(f"Failed to add job {job_title} to database: {e}")
                logger.info(f"Skipping job {job_title} and continuing with next job...")
                continue
        
        # Update the last fetch time for this company
        update_fetch_time(company_name)
        logger.info(f"Processed {new_jobs_processed} new jobs for {company_name}")
    
    logger.info(f"Added {jobs_added} new jobs to the vector store")
    print(f"Successfully added {jobs_added} new jobs to the database")


def _handle_fetch_command_today_based(args):
    """Handle fetch command with TODAY-BASED logic (for /api/fetch-companies) using Supabase database only."""
    # Initialize components
    vector_store = VectorStoreIntegrated()
    api_client = JobAPIClient()
      # Initialize Groq API client
    try:
        groq_client = GroqLLMClient()
        logger.info("Groq API client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Groq API client: {e}")
        print(f"Error: Failed to initialize Groq API client. Please check your API key in .env file.")
        sys.exit(1)
    
    # Read companies from Supabase database only
    try:
        companies = read_companies_data(limit=getattr(args, 'limit', None))
        logger.info(f"Read {len(companies)} companies from Supabase database")
    except Exception as e:
        logger.error(f"Error reading companies from database: {e}")
        print(f"Error: Failed to read companies from Supabase database. {e}")
        return {}
    
    jobs_added = 0
    results = {}
    
    for company_name, api_endpoint in companies:
        try:
            # Fetch jobs from the API
            api_response = api_client.fetch_jobs(company_name, api_endpoint)
            
            if not api_response:
                results[company_name] = {
                    "status": "error",
                    "message": "Failed to fetch jobs from API",
                    "jobs_processed": 0,
                    "fetch_type": "error"
                }
                continue
            
            # Find the jobs array in the response
            jobs_array = _find_jobs_array(api_response)
            logger.info(f"Found {len(jobs_array)} jobs for {company_name}")
            
            # Get last fetch time for this company (TODAY-BASED LOGIC)
            last_fetch_time = get_last_fetch_time(company_name)
            last_fetch_today = get_last_fetch_time_today(company_name)
            is_first_today = is_first_fetch_today(company_name)
            
            fetch_type = "first_fetch_today" if is_first_today else "incremental_today"
            
            if is_first_today:
                logger.info(f"First fetch of the day for {company_name} - will process ALL jobs from today")
            else:
                logger.info(f"Subsequent fetch for {company_name} - last fetch today at {last_fetch_today.strftime('%H:%M:%S') if last_fetch_today else 'unknown'}")
            
            if last_fetch_time:
                logger.info(f"Overall last fetch for {company_name} was at {last_fetch_time}")
            else:
                logger.info(f"No previous fetch record for {company_name}")
              # Process each job
            new_jobs_processed = 0
            skipped_not_today = 0
            skipped_already_fetched = 0
            
            for job in jobs_array:
                # Extract job link
                job_link = _extract_field(job, ['absolute_url', 'url', 'link', 'job_url', 'apply_url'])
                
                if not job_link:
                    logger.warning(f"Skipping job from {company_name} because no job link was found")
                    continue
                
                # Extract other fields
                job_title = _extract_field(job, ['title', 'job_title', 'position', 'name'])
                company = job.get('company_name', company_name)
                
                # Handle nested location field
                location = ""
                if "location" in job and isinstance(job["location"], dict) and "name" in job["location"]:
                    location = job["location"]["name"]
                else:
                    location = _extract_field(job, ['location', 'job_location', 'city'])
                  # Extract dates
                first_published = _extract_field(job, ['first_published'])
                last_updated = _extract_field(job, ['updated_at', 'last_updated'])
                    # TODAY-BASED LOGIC: Apply today's fetch logic
                job_date = first_published or last_updated
                if not should_process_job_today(company_name, job_date):
                    if job_date:
                        try:
                            job_dt = datetime.fromisoformat(job_date)
                            if job_dt.date() != datetime.now().date():
                                skipped_not_today += 1
                                logger.debug(f"Skipping job {job_title} - not from today")
                            else:
                                skipped_already_fetched += 1
                                logger.debug(f"Skipping job {job_title} - already fetched today")
                        except:
                            skipped_not_today += 1
                            logger.debug(f"Skipping job {job_title} - date parsing issue")
                    continue
                    
                # Extract job description
                job_description = _extract_field(job, ['content', 'description', 'summary', 'job_description'])
                
                if not job_description:
                    logger.warning(f"Skipping job {job_title} from {company} because no job description was found")
                    continue
                
                # Extract all job data (experience, skills, summary) using Groq in single API call
                logger.info(f"Extracting job data (experience, skills, summary) for: {job_title}")
                job_extraction_data = groq_client.extract_all_job_data(job_description, job_title)
                
                # Log extraction results
                experience_years = job_extraction_data.get('min_experience_years', 'N/A')
                skills_count = len(job_extraction_data.get('skills', [])) if isinstance(job_extraction_data.get('skills'), list) else 0
                summary_points_count = len(job_extraction_data.get('summary_points', [])) if isinstance(job_extraction_data.get('summary_points'), list) else 0
                logger.info(f"Job data extraction completed for {job_title}: {experience_years} years experience, {skills_count} skills, {summary_points_count} summary points")
                
                # Prepare job data (no local embedding generation needed - Pinecone does it)
                job_data = {
                    'job_link': job_link,
                    'job_title': job_title,
                    'company_name': company,
                    'location': location,
                    'first_published': first_published,                    'last_updated': last_updated,
                    'job_description': job_description
                }
                
                # Add all extracted data from Groq (experience, skills, summary)
                job_data.update(job_extraction_data)
                
                # Store in vector database (Pinecone will generate embeddings from job_description)
                try:
                    vector_store.add_job(job_link, job_data)
                    jobs_added += 1
                    new_jobs_processed += 1
                except Exception as e:
                    logger.error(f"Failed to add job {job_title} to database: {e}")
                    logger.info(f"Skipping job {job_title} and continuing with next job...")
                    continue
              # Update the last fetch time for this company
            update_fetch_time(company_name)
            
            # Store results for this company
            if is_first_today:
                message = f"Processed {new_jobs_processed} jobs (first fetch of day)"
            elif last_fetch_today:
                message = f"Processed {new_jobs_processed} jobs (incremental after {last_fetch_today.strftime('%H:%M:%S')})"
            else:
                message = f"Processed {new_jobs_processed} jobs (incremental)"
                
            results[company_name] = {
                "status": "success",
                "fetch_type": fetch_type,
                "jobs_processed": new_jobs_processed,
                "jobs_skipped_not_today": skipped_not_today,
                "jobs_skipped_already_fetched": skipped_already_fetched,
                "message": message
            }
            
            # Log detailed summary for this company
            fetch_type_desc = "first fetch of the day" if is_first_today else "incremental fetch"
            logger.info(f"Fetch complete for {company_name} ({fetch_type_desc}):")
            logger.info(f"  - New jobs processed: {new_jobs_processed}")
            logger.info(f"  - Skipped (not today): {skipped_not_today}")
            logger.info(f"  - Skipped (already fetched today): {skipped_already_fetched}")
            
        except Exception as e:
            results[company_name] = {
                "status": "error",
                "message": str(e),
                "jobs_processed": 0,
                "fetch_type": "error"
            }
    
    logger.info(f"Added {jobs_added} new jobs to the vector store")
    print(f"Successfully added {jobs_added} new jobs to the database")
    
    return results



def _find_jobs_array(response):
    """Find the jobs array in the response."""
    # Common names for the jobs array
    possible_keys = ['jobs', 'data', 'results', 'items', 'positions']
    
    # Check if any of the common keys are in the top level
    for key in possible_keys:
        if key in response and isinstance(response[key], list):
            return response[key]
    
    # Check one level deeper
    for key, value in response.items():
        if isinstance(value, dict):
            for inner_key in possible_keys:
                if inner_key in value and isinstance(value[inner_key], list):
                    return value[inner_key]
    
    return []


def _extract_field(job, possible_keys):
    """Extract a field from a job dictionary using a list of possible keys."""
    for key in possible_keys:
        if key in job:
            value = job[key]
            if isinstance(value, (str, int, float)):
                return str(value)
            elif isinstance(value, dict):
                # If it's a nested object, try to extract a string from it
                for inner_key, inner_value in value.items():
                    if isinstance(inner_value, (str, int, float)):
                        return str(inner_value)
    
    return ""


def _is_date_in_range(date_str: str, start_date: str, end_date: str) -> bool:
    """Check if a date string is within a given range."""
    if not date_str:
        return False
        
    try:
        from datetime import datetime
        
        # Simple approach: just extract YYYY-MM-DD from the date string
        if 'T' in date_str:
            # For ISO format dates like "2025-04-23T11:23:17-04:00"
            # Just extract the date part (before the 'T')
            date_part = date_str.split('T')[0]
            try:
                date_obj = datetime.strptime(date_part, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Could not parse date part from cli: {date_part}")
                return False
        else:
            # For simple date formats like "2025-04-23"
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Could not parse date part from cli: {date_str}")
                return False
        
        # Parse start and end dates
        start_obj = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
        end_obj = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None
        
        # Check if date is in range
        if start_obj and date_obj < start_obj:
            return False
        if end_obj and date_obj > end_obj:
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error checking date range: {e}")
        return False

def _handle_reset_command(args):
    """Handle the 'reset' command."""
    vector_store = VectorStoreIntegrated()
    
    try:
        # Reset vector store
        job_count = vector_store.count_jobs()
        success = vector_store.reset()
        
        if success:
            print(f"Vector database has been reset - {job_count} jobs deleted")
        else:
            print("Failed to reset vector database")
    except Exception as e:
        logger.error(f"Error resetting vector database: {e}")
        print(f"Error: {e}")
        sys.exit(1)


def _handle_match_resume_command(args, is_server_call=False):
    """Handle the 'match-resume' command using Pinecone integrated embedding."""
    console = Console()
    
    # Check if resume file exists
    if not os.path.isfile(args.resume_file):
        console.print(f"Error: Resume file not found: {args.resume_file}", style="bold red")
        if not is_server_call:
            sys.exit(1)
        return []

    try:
        # Initialize components
        vector_store = VectorStoreIntegrated()
        
        # Check if we have jobs in the vector store
        job_count = vector_store.count_jobs()
        if job_count == 0:
            console.print("No jobs found in the database. Please fetch jobs first.", style="bold red")
            if not is_server_call:
                sys.exit(1)
            return []

        console.print(f"Analyzing resume: {args.resume_file}", style="bold blue")
        
        # Extract text from resume using the same parser as the API
        try:
            with open(args.resume_file, 'rb') as f:
                file_content = f.read()
            parse_result = parse_resume_file(file_content, os.path.basename(args.resume_file))
            resume_text = parse_result['text']
        except ResumeParsingError as e:
            console.print(f"Error parsing resume: {e}", style="bold red")
            if not is_server_call:
                sys.exit(1)
            return []
        except Exception as e:
            console.print(f"Error reading resume file: {e}", style="bold red")
            if not is_server_call:
                sys.exit(1)
            return []
            
        if not resume_text:
            console.print("Error: Could not extract text from resume", style="bold red")
            if not is_server_call:
                sys.exit(1)
            return []
        
        console.print(f"Using Pinecone integrated embedding for resume text ({len(resume_text)} characters)...", style="bold blue")
        
        # Prepare search text
        search_text = resume_text
        if args.keywords:
            keywords = [kw.strip() for kw in args.keywords.split(',')]
            console.print(f"Adding keywords to search: {', '.join(keywords)}", style="bold blue")
            search_text = f"{resume_text}\n\nPreferred keywords: {' '.join(keywords)}"
        
        # Search for matching jobs using Pinecone integrated embedding        console.print(f"Searching for matching jobs among {job_count} jobs with {args.user_experience} years experience (matching jobs requiring {args.user_experience - 2} to {args.user_experience + 1} years)...", style="bold blue")
          # Build date range filter
        date_range = None
        if args.start_date and args.end_date:
            console.print(f"Filtering by date range: {args.start_date} to {args.end_date}", style="bold blue")
            date_range = (args.start_date, args.end_date)
          # Use Pinecone's integrated search (no need for local embeddings)
        matching_jobs = vector_store.search_with_resume(
            resume_text=search_text,
            user_experience=args.user_experience,
            limit=args.limit,
            date_range=date_range
        )
        
        # Debug logging for server calls
        if is_server_call:
            logger.info(f"CLI search returned {len(matching_jobs)} jobs")
            if matching_jobs:
                logger.info(f"First job: {matching_jobs[0].get('job_title', 'N/A')} at {matching_jobs[0].get('company_name', 'N/A')}")
            else:
                logger.info("No jobs returned from vector store search")
        
        if not matching_jobs:
            console.print("No matching jobs found meeting your criteria.", style="bold yellow")
            if not is_server_call:
                sys.exit(0)
            return []
        
        console.print(f"Found {len(matching_jobs)} matching jobs", style="bold green")
        
        # Display results
        _display_matching_jobs(matching_jobs, console)
        
        # Export to CSV if requested
        if args.output:
            _export_matching_jobs_to_csv(matching_jobs, args.output, console)
        
        return matching_jobs
        
    except Exception as e:
        logger.error(f"Error matching resume: {e}")
        console.print(f"Error: {e}", style="bold red")
        if not is_server_call:
            sys.exit(1)
        return []


def _display_matching_jobs(results, console):
    """Display matching jobs in a table with enhanced keyword information."""
    if not results:
        console.print("No matching jobs found.", style="bold yellow")
        return
        
    table = Table(title="Jobs Matching Your Resume")
      # Add columns
    table.add_column("Match %", style="cyan", justify="right")
    table.add_column("Company", style="green")
    table.add_column("Job Title", style="yellow")
    table.add_column("Location", style="magenta")
    table.add_column("Min Exp", style="red", justify="right")  # New experience column
    
    # Add keyword match columns if available
    has_keyword_data = any('keyword_matches' in job for job in results)
    if has_keyword_data:
        table.add_column("KW Matches", style="bright_cyan", justify="right")
    
    table.add_column("Date Published", style="blue")
    table.add_column("Job Link", style="blue")
    
    # Add rows
    for job in results:
        match_percent = f"{job['similarity_score'] * 100:.1f}%"
        
        # Add original score info if available 
        if 'original_score' in job and job['original_score'] != job['similarity_score']:
            base_percent = job['original_score'] * 100
            match_percent = f"{job['similarity_score'] * 100:.1f}% (+{(job['similarity_score'] - job['original_score']) * 100:.1f}%)"
          # Use first_published if available, otherwise last_updated
        publish_date = job.get('first_published', '') or job.get('last_updated', '')
        publish_date = publish_date if publish_date else "N/A"
        
        # Format experience information
        min_exp = job.get('min_experience_years')
        exp_display = f"{min_exp}y" if min_exp is not None else "N/A"
        
        # Create row data
        row_data = [
            match_percent,
            job.get('company_name', ''),
            job.get('job_title', ''),
            job.get('location', '') or "Remote/Not Specified",
            exp_display,  # Add experience column
        ]
        
        # Add keyword match count if available
        if has_keyword_data:
            row_data.append(str(job.get('keyword_matches', 0)))
        
        # Add remaining columns
        row_data.extend([
            publish_date,
            job.get('job_link', '')
        ])
        
        table.add_row(*row_data)
    
    console.print(table)
    console.print(f"Total matching jobs found: {len(results)}", style="bold green")


def _export_matching_jobs_to_csv(results, output_path, console):
    """Export matching jobs to a CSV file with enhanced keyword information."""
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
              # Create header with keyword columns if available
            has_keyword_data = any('keyword_matches' in job for job in results)
            
            header = [
                'Match %', 'Original Match %' if has_keyword_data else '', 
                'Keyword Matches' if has_keyword_data else '', 
                'Company', 'Job Title', 'Location', 'Min Experience Years', 'Experience Details',
                'Date Published', 'Date Updated', 'Job Link', 'Job Description'
            ]
            
            # Remove empty headers
            header = [h for h in header if h]
            writer.writerow(header)
            
            # Write job data
            for job in results:
                # Format percentages
                match_percent = f"{job['similarity_score'] * 100:.1f}%"
                
                # Prepare row data
                row = []
                
                # Add match percentages
                row.append(match_percent)
                
                # Add original percentage if available
                if has_keyword_data:
                    original_percent = f"{job.get('original_score', 0) * 100:.1f}%"
                    row.append(original_percent)
                    row.append(str(job.get('keyword_matches', 0)))
                  # Add remaining data
                row.extend([
                    job.get('company_name', ''),
                    job.get('job_title', ''),
                    job.get('location', '') or "Remote/Not Specified",
                    job.get('min_experience_years', 'N/A'),  # Add experience data
                    job.get('experience_details', 'N/A'),  # Add experience details
                    job.get('first_published', '') or "N/A",
                    job.get('last_updated', '') or "N/A",
                    job.get('job_link', ''),
                    job.get('job_description', '')[:1000] + "..." if len(job.get('job_description', '')) > 1000 else job.get('job_description', '')
                ])
                
                writer.writerow(row)
        
        console.print(f"CSV report saved to {output_path}", style="bold green")
    except Exception as e:
        logger.error(f"Error exporting to CSV: {e}")
        console.print(f"Error exporting to CSV: {e}", style="bold red")


def _handle_set_default_date_command(args):
    """Handle the 'set-default-date' command."""
    console = Console()
    date_str = args.date
    
    try:
        # Validate date format
        datetime.strptime(date_str, '%Y-%m-%d')
        
        # Set the default start date
        if set_default_start_date(date_str):
            console.print(f"Default start date set to [bold green]{date_str}[/bold green]")
        else:
            console.print("Failed to set default start date", style="bold red")
            sys.exit(1)
    except ValueError:
        console.print(f"Invalid date format: {date_str}. Please use YYYY-MM-DD format.", style="bold red")
        sys.exit(1)

def _handle_stats_command(args):
    """Handle the 'stats' command to show database statistics."""
    console = Console()
    
    try:
        vector_store = VectorStoreIntegrated()
        
        # Get basic stats
        console.print("\n[bold blue]Job Database Statistics[/bold blue]")
        console.print("=" * 50)
        
        # Get total count
        stats = vector_store.get_stats()
        total_jobs = stats.get('total_jobs', 0)
        
        # Create a table for the stats
        table = Table(title="Database Overview")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        
        table.add_row("Total Jobs", str(total_jobs))
        table.add_row("Index Name", stats.get('index_name', 'N/A'))
        table.add_row("Namespace", stats.get('namespace', 'N/A'))
        
        if 'companies' in stats:
            table.add_row("Companies", str(len(stats['companies'])))
        
        console.print(table)
        
        # Show companies breakdown if available
        if 'companies' in stats and stats['companies']:
            console.print("\n[bold green]Jobs by Company[/bold green]")
            company_table = Table()
            company_table.add_column("Company", style="cyan")
            company_table.add_column("Job Count", style="magenta", justify="right")
            
            for company, count in sorted(stats['companies'].items(), key=lambda x: x[1], reverse=True):
                company_table.add_row(company, str(count))
            
            console.print(company_table)
        
        if total_jobs == 0:
            console.print("\n[yellow]No jobs found in the database. Use 'fetch' command to add jobs.[/yellow]")
            
    except Exception as e:
        console.print(f"Error getting stats: {e}", style="bold red")
        logger.error(f"Error in stats command: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()