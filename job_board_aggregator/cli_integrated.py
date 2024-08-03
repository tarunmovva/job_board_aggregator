"""Simplified CLI using Pinecone integrated embedding (no local embedding generation needed)."""

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
from job_board_aggregator.embeddings.vector_store_integrated import VectorStoreIntegrated
from job_board_aggregator.util.timestamp import get_last_fetch_time, update_fetch_time, is_job_newer_than_last_fetch, set_default_start_date


def main():
    """Main entry point for the simplified command line interface."""
    parser = argparse.ArgumentParser(description='Job board aggregator tool (with Pinecone integrated embedding)')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Add the 'fetch' command
    fetch_parser = subparsers.add_parser('fetch', help='Fetch jobs from APIs')
    fetch_parser.add_argument('csv_file', help='Path to the CSV file containing company names and API endpoints')
    fetch_parser.add_argument('--limit', type=int, default=None, help='Limit the number of companies to process')
    
    # Add the 'reset' command
    reset_parser = subparsers.add_parser('reset', help='Reset the vector database by deleting all jobs')
    
    # Add the 'match-resume' command
    match_parser = subparsers.add_parser('match-resume', help='Find jobs matching a resume')
    match_parser.add_argument('resume_file', help='Path to the resume file (PDF, DOCX, or TXT)')
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
    else:
        parser.print_help()
        sys.exit(1)


def _handle_fetch_command(args):
    """Handle the 'fetch' command using integrated embedding."""
    # Initialize vector store (no embedding generator needed!)
    vector_store = VectorStoreIntegrated()
    api_client = JobAPIClient()
    
    # Read companies from CSV
    companies = _read_csv_file(args.csv_file, args.limit)
    
    jobs_added = 0
    for company_name, api_endpoint in companies:
        # Fetch jobs from the API
        api_response = api_client.fetch_jobs(company_name, api_endpoint)
        
        if not api_response:
            continue
        
        # Find the jobs array in the response
        jobs_array = _find_jobs_array(api_response)
        logger.info(f"Found {len(jobs_array)} jobs for {company_name}")
        
        # Get last fetch time for this company
        last_fetch_time = get_last_fetch_time(company_name)
        if last_fetch_time:
            logger.info(f"Last fetch for {company_name} was at {last_fetch_time}")
        else:
            logger.info(f"No previous fetch record for {company_name}")
        
        # Process each job
        new_jobs_processed = 0
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
            
            # Skip if job is older than last fetch time
            job_date = first_published or last_updated
            if last_fetch_time and not is_job_newer_than_last_fetch(company_name, job_date):
                logger.info(f"Skipping job {job_title} from {company} because it's not newer than the last fetch")
                continue
            
            # Extract job description
            job_description = _extract_field(job, ['content', 'description', 'summary', 'job_description'])
            
            if not job_description:
                logger.warning(f"Skipping job {job_title} from {company} because no job description was found")
                continue
            
            # Prepare job data (no need to generate embeddings!)
            job_data = {
                'job_link': job_link,
                'job_title': job_title,
                'company_name': company,
                'location': location,
                'first_published': first_published,
                'last_updated': last_updated,
                'job_description': job_description
            }
            
            # Store in vector database (Pinecone will generate embeddings automatically)
            vector_store.add_job(job_link, job_data)
            jobs_added += 1
            new_jobs_processed += 1
        
        # Update the last fetch time for this company
        update_fetch_time(company_name)
        logger.info(f"Processed {new_jobs_processed} new jobs for {company_name}")
    
    logger.info(f"Added {jobs_added} new jobs to the vector store")
    print(f"Successfully added {jobs_added} new jobs to the database")


def _handle_reset_command(args):
    """Handle the 'reset' command."""
    vector_store = VectorStoreIntegrated()
    
    # Confirm reset
    response = input("Are you sure you want to reset the vector database? This will delete all jobs. (y/N): ")
    if response.lower() not in ['y', 'yes']:
        print("Reset cancelled.")
        return
    
    # Reset the vector store
    success = vector_store.reset()
    if success:
        print("Vector database reset successfully.")
    else:
        print("Failed to reset vector database.")
        sys.exit(1)


