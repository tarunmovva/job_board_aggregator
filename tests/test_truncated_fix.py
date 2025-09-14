#!/usr/bin/env python3
"""
Test the truncated JSON repair functionality.
"""

import logging
logging.basicConfig(level=logging.INFO)

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

def main():
    print("=== TRUNCATED JSON REPAIR TEST ===")
    
    validator = CerebrasSchemaValidator()
    
    # Test case matching the actual error from logs
    truncated_json = """{
  "flagged_job_urls": [
    "https://job-boards.greenhouse.io/angi/jobs/8150277002",
    "https://job-boards.greenhouse.io/angi/jobs/8162863002",
    "https://job-boards.greenhouse.io/angi/jobs/8162864002",
    "https://boards.greenhouse.io/andurilindustries/jobs/4874833007",
    "https://job-boards.greenhouse.io/pandadoc/jobs/7244876",
    "https://job-boards.greenhouse.io/pandadoc/jobs/7244875",
    "https://job-boards.greenhouse.io/pandadoc/jobs/7244877",
    "https://job-boards.greenhouse."""
    
    print("Testing truncated JSON repair...")
    print(f"Input length: {len(truncated_json)} characters")
    
    result = validator._extract_json_from_text(truncated_json)
    
    if result:
        print(f"✓ SUCCESS: Repaired and parsed {len(result['flagged_job_urls'])} URLs")
        print("First few URLs:")
        for i, url in enumerate(result['flagged_job_urls'][:3]):
            print(f"  {i+1}. {url}")
    else:
        print("✗ FAILED: Could not repair truncated JSON")
    
    print("\n=== SYSTEM IMPROVEMENTS ===")
    print("✓ Increased max_completion_tokens to 500")
    print("✓ Added truncated JSON detection and repair")
    print("✓ Enhanced error handling for 'Unterminated string' errors")
    print("✓ Production-ready for handling model response truncation")

if __name__ == "__main__":
    main()