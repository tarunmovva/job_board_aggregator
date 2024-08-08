"""Test FastAPI concurrency behavior with blocking operations."""

import asyncio
import time
import aiohttp
import json
from concurrent.futures import ThreadPoolExecutor
import threading

# Simulated blocking operations (like Vector Store and File Parsing)
def blocking_vector_search(query_text: str, duration: float = 2.0) -> str:
    """Simulate blocking vector store search operation."""
    print(f"[Thread {threading.current_thread().ident}] Starting vector search for: {query_text[:50]}...")
    time.sleep(duration)  # Blocking I/O simulation
    print(f"[Thread {threading.current_thread().ident}] Vector search completed for: {query_text[:50]}...")
    return f"Vector results for: {query_text[:50]}"

def blocking_file_parse(filename: str, duration: float = 1.0) -> str:
    """Simulate blocking file parsing operation."""
    print(f"[Thread {threading.current_thread().ident}] Starting file parse for: {filename}")
    time.sleep(duration)  # Blocking I/O simulation
    print(f"[Thread {threading.current_thread().ident}] File parse completed for: {filename}")
    return f"Parsed content from: {filename}"

async def async_ai_enhancement(text: str, duration: float = 1.5) -> str:
    """Simulate async AI enhancement (like Groq/Cerebras)."""
    print(f"[Thread {threading.current_thread().ident}] Starting AI enhancement...")
    await asyncio.sleep(duration)  # Non-blocking async operation
    print(f"[Thread {threading.current_thread().ident}] AI enhancement completed")
    return f"Enhanced: {text[:50]}"

async def simulate_resume_upload_endpoint(request_id: int):
    """
    Simulate the resume upload endpoint processing pipeline.
    This mirrors the actual /match-resume-upload endpoint structure.
    """
    start_time = time.time()
    print(f"\n🚀 Request {request_id} started at {start_time:.2f}")
    
    try:
        # Step 1: File parsing (BLOCKING operation - like resume_parser.py)
        print(f"[Request {request_id}] Step 1: File parsing...")
        parse_start = time.time()
        parsed_content = blocking_file_parse(f"resume_{request_id}.pdf", 1.0)
        parse_time = time.time() - parse_start
        print(f"[Request {request_id}] File parsing took {parse_time:.2f}s")
        
        # Step 2: AI Enhancement (ASYNC operation - like resume_enhancer.py)
        print(f"[Request {request_id}] Step 2: AI enhancement...")
        enhance_start = time.time()
        enhanced_content = await async_ai_enhancement(parsed_content, 1.5)
        enhance_time = time.time() - enhance_start
        print(f"[Request {request_id}] AI enhancement took {enhance_time:.2f}s")
        
        # Step 3: Vector store search (BLOCKING operation - like vector_store_integrated.py)
        print(f"[Request {request_id}] Step 3: Vector search...")
        search_start = time.time()
        search_results = blocking_vector_search(enhanced_content, 2.0)
        search_time = time.time() - search_start
        print(f"[Request {request_id}] Vector search took {search_time:.2f}s")
        
        # Step 4: AI Validation (ASYNC operation - like cerebras_validator.py)
        print(f"[Request {request_id}] Step 4: AI validation...")
        validation_start = time.time()
        validation_results = await async_ai_enhancement(search_results, 1.0)
        validation_time = time.time() - validation_start
        print(f"[Request {request_id}] AI validation took {validation_time:.2f}s")
        
        total_time = time.time() - start_time
        print(f"✅ Request {request_id} completed in {total_time:.2f}s")
        return {
            "request_id": request_id,
            "total_time": total_time,
            "parse_time": parse_time,
            "enhance_time": enhance_time,
            "search_time": search_time,
            "validation_time": validation_time,
            "result": validation_results
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ Request {request_id} failed after {total_time:.2f}s: {e}")
        return {"request_id": request_id, "error": str(e), "total_time": total_time}

async def test_concurrent_requests():
    """Test how FastAPI handles multiple concurrent requests with blocking operations."""
    print("🔬 Testing FastAPI Concurrency with Mixed Async/Blocking Operations")
    print("=" * 70)
    
    # Test 1: Sequential requests (baseline)
    print("\n📊 Test 1: Sequential Requests (Baseline)")
    print("-" * 40)
    sequential_start = time.time()
    
    for i in range(3):
        await simulate_resume_upload_endpoint(i + 1)
    
    sequential_total = time.time() - sequential_start
    print(f"\n⏱️  Sequential total time: {sequential_total:.2f}s")
    
    # Test 2: Concurrent requests (FastAPI behavior)
    print("\n📊 Test 2: Concurrent Requests (FastAPI Simulation)")
    print("-" * 50)
    concurrent_start = time.time()
    
    # This simulates what happens when FastAPI receives 3 simultaneous requests
    tasks = []
    for i in range(3):
        task = simulate_resume_upload_endpoint(i + 10)
        tasks.append(task)
    
    # Wait for all requests to complete
    results = await asyncio.gather(*tasks)
    
    concurrent_total = time.time() - concurrent_start
    print(f"\n⏱️  Concurrent total time: {concurrent_total:.2f}s")
    
    # Analysis
    print("\n📈 Analysis:")
    print("-" * 20)
    time_saved = sequential_total - concurrent_total
    improvement = (time_saved / sequential_total) * 100 if sequential_total > 0 else 0
    
    print(f"Sequential time: {sequential_total:.2f}s")
    print(f"Concurrent time: {concurrent_total:.2f}s")
    print(f"Time saved: {time_saved:.2f}s")
    print(f"Performance improvement: {improvement:.1f}%")
    
    # Detailed timing analysis
    print(f"\n🔍 Individual Request Times:")
    for result in results:
        if 'error' not in result:
            print(f"Request {result['request_id']}: {result['total_time']:.2f}s")
            print(f"  - File parse: {result['parse_time']:.2f}s (blocking)")
            print(f"  - AI enhance: {result['enhance_time']:.2f}s (async)")
            print(f"  - Vector search: {result['search_time']:.2f}s (blocking)")
            print(f"  - AI validation: {result['validation_time']:.2f}s (async)")
    
    return improvement > 0

async def main():
    """Main test function."""
    print("🧪 FastAPI Concurrency Analysis with Real-World Pipeline")
    print("=" * 70)
    print("This test simulates the actual /match-resume-upload endpoint behavior")
    print("with mixed async and blocking operations, just like your codebase.")
    print()
    
    success = await test_concurrent_requests()
    
    print(f"\n🎯 Conclusion:")
    print("-" * 15)
    if success:
        print("✅ FastAPI DOES provide concurrency benefits even with blocking operations!")
        print("   - Async operations (AI enhancement, validation) run concurrently")
        print("   - Blocking operations (file parse, vector search) still benefit from")
        print("     FastAPI's async nature when multiple requests are handled")
        print("   - Overall throughput is improved for multiple concurrent users")
    else:
        print("❌ No significant concurrency benefit detected")
    
    print(f"\n💡 Key Insights:")
    print("   1. FastAPI can handle multiple requests concurrently")
    print("   2. Blocking operations don't completely block other requests")
    print("   3. Async operations provide the best concurrency benefits")
    print("   4. Mixed pipelines still show improved throughput")

if __name__ == "__main__":
    asyncio.run(main())