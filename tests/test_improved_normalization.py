#!/usr/bin/env python3
"""
Test the improved URL normalization that preserves job-specific parameters.
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_improved_normalization():
    """Test that the new normalization preserves unique job identifiers."""
    
    from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator
    
    validator = CerebrasSchemaValidator()
    
    # Test cases that were causing issues
    test_urls = [
        # Moveworks jobs - different gh_jid values
        "https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002&gh_jid=8153753002",
        "https://www.moveworks.com/us/en/company/careers/position?gh_jid=8128924002&gh_jid=8128924002",
        
        # Elastic jobs - different gh_jid values
        "https://jobs.elastic.co/jobs?gh_jid=7193863&gh_jid=7193863",
        "https://jobs.elastic.co/jobs?gh_jid=7244676&gh_jid=7244676",
        
        # Additional test cases
        "https://company.com/careers/",  # Trailing slash
        "https://company.com/careers",   # No trailing slash
        "https://company.com/job?id=123#apply",  # Fragment to remove
        "https://company.com/job?id=456",  # Query param to keep
        "https://company.com/job?id=789&ref=linkedin",  # Multiple params to keep
    ]
    
    print("Testing Improved URL Normalization")
    print("=" * 60)
    print("Goal: Preserve job-specific parameters while removing only problematic characters")
    print()
    
    normalized_urls = {}
    duplicates_found = False
    
    for original_url in test_urls:
        normalized = validator._normalize_url(original_url)
        
        print(f"Original:   {original_url}")
        print(f"Normalized: {normalized}")
        
        # Check for duplicates
        if normalized in normalized_urls:
            print(f"❌ DUPLICATE: This normalized URL already exists!")
            print(f"   First seen: {normalized_urls[normalized]}")
            print(f"   Current:    {original_url}")
            duplicates_found = True
        else:
            normalized_urls[normalized] = original_url
            print(f"✅ UNIQUE: New normalized URL")
        
        print("-" * 40)
    
    print("\nSummary:")
    print(f"Total URLs tested: {len(test_urls)}")
    print(f"Unique normalized URLs: {len(normalized_urls)}")
    print(f"Duplicates found: {duplicates_found}")
    
    if not duplicates_found:
        print("\n🎉 SUCCESS: All job-specific URLs remain unique after normalization!")
        print("The normalization now properly preserves job identifiers.")
    else:
        print("\n⚠️ ISSUE: Some URLs still collide after normalization.")
    
    print("\nNormalized URL mapping:")
    for norm_url, orig_url in normalized_urls.items():
        if norm_url != orig_url:
            print(f"  {norm_url} <- {orig_url}")
        else:
            print(f"  {norm_url} (unchanged)")

def test_url_mapping_with_improved_normalization():
    """Test that URL mapping no longer has collisions."""
    
    from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator
    
    # Simulate job data that was causing the warnings
    sample_jobs = [
        {
            "job_link": "https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002&gh_jid=8153753002",
            "chunk_text": "Senior Software Engineer - AI Platform"
        },
        {
            "job_link": "https://www.moveworks.com/us/en/company/careers/position?gh_jid=8128924002&gh_jid=8128924002", 
            "chunk_text": "Frontend Developer - React/TypeScript"
        },
        {
            "job_link": "https://jobs.elastic.co/jobs?gh_jid=7193863&gh_jid=7193863",
            "chunk_text": "DevOps Engineer - Elasticsearch Platform"
        },
        {
            "job_link": "https://jobs.elastic.co/jobs?gh_jid=7244676&gh_jid=7244676",
            "chunk_text": "Data Engineer - Analytics Team"
        }
    ]
    
    print("\n" + "=" * 60)
    print("Testing URL Mapping with Improved Normalization")
    print("=" * 60)
    
    validator = CerebrasSchemaValidator()
    url_mapping = validator._create_url_mapping(sample_jobs)
    
    print(f"Jobs processed: {len(sample_jobs)}")
    print(f"URL mappings created: {len(url_mapping)}")
    
    if len(url_mapping) == len(sample_jobs):
        print("✅ SUCCESS: Each job has a unique normalized URL!")
        print("No more collision warnings should appear.")
    else:
        print(f"⚠️ ISSUE: Expected {len(sample_jobs)} mappings, got {len(url_mapping)}")
    
    print("\nURL Mappings:")
    for normalized, original in url_mapping.items():
        print(f"  {normalized}")
        print(f"    <- {original}")
        print()

if __name__ == "__main__":
    test_improved_normalization()
    test_url_mapping_with_improved_normalization()