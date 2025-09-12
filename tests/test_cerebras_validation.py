"""
Test script for Cerebras AI false positive detection.

Usage:
    python test_cerebras_validation.py

Prerequisites:
    1. Install dependencies: pip install -r requirements.txt
    2. Ensure .env file contains CERABRAS_API_KEY
    3. Activate virtual environment if using one
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[OK] Environment variables loaded from .env file")
except ImportError:
    print("[WARN] python-dotenv not available, ensure environment variables are set manually")

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

async def test_cerebras_validation():
    """Test the Cerebras validation with sample data."""
    
    # Sample resume text
    sample_resume = """
    John Doe
    Software Engineer
    
    Experience:
    - 3 years Python development
    - React and JavaScript frontend
    - Node.js backend development
    - AWS cloud services
    - REST API development
    
    Skills: Python, JavaScript, React, Node.js, AWS, Git, Docker
    """
    
    # Sample job matches (mix of good and potentially false positive matches)
    sample_jobs = [
        {
            "job_link": "https://company1.com/python-developer",
            "chunk_text": "Python Developer position. 2-4 years experience with Python, Django, REST APIs. Remote work available."
        },
        {
            "job_link": "https://company2.com/react-developer", 
            "chunk_text": "React Frontend Developer. 3+ years React, JavaScript, TypeScript. Build modern web applications."
        },
        {
            "job_link": "https://company3.com/java-architect",
            "chunk_text": "Senior Java Architect. 10+ years Java Enterprise, Spring Boot, Microservices architecture. Team leadership required."
        },
        {
            "job_link": "https://company4.com/data-scientist",
            "chunk_text": "Data Scientist position. PhD preferred. Machine Learning, Python, R, TensorFlow, PyTorch. 5+ years ML experience."
        },
        {
            "job_link": "https://company5.com/fullstack-developer",
            "chunk_text": "Full Stack Developer. Python, React, Node.js, AWS. 2-5 years experience. Build end-to-end applications."
        }
    ]
    
    print("Testing Cerebras AI False Positive Detection")
    print("=" * 50)
    print(f"Sample jobs: {len(sample_jobs)}")
    print("Jobs to evaluate:")
    for i, job in enumerate(sample_jobs, 1):
        print(f"{i}. {job['job_link']} - {job['chunk_text'][:50]}...")
    
    print("\n" + "=" * 50)
    print("Running Cerebras validation...")
    
    try:
        validator = CerebrasSchemaValidator()
        false_positives, metadata = await validator.validate_job_matches(sample_jobs, sample_resume)
        
        print(f"\nValidation Results:")
        print(f"Models used: {metadata.get('models_used', [])}")
        print(f"Jobs evaluated: {metadata.get('jobs_evaluated', 0)}")
        print(f"False positives found: {len(false_positives)}")
        
        if false_positives:
            print(f"\nFalse positive URLs:")
            for url in false_positives:
                print(f"  - {url}")
        else:
            print("\nNo false positives detected.")
            
        print(f"\nFull metadata: {metadata}")
        
    except Exception as e:
        print(f"Error during validation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Check if API key is set
    if not os.getenv('CERABRAS_API_KEY'):
        print("ERROR: CERABRAS_API_KEY environment variable not set!")
        print("Please ensure your .env file is loaded or set the environment variable.")
        sys.exit(1)
    
    print("Cerebras API Key found [OK]")
    
    # Run the test
    asyncio.run(test_cerebras_validation())