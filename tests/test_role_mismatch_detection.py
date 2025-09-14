"""
Enhanced test script for role mismatch detection in Cerebras validation.
Tests various types of role incompatibilities.
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

async def test_role_mismatch_detection():
    """Test role mismatch detection with specific scenarios."""
    
    # Test Case 1: Software Engineer Resume
    software_engineer_resume = """
    Sarah Johnson
    Software Engineer
    
    Experience:
    - 4 years Python web development (Django, Flask)
    - React and TypeScript frontend development
    - RESTful API design and implementation
    - PostgreSQL database design
    - AWS deployment and DevOps basics
    - Agile development practices
    
    Skills: Python, JavaScript, React, TypeScript, Django, PostgreSQL, Git, Docker, AWS
    Education: Bachelor's in Computer Science
    """
    
    # Test Case 2: Data Scientist Resume  
    data_scientist_resume = """
    Dr. Michael Chen
    Senior Data Scientist
    
    Experience:
    - 6 years machine learning and statistical modeling
    - Python data science stack (Pandas, NumPy, Scikit-learn)
    - Deep learning with TensorFlow and PyTorch
    - Statistical analysis and hypothesis testing
    - Big data processing with Spark
    - Research publication in ML conferences
    
    Skills: Python, R, TensorFlow, PyTorch, Pandas, SQL, Statistics, Machine Learning
    Education: PhD in Statistics, MS in Computer Science
    """
    
    # Mixed job opportunities (some matching, some mismatched)
    test_jobs = [
        # Good matches for Software Engineer
        {
            "job_link": "https://company1.com/python-developer",
            "chunk_text": "Python Developer position. 3-5 years experience with Django, REST APIs, PostgreSQL. Build scalable web applications."
        },
        {
            "job_link": "https://company2.com/fullstack-developer", 
            "chunk_text": "Full Stack Developer. React frontend, Python backend. 3+ years experience. Modern web development stack."
        },
        
        # Role mismatches for Software Engineer
        {
            "job_link": "https://company3.com/data-scientist",
            "chunk_text": "Senior Data Scientist. PhD preferred. Machine Learning, statistical modeling, research. 5+ years ML experience required."
        },
        {
            "job_link": "https://company4.com/ml-engineer",
            "chunk_text": "ML Engineer position. Deep learning, TensorFlow, PyTorch. Model deployment at scale. PhD in ML/Statistics required."
        },
        {
            "job_link": "https://company5.com/devops-architect",
            "chunk_text": "Senior DevOps Architect. 8+ years infrastructure. Kubernetes, Terraform, CI/CD pipelines. Lead platform engineering team."
        },
        {
            "job_link": "https://company6.com/mobile-developer",
            "chunk_text": "iOS Mobile Developer. Swift, Objective-C, iOS SDK. 5+ years mobile app development. App Store optimization."
        },
        {
            "job_link": "https://company7.com/security-engineer",
            "chunk_text": "Cybersecurity Engineer. Security clearance required. Penetration testing, CISSP certification. 7+ years security experience."
        },
        
        # Edge cases (borderline matches)
        {
            "job_link": "https://company8.com/backend-engineer",
            "chunk_text": "Backend Engineer. Java, Spring Boot, microservices. 4+ years enterprise backend development."
        },
        {
            "job_link": "https://company9.com/frontend-lead",
            "chunk_text": "Frontend Tech Lead. 6+ years frontend. Team leadership. Advanced React, Next.js, performance optimization."
        }
    ]
    
    print("Testing Enhanced Role Mismatch Detection")
    print("=" * 60)
    
    # Test with Software Engineer resume
    print(f"\n🧑‍💻 Testing with SOFTWARE ENGINEER resume:")
    print("Expected role mismatches: Data Scientist, ML Engineer, DevOps Architect, Mobile Developer, Security Engineer")
    print("Expected matches: Python Developer, Fullstack Developer")
    print("Edge cases: Backend Engineer (Java), Frontend Lead (seniority)")
    
    await test_validation(software_engineer_resume, test_jobs, "Software Engineer")
    
    print("\n" + "="*60)
    
    # Test with Data Scientist resume
    print(f"\n🔬 Testing with DATA SCIENTIST resume:")
    print("Expected role mismatches: Python Web Developer, Fullstack Developer, DevOps Architect, Mobile Developer")
    print("Expected matches: Data Scientist, ML Engineer")
    
    await test_validation(data_scientist_resume, test_jobs, "Data Scientist")

async def test_validation(resume_text, job_list, resume_type):
    """Run validation and analyze results."""
    
    print(f"\nSample jobs: {len(job_list)}")
    print("Jobs to evaluate:")
    for i, job in enumerate(job_list, 1):
        print(f"{i:2d}. {job['job_link'].split('/')[-1]:20} - {job['chunk_text'][:60]}...")
    
    print(f"\n{'-'*50}")
    print("Running Cerebras validation...")
    
    try:
        validator = CerebrasSchemaValidator()
        false_positives, metadata = await validator.validate_job_matches(job_list, resume_text)
        
        print(f"\nValidation Results for {resume_type}:")
        print(f"Models used: {metadata.get('models_used', [])}")
        print(f"Jobs evaluated: {metadata.get('jobs_evaluated', 0)}")
        print(f"Role mismatches detected: {len(false_positives)}")
        
        if false_positives:
            print(f"\n🚫 Flagged as role mismatches:")
            for url in false_positives:
                job_name = url.split('/')[-1]
                print(f"  - {job_name}")
        else:
            print("\n✅ No role mismatches detected.")
        
        # Analyze results
        print(f"\n📊 Analysis:")
        total_jobs = len(job_list)
        mismatch_rate = len(false_positives) / total_jobs * 100
        print(f"  - Mismatch detection rate: {mismatch_rate:.1f}% ({len(false_positives)}/{total_jobs})")
        
        # Show which jobs were NOT flagged
        not_flagged = [job for job in job_list if job['job_link'] not in false_positives]
        if not_flagged:
            print(f"\n✅ Jobs considered compatible:")
            for job in not_flagged:
                job_name = job['job_link'].split('/')[-1]
                print(f"  - {job_name}")
                
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
    
    # Run the enhanced test
    asyncio.run(test_role_mismatch_detection())