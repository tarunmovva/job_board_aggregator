#!/usr/bin/env python3
"""
Test script to verify the URL mapping fix for Cerebras validation.
"""

import asyncio
import os
import sys
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[OK] Environment variables loaded")
except ImportError:
    print("[WARN] python-dotenv not available")

async def test_url_mapping_fix():
    """Test the URL mapping fix with URLs that have different formats."""
    
    # Import after path setup
    from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator
    
    # Sample resume
    sample_resume = """
    Jane Smith
    Software Engineer
    
    Experience:
    - 5 years Python development
    - React frontend development  
    - Django backend
    - AWS cloud services
    """
    
    # Sample jobs with URLs that have different formats (with/without trailing slashes, query params)
    sample_jobs = [
        {
            "job_link": "https://company1.com/python-developer/",  # Trailing slash
            "chunk_text": "Python Developer. 3+ years experience with Python, Django, REST APIs."
        },
        {
            "job_link": "https://company2.com/react-developer?ref=careers",  # Query parameter
            "chunk_text": "React Frontend Developer. 3+ years React, JavaScript, TypeScript."
        },
        {
            "job_link": "https://company3.com/java-architect#apply",  # Fragment
            "chunk_text": "Senior Java Architect. 10+ years Java Enterprise, Spring Boot. Leadership required."
        },
        {
            "job_link": "https://company4.com/data-scientist",  # Clean URL
            "chunk_text": "Data Scientist. PhD preferred. ML, Python, R, TensorFlow. 5+ years experience."
        },
        {
            "job_link": "https://company5.com/fullstack-developer/?utm_source=indeed&ref=portal",  # Multiple params
            "chunk_text": "Full Stack Developer. Python, React, Node.js, AWS. 2-5 years experience."
        }
    ]
    
    print("Testing URL Mapping Fix for Cerebras Validation")
    print("=" * 60)
    print(f"Sample jobs: {len(sample_jobs)}")
    print("\nJobs with different URL formats:")
    for i, job in enumerate(sample_jobs, 1):
        print(f"{i}. {job['job_link']}")
    
    print("\n" + "=" * 60)
    print("Testing URL normalization and mapping...")
    
    try:
        validator = CerebrasSchemaValidator()
        
        # Test URL normalization
        print("\nURL Normalization Test:")
        for job in sample_jobs:
            original = job['job_link']
            normalized = validator._normalize_url(original)
            print(f"  {original} -> {normalized}")
        
        # Test URL mapping creation
        print("\nURL Mapping Test:")
        url_mapping = validator._create_url_mapping(sample_jobs)
        for normalized, original in url_mapping.items():
            print(f"  {normalized} -> {original}")
        
        print(f"\nMapping created: {len(url_mapping)} entries")
        
        # Test full validation (if API key is available)
        if os.getenv('CERABRAS_API_KEY'):
            print("\n" + "=" * 60)
            print("Running full validation test...")
            
            false_positives, metadata = await validator.validate_job_matches(sample_jobs, sample_resume)
            
            print(f"\nValidation Results:")
            print(f"Models used: {metadata.get('models_used', [])}")
            print(f"Jobs evaluated: {metadata.get('jobs_evaluated', 0)}")
            print(f"False positives found: {len(false_positives)}")
            
            if false_positives:
                print(f"\nFalse positive URLs (in original format):")
                for url in false_positives:
                    print(f"  - {url}")
                    
                # Verify these are in original format
                original_urls = {job['job_link'] for job in sample_jobs}
                for fp_url in false_positives:
                    if fp_url in original_urls:
                        print(f"  ✓ '{fp_url}' matches original format")
                    else:
                        print(f"  ✗ '{fp_url}' does NOT match any original URL")
            else:
                print("\nNo false positives detected.")
                
            print(f"\nFull metadata: {metadata}")
        else:
            print("\nSkipping full validation test (no API key)")
            
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_url_mapping_fix())