#!/usr/bin/env python3
"""
Test all Cerebras models with our actual validator schema and rank by performance.
"""

import os
import json
import time
from typing import Dict, List, Any
from cerebras.cloud.sdk import Cerebras
from dataclasses import dataclass

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

@dataclass
class ValidatorTestResult:
    model_id: str
    success: bool
    response_time: float
    flagged_jobs: int
    error_message: str = None

class CerebrasValidatorTester:
    def __init__(self):
        api_key = os.environ.get("CERABRAS_API_KEY")
        if not api_key:
            raise ValueError("CERABRAS_API_KEY not found in environment variables.")
        self.client = Cerebras(api_key=api_key)
        
        # All 5 models we want to test
        self.models_to_test = [
            "llama-4-scout-17b-16e-instruct",
            "llama-3.3-70b", 
            "qwen-3-coder-480b",
            "llama-4-maverick-17b-128e-instruct",
            "qwen-3-235b-a22b-instruct-2507"
        ]
        
        # Use the EXACT same schema as our validator
        self.response_schema = {
            "type": "object",
            "properties": {
                "flagged_job_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of job URLs that are false positives"
                }
            },
            "required": ["flagged_job_urls"],
            "additionalProperties": False
        }
        
        # Sample test data - mix of good and bad matches
        self.test_jobs = [
            {
                "url": "https://example.com/job1",
                "title": "Senior Data Scientist",
                "description": "Build machine learning models using Python and TensorFlow"
            },
            {
                "url": "https://example.com/job2", 
                "title": "Marketing Manager",
                "description": "Develop marketing campaigns and manage social media"
            },
            {
                "url": "https://example.com/job3",
                "title": "Full Stack Developer", 
                "description": "Build web applications using React and Node.js"
            },
            {
                "url": "https://example.com/job4",
                "title": "Medical Doctor",
                "description": "Provide patient care and medical consultations"
            }
        ]
        
        self.resume_profile = """
        Senior Software Engineer with 5 years experience in Python, React, Node.js, 
        and full-stack web development. Expert in Django, FastAPI, JavaScript, and cloud platforms.
        """

    def test_model_with_validator_schema(self, model_id: str) -> ValidatorTestResult:
        """Test model with our exact validator schema and logic"""
        start_time = time.time()
        
        # Create validation prompt similar to our validator
        prompt = self._create_validation_prompt(self.test_jobs, self.resume_profile)
        
        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "You are a precision job-resume matching validator. Analyze each job against the candidate profile and flag URLs of jobs that are poor matches (false positives)."},
                    {"role": "user", "content": prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "validation_result",
                        "schema": self.response_schema,
                        "strict": True
                    }
                }
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            # Parse and validate response
            parsed = json.loads(content)
            flagged_jobs = len(parsed.get("flagged_job_urls", []))
            
            return ValidatorTestResult(
                model_id=model_id,
                success=True,
                response_time=response_time,
                flagged_jobs=flagged_jobs
            )
            
        except Exception as e:
            return ValidatorTestResult(
                model_id=model_id,
                success=False,
                response_time=time.time() - start_time,
                flagged_jobs=0,
                error_message=str(e)
            )

    def _create_validation_prompt(self, jobs: List[Dict], resume_text: str) -> str:
        """Create validation prompt matching our validator style"""
        prompt = f"""Analyze these jobs against the candidate profile for role mismatch detection.

CANDIDATE PROFILE:
{resume_text}

JOBS TO VALIDATE:
"""
        
        for i, job in enumerate(jobs, 1):
            prompt += f"""
Job {i}:
URL: {job['url']}
Title: {job['title']}
Description: {job['description']}
"""
        
        prompt += """
VALIDATION CRITERIA:
- Role Category Mismatch: Software Engineer ≠ Marketing Manager, Doctor, etc.
- Seniority Level Mismatch: Senior position for Junior candidate
- Technology Stack Mismatch: Java developer for Python-only role
- Domain Expertise Mismatch: Medical role for non-medical candidate

Return URLs of jobs that are FALSE POSITIVES (poor matches that should be removed).
Expected false positives: Marketing Manager, Medical Doctor (role mismatches)."""
        
        return prompt

    def run_performance_test(self) -> List[ValidatorTestResult]:
        """Test all models and rank by performance"""
        print("🎯 Testing all Cerebras models with validator schema...")
        print("=" * 65)
        
        results = []
        
        for model_id in self.models_to_test:
            print(f"\n🔍 Testing {model_id}...")
            
            result = self.test_model_with_validator_schema(model_id)
            results.append(result)
            
            if result.success:
                print(f"✅ SUCCESS: {result.response_time:.2f}s, flagged {result.flagged_jobs} jobs")
            else:
                print(f"❌ FAILED: {result.error_message}")
            
            time.sleep(1)  # Rate limiting
        
        return results

    def generate_performance_report(self, results: List[ValidatorTestResult]) -> None:
        """Generate performance ranking report"""
        print("\n" + "=" * 80)
        print("🏆 CEREBRAS VALIDATOR PERFORMANCE RANKING")
        print("=" * 80)
        
        # Sort successful models by speed
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        successful.sort(key=lambda x: x.response_time)
        
        print(f"\n✅ WORKING MODELS ({len(successful)}):")
        print("-" * 50)
        
        for i, result in enumerate(successful, 1):
            speed_rating = "🚀" if result.response_time < 0.5 else "⚡" if result.response_time < 1.0 else "🐌"
            print(f"{i}. {speed_rating} {result.model_id}")
            print(f"   ⏱️  {result.response_time:.2f}s")
            print(f"   🎯 Flagged {result.flagged_jobs}/4 jobs")
            print()
        
        if failed:
            print(f"❌ FAILED MODELS ({len(failed)}):")
            print("-" * 50)
            for result in failed:
                print(f"• {result.model_id}: {result.error_message}")
        
        print("🚀 FINAL RECOMMENDATION:")
        print("-" * 50)
        if len(successful) >= 5:
            print("✅ ALL 5 MODELS WORKING! Current validator can use all models.")
            print(f"⚡ Fastest: {successful[0].model_id} ({successful[0].response_time:.2f}s)")
            print(f"📊 Average speed: {sum(r.response_time for r in successful) / len(successful):.2f}s")
            print("\n🎯 OPTIMAL CONFIGURATION:")
            print("• Use top 3-4 fastest models for best performance")
            print("• 2-model consensus will be very fast")
            print("• Strict JSON schema enforcement confirmed working")
        else:
            print("⚠️  Some models not working. Use only successful models.")
        
        print("\n" + "=" * 80)

def main():
    """Run the Cerebras validator performance test"""
    tester = CerebrasValidatorTester()
    
    try:
        results = tester.run_performance_test()
        tester.generate_performance_report(results)
        
        # Save results
        results_data = []
        for result in results:
            results_data.append({
                "model_id": result.model_id,
                "success": result.success,
                "response_time": result.response_time,
                "flagged_jobs": result.flagged_jobs,
                "error_message": result.error_message
            })
        
        with open("cerebras_validator_performance.json", "w") as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\n💾 Results saved to: cerebras_validator_performance.json")
        
    except Exception as e:
        print(f"💥 Test failed: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())