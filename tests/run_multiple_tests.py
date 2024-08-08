#!/usr/bin/env python3
"""
Run Cerebras validation test multiple times to check for consistency and errors.
"""

import subprocess
import sys
import time
from datetime import datetime

def run_test(test_number):
    """Run a single test and capture results."""
    print(f"\n{'='*60}")
    print(f"🧪 TEST RUN #{test_number} - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    
    try:
        start_time = time.time()
        result = subprocess.run(
            [sys.executable, "test_cerebras_validation.py"],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"⏱️  Duration: {duration:.2f} seconds")
        print(f"🔄 Exit Code: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ TEST PASSED")
            # Extract key metrics from output
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if "Models used:" in line or "False positives found:" in line or "Jobs evaluated:" in line:
                    print(f"📊 {line.strip()}")
        else:
            print("❌ TEST FAILED")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
        
        return {
            'test_number': test_number,
            'success': result.returncode == 0,
            'duration': duration,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode
        }
        
    except subprocess.TimeoutExpired:
        print("⏰ TEST TIMED OUT (120 seconds)")
        return {
            'test_number': test_number,
            'success': False,
            'duration': 120,
            'error': 'TIMEOUT',
            'exit_code': -1
        }
    except Exception as e:
        print(f"💥 TEST ERROR: {e}")
        return {
            'test_number': test_number,
            'success': False,
            'duration': 0,
            'error': str(e),
            'exit_code': -1
        }

def main():
    """Run tests and generate summary."""
    print("🚀 Starting 10 consecutive Cerebras validation tests...")
    print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    for i in range(1, 11):
        result = run_test(i)
        results.append(result)
        
        # Small delay between tests to avoid rate limiting
        if i < 10:
            print("\n⏳ Waiting 2 seconds before next test...")
            time.sleep(2)
    
    # Generate summary
    print(f"\n{'='*60}")
    print("📈 SUMMARY REPORT")
    print(f"{'='*60}")
    
    successful_tests = [r for r in results if r['success']]
    failed_tests = [r for r in results if not r['success']]
    
    print(f"✅ Successful tests: {len(successful_tests)}/10")
    print(f"❌ Failed tests: {len(failed_tests)}/10")
    print(f"📊 Success rate: {len(successful_tests)/10*100:.1f}%")
    
    if successful_tests:
        avg_duration = sum(r['duration'] for r in successful_tests) / len(successful_tests)
        min_duration = min(r['duration'] for r in successful_tests)
        max_duration = max(r['duration'] for r in successful_tests)
        print(f"⏱️  Average duration: {avg_duration:.2f}s")
        print(f"⏱️  Min/Max duration: {min_duration:.2f}s / {max_duration:.2f}s")
    
    # Show failed test details
    if failed_tests:
        print(f"\n🔍 FAILED TEST DETAILS:")
        for test in failed_tests:
            print(f"  Test #{test['test_number']} - Exit Code: {test['exit_code']}")
            if 'error' in test:
                print(f"    Error: {test['error']}")
            if test.get('stderr'):
                print(f"    STDERR: {test['stderr'][:200]}...")
    
    # Extract model combinations used
    model_combinations = set()
    for test in successful_tests:
        if test.get('stdout'):
            for line in test['stdout'].split('\n'):
                if "Selected models for validation:" in line:
                    models = line.split(': [')[1].split(']')[0] if ': [' in line else 'Unknown'
                    model_combinations.add(models)
    
    if model_combinations:
        print(f"\n🤖 MODEL COMBINATIONS TESTED:")
        for combo in sorted(model_combinations):
            print(f"  - {combo}")
    
    print(f"\n📅 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Return exit code based on results
    if len(successful_tests) >= 8:  # Allow up to 2 failures
        print("\n🎉 OVERALL RESULT: PASS (≥80% success rate)")
        return 0
    else:
        print("\n⚠️  OVERALL RESULT: FAIL (<80% success rate)")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)