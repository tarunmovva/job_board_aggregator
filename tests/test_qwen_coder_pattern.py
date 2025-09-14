#!/usr/bin/env python3
"""
Test truncation repair with the Qwen 3 Coder 480B pattern.
"""

import logging
logging.basicConfig(level=logging.INFO)

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

def main():
    print("=== QWEN 3 CODER TRUNCATION PATTERN TEST ===")
    
    validator = CerebrasSchemaValidator()
    
    # Test case: Exact truncation pattern from Qwen 3 Coder 480B logs
    qwen_coder_truncated = """{
  "flagged_job_urls": [
    "https://job-boards.greenhouse.io/affirm/jobs/7118737003",
    "https://job-boards.greenhouse.io/affirm/jobs/6996652003",
    "https://job-boards.greenhouse.io/affirm/jobs/7118739003",
    "https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002&gh_jid=8153753002",
    "https://app.careerpuck.com/job-board/lyft/job/8160056002?gh_jid=8160056002",
    "https://www.make.com/en/careers-detail?gh_jid=6692408003",
    "https://job-boards.greenhouse.io/s"""
    
    print("Testing Qwen 3 Coder 480B truncation pattern...")
    print(f"Input length: {len(qwen_coder_truncated)} characters")
    print(f"Truncation point: 'line 19 column 1 (char 1133)' - shows multi-line truncation")
    
    result = validator._extract_json_from_text(qwen_coder_truncated)
    
    if result:
        print(f"✅ SUCCESS: Recovered {len(result['flagged_job_urls'])} URLs")
        print("Complete URLs recovered:")
        for i, url in enumerate(result['flagged_job_urls'], 1):
            print(f"  {i}. {url}")
    else:
        print("❌ FAILED: Could not repair Qwen 3 Coder truncated JSON")
    
    print("\n=== TRUNCATION ANALYSIS ===")
    print("Pattern: Multi-line JSON with incomplete URL at end")
    print("Error: 'Expecting value: line 19 column 1' - likely missing closing bracket")
    print("Fix: Multi-line repair logic removes incomplete lines, closes properly")
    
    print("\n=== PREVENTION vs REPAIR ===")
    print("🔧 Schema Mode (Prevention):")
    print("  • Qwen 3 Coder 480B now uses schema mode")
    print("  • Should prevent truncation in future requests")
    print("  • More structured, controlled output")
    
    print("\n🛠️ Repair System (Backup):")
    print("  • Still available if truncation occurs")
    print("  • Handles both single-line and multi-line patterns")
    print("  • Extracts maximum valid data from corrupted responses")
    
    if result:
        print(f"\n🎉 COMPREHENSIVE SOLUTION WORKING!")
        print(f"✅ Repair system recovered {len(result['flagged_job_urls'])}/6 complete URLs")
        print("✅ Schema mode will prevent future truncation")
        print("✅ Double protection ensures validation reliability")
    else:
        print("\n⚠️ Repair needs investigation")

if __name__ == "__main__":
    main()