def _handle_match_resume_command(args):
    """Handle the 'match-resume' command using text-based search."""
    # Initialize vector store
    vector_store = VectorStoreIntegrated()
    
    # Read resume file
    resume_text = _read_resume_file(args.resume_file)
    if not resume_text:
        print(f"Error: Could not read resume file {args.resume_file}")
        sys.exit(1)
    
    # Parse keywords if provided
    keywords = []
    if args.keywords:
        keywords = [kw.strip() for kw in args.keywords.split(',')]
        logger.info(f"Using keywords: {keywords}")
    
    # Parse date range if provided
    date_range = None
    if args.start_date or args.end_date:
        start_date = args.start_date or "1970-01-01"
        end_date = args.end_date or "2030-12-31"
        date_range = (start_date, end_date)
        logger.info(f"Using date range: {start_date} to {end_date}")
    
    # Search for matching jobs (Pinecone will handle embedding automatically)
    logger.info(f"Searching for jobs matching resume with limit {args.limit}")
    matching_jobs = vector_store.search_with_resume(
        resume_text=resume_text,
        keywords=keywords,
        limit=args.limit * 5,  # Get more results to account for filtering
        date_range=date_range
    )
    
    # Limit results
    matching_jobs = matching_jobs[:args.limit]
    
    if not matching_jobs:
        print("No matching jobs found.")
        return
    
    # Display results
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="dim", width=6)
    table.add_column("Job Title", style="cyan", no_wrap=True)
    table.add_column("Company", style="green")
    table.add_column("Location", style="yellow")
    table.add_column("Similarity", style="red")
    table.add_column("Link", style="blue")
    
    for i, job in enumerate(matching_jobs):
        table.add_row(
            str(i + 1),
            job.get('job_title', 'N/A')[:50],
            job.get('company_name', 'N/A')[:30],
            job.get('location', 'N/A')[:30],
            f"{job.get('similarity_score', 0):.3f}",
            job.get('job_link', 'N/A')[:50]
        )
    
    console.print(table)
    print(f"\nFound {len(matching_jobs)} matching jobs")
    
    # Save to file if output path provided
    if args.output:
        _save_results_to_csv(matching_jobs, args.output)
        print(f"Results saved to {args.output}")


def _handle_set_default_date_command(args):
    """Handle the 'set-default-date' command."""
    try:
        # Validate date format
        datetime.strptime(args.date, '%Y-%m-%d')
        set_default_start_date(args.date)
        print(f"Default start date set to {args.date}")
    except ValueError:
        print(f"Error: Invalid date format. Please use YYYY-MM-DD format.")
        sys.exit(1)


# Helper functions (same as original)
def _read_csv_file(csv_path, limit=None):
    """Read the CSV file containing company names and API endpoints."""
    companies = []
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            # Skip header row if it exists
            first_row = next(reader, None)
            if first_row and 'company' in first_row[0].lower():
                pass  # Skip header
            else:
                # If first row doesn't look like a header, add it to companies
                companies.append((first_row[0], first_row[1]))
            
            # Read the rest of the rows
            for row in reader:
                if len(row) >= 2:
                    companies.append((row[0], row[1]))
                    
                # Check if we've reached the limit
                if limit and len(companies) >= limit:
                    logger.info(f"Reached limit of {limit} companies, stopping CSV reading")
                    break
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
    
    return companies


def _find_jobs_array(api_response):
    """Find the array of jobs in the API response."""
    if isinstance(api_response, list):
        return api_response
    elif isinstance(api_response, dict):
        # Common keys for job arrays
        possible_keys = ['jobs', 'results', 'data', 'items', 'openings', 'positions']
        for key in possible_keys:
            if key in api_response and isinstance(api_response[key], list):
                return api_response[key]
        # If no standard key found, look for any list
        for value in api_response.values():
            if isinstance(value, list) and len(value) > 0:
                return value
    return []


def _extract_field(job, field_names):
    """Extract a field from a job using multiple possible field names."""
    for field_name in field_names:
        if field_name in job and job[field_name]:
            return job[field_name]
    return None


def _read_resume_file(file_path):
    """Read resume content from various file formats."""
    try:
        if file_path.lower().endswith('.pdf'):
            from pdfminer.high_level import extract_text
            return extract_text(file_path)
        elif file_path.lower().endswith('.docx'):
            from docx import Document
            doc = Document(file_path)
            return '\n'.join([paragraph.text for paragraph in doc.paragraphs])
        elif file_path.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logger.error(f"Unsupported file format: {file_path}")
            return None
    except Exception as e:
        logger.error(f"Error reading resume file: {e}")
        return None


def _save_results_to_csv(jobs, output_path):
    """Save job results to a CSV file."""
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            if not jobs:
                return
                
            fieldnames = ['rank', 'job_title', 'company_name', 'location', 'similarity_score', 'job_link', 'job_description']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for i, job in enumerate(jobs):
                writer.writerow({
                    'rank': i + 1,
                    'job_title': job.get('job_title', ''),
                    'company_name': job.get('company_name', ''),
                    'location': job.get('location', ''),
                    'similarity_score': job.get('similarity_score', 0),
                    'job_link': job.get('job_link', ''),
                    'job_description': job.get('job_description', '')
                })
    except Exception as e:
        logger.error(f"Error saving results to CSV: {e}")


if __name__ == '__main__':
    main()
