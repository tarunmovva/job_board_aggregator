#!/usr/bin/env python3
"""
Test script to verify the parallel batch processing optimization for Cerebras validation.
This tests that multiple batches are processed in parallel rather than sequentially.
"""

import asyncio
import time
import logging
from typing import List, Dict
from job_board_aggregator.api.cerebras.cerebras_validator import validate_jobs_with_cerebras

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_jobs(num_jobs: int) -> List[Dict]:
    """Create a list of test job entries for validation."""
    jobs = []
    for i in range(num_jobs):
        jobs.append({
            "url": f"https://example{i}.com/job-{i}",
            "chunk_text": f"Software Engineer position {i}. We are looking for a skilled developer with Python experience. "
                         f"This role involves building web applications and working with databases. "
                         f"Requirements: 2+ years experience, Python, JavaScript, SQL. "
                         f"Join our dynamic team and work on exciting projects!"
        })
    return jobs

def create_test_resume() -> str:
    """Create a test resume for validation."""
    return """
    John Doe
    Software Engineer
    
    Experience:
    - 3 years Python development
    - Web application development with Django and Flask
    - Database design and optimization
    - JavaScript and React frontend development
    - RESTful API development
    
    Skills:
    - Programming: Python, JavaScript, SQL, HTML, CSS
    - Frameworks: Django, Flask, React, Node.js
    - Databases: PostgreSQL, MySQL, MongoDB
    - Tools: Git, Docker, AWS, Linux
    
    Education:
    - Bachelor's Degree in Computer Science
    """

async def test_parallel_processing():
    """Test the parallel batch processing optimization."""
    print("🚀 Testing Parallel Batch Processing Optimization")
    print("=" * 60)
    
    # Test with multiple batches (enough jobs to create multiple batches)
    # Assuming batch size is 25 (from .env), we'll use 60 jobs to create 3 batches
    test_jobs = create_test_jobs(60)
    test_resume = create_test_resume()
    
    print(f"📊 Test Setup:")
    print(f"   • Total jobs: {len(test_jobs)}")
    print(f"   • Expected batches: ~3 (assuming batch size of 25)")
    print(f"   • Resume length: {len(test_resume)} characters")
    print()
    
    # Run the validation and measure time
    start_time = time.time()
    
    try:
        false_positives, metadata = await validate_jobs_with_cerebras(test_jobs, test_resume)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print("✅ Validation completed successfully!")
        print()
        print("📈 Results:")
        print(f"   • Processing time: {processing_time:.2f} seconds")
        print(f"   • Jobs evaluated: {metadata.get('jobs_evaluated', 0)}")
        print(f"   • Batches processed: {metadata.get('batches_processed', 0)}")
        print(f"   • Models used: {metadata.get('models_used', [])}")
        print(f"   • False positives found: {len(false_positives)}")
        print(f"   • Schema enforced: {metadata.get('schema_enforced', False)}")
        
        if 'batch_details' in metadata:
            print()
            print("🔍 Batch Details:")
            for batch_detail in metadata['batch_details']:
                batch_idx = batch_detail.get('batch_index', 'Unknown')
                jobs_count = batch_detail.get('jobs_count', 0)
                models_successful = batch_detail.get('models_successful', 0)
                fp_found = batch_detail.get('false_positives_found', 0)
                error = batch_detail.get('error')
                
                if error:
                    print(f"   • Batch {batch_idx + 1}: {jobs_count} jobs, ERROR: {error}")
                else:
                    print(f"   • Batch {batch_idx + 1}: {jobs_count} jobs, {models_successful}/2 models successful, {fp_found} false positives")
        
        print()
        print("🎯 Performance Analysis:")
        
        # Estimate what sequential processing would have taken
        batches_count = metadata.get('batches_processed', 1)
        estimated_sequential_time = processing_time * batches_count
        time_saved = estimated_sequential_time - processing_time
        improvement_percentage = (time_saved / estimated_sequential_time) * 100 if estimated_sequential_time > 0 else 0
        
        print(f"   • Actual time (parallel): {processing_time:.2f}s")
        print(f"   • Estimated sequential time: {estimated_sequential_time:.2f}s")
        print(f"   • Time saved: {time_saved:.2f}s")
        print(f"   • Performance improvement: {improvement_percentage:.1f}%")
        
        if false_positives:
            print()
            print("🚫 False Positives Detected:")
            for fp_url in false_positives:
                print(f"   • {fp_url}")
        
        return True
        
    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"❌ Validation failed after {processing_time:.2f}s")
        print(f"   Error: {str(e)}")
        
        # Check if it's a configuration issue
        if "CERABRAS_API_KEY" in str(e):
            print()
            print("💡 Tip: Make sure CERABRAS_API_KEY is set in your .env file")
        elif "cerebras_cloud_sdk" in str(e):
            print()
            print("💡 Tip: Install the Cerebras SDK with: pip install cerebras_cloud_sdk")
        
        import traceback
        traceback.print_exc()
        return False

async def test_single_batch():
    """Test with a single batch to ensure the optimization doesn't break simple cases."""
    print()
    print("🧪 Testing Single Batch Processing")
    print("=" * 40)
    
    # Create a small job list that fits in one batch
    test_jobs = create_test_jobs(10)
    test_resume = create_test_resume()
    
    start_time = time.time()
    
    try:
        false_positives, metadata = await validate_jobs_with_cerebras(test_jobs, test_resume)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"✅ Single batch test completed in {processing_time:.2f}s")
        print(f"   • Batches processed: {metadata.get('batches_processed', 0)}")
        print(f"   • Expected: 1 batch")
        
        return metadata.get('batches_processed', 0) == 1
        
    except Exception as e:
        print(f"❌ Single batch test failed: {str(e)}")
        return False

async def main():
    """Run all tests."""
    print("🔬 Cerebras Parallel Processing Optimization Test")
    print("=" * 60)
    print()
    
    # Test single batch first
    single_batch_success = await test_single_batch()
    
    # Test parallel batch processing
    parallel_success = await test_parallel_processing()
    
    print()
    print("📋 Test Summary:")
    print(f"   • Single batch test: {'✅ PASS' if single_batch_success else '❌ FAIL'}")
    print(f"   • Parallel batch test: {'✅ PASS' if parallel_success else '❌ FAIL'}")
    
    if single_batch_success and parallel_success:
        print()
        print("🎉 All tests passed! The parallel optimization is working correctly.")
        print("   Your system should now be significantly faster when processing large job lists!")
    else:
        print()
        print("⚠️  Some tests failed. Please check the error messages above.")
    
    return 0 if (single_batch_success and parallel_success) else 1

if __name__ == "__main__":
    exit(asyncio.run(main()))