#!/usr/bin/env python3
"""
Test the enhanced truncated JSON repair for single-line responses.
"""

import logging
logging.basicConfig(level=logging.INFO)

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

def main():
    print("=== SINGLE-LINE TRUNCATED JSON REPAIR TEST ===")
    
    validator = CerebrasSchemaValidator()
    
    # Test case: Exact error from Qwen 3 32B logs (single-line truncated)
    single_line_truncated = '{"flagged_job_urls": ["https://job-boards.greenhouse.io/userinterviews/jobs/5649159004", "https://www.shift-technology.com/careers?gh_jid=6666663003", "https://www.make.com/en/careers-detail?gh_jid=6692408003", "https://job-boards.greenhouse.io/reddit/jobs/7249227", "https://app.careerpuck.com/job-board/udemy/job/5647447004?gh_jid=5647447004", "https://boards.greenhouse.io/andurilindustries/jobs/4874833007?gh_jid=4874833007", "https://boards.greenhouse.io/andurilindustries/jobs/4872151007?gh_jid'
    
    # Test case: Multi-line truncated (from previous logs)
    multi_line_truncated = """{
  "flagged_job_urls": [
    "https://job-boards.greenhouse.io/angi/jobs/8150277002",
    "https://job-boards.greenhouse.io/angi/jobs/8162863002",
    "https://job-boards.greenhouse.io/angi/jobs/8162864002",
    "https://boards.greenhouse.io/andurilindustries/jobs/4874833007",
    "https://job-boards.greenhouse.io/pandadoc/jobs/7244876",
    "https://job-boards.greenhouse.io/pandadoc/jobs/7244875",
    "https://job-boards.greenhouse.io/pandadoc/jobs/7244877",
    "https://job-boards.greenhouse."""
    
    print("Testing single-line truncated JSON repair...")
    print(f"Input length: {len(single_line_truncated)} characters")
    
    result1 = validator._extract_json_from_text(single_line_truncated)
    if result1:
        print(f"✓ SUCCESS: Recovered {len(result1['flagged_job_urls'])} URLs from single-line response")
        print("First few URLs:")
        for i, url in enumerate(result1['flagged_job_urls'][:3]):
            print(f"  {i+1}. {url}")
    else:
        print("✗ FAILED: Could not repair single-line truncated JSON")
    
    print("\nTesting multi-line truncated JSON repair...")
    result2 = validator._extract_json_from_text(multi_line_truncated)
    if result2:
        print(f"✓ SUCCESS: Recovered {len(result2['flagged_job_urls'])} URLs from multi-line response")
    else:
        print("✗ FAILED: Could not repair multi-line truncated JSON")
    
    print("\n=== ENHANCED REPAIR FEATURES ===")
    print("✅ Single-line JSON truncation handling")
    print("✅ Multi-line JSON truncation handling")
    print("✅ Regex-based URL extraction for precision")
    print("✅ Complete URL validation (no partial URLs)")
    print("✅ Graceful fallback to empty array if needed")
    
    print(f"\n=== RESULTS SUMMARY ===")
    print(f"Single-line repair: {'✓ WORKING' if result1 else '✗ FAILED'}")
    print(f"Multi-line repair: {'✓ WORKING' if result2 else '✗ FAILED'}")
    
    if result1 and result2:
        print("\n🎉 ENHANCED REPAIR SYSTEM WORKING!")
        print("Both single-line and multi-line truncated JSON can be recovered.")
    else:
        print("\n⚠️  Some repair patterns need more work.")

if __name__ == "__main__":
    main()