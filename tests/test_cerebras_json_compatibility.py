#!/usr/bin/env python3
"""
Test Cerebras JSON schema compatibility levels.
Determine what level of JSON schema enforcement is actually supported.
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
class JSONTestResult:
    model_id: str
    test_type: str
    success: bool
    response_time: float
    error_message: str = None
    raw_response: str = None

class CerebrasJSONCompatibilityTester:
    def __init__(self):
        # Use the same env var name as the existing code (typo preserved for consistency)
        api_key = os.environ.get("CERABRAS_API_KEY")
        if not api_key:
            raise ValueError("CERABRAS_API_KEY not found in environment variables. Please set it to run the test.")
        self.client = Cerebras(api_key=api_key)
        
        # Test a subset of the best models
        self.models_to_test = [
            "llama-4-scout-17b-16e-instruct",
            "llama-3.3-70b", 
            "qwen-3-coder-480b",
            "llama-4-maverick-17b-128e-instruct",
            "qwen-3-235b-a22b-instruct-2507"
        ]
        
        self.test_prompt = """
        Analyze this job description and determine if it matches the candidate profile:
        
        Job: "Senior Data Scientist - Use Python and ML to build predictive models"
        Candidate: "Software Engineer with 5 years Java/C++ experience"
        
        Respond with your analysis.
        """

    def test_basic_json_object(self, model_id: str) -> JSONTestResult:
        """Test basic JSON object response format"""
        start_time = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "You must respond only with valid JSON in this format: {\"is_match\": boolean, \"confidence\": number, \"reasoning\": string}"},
                    {"role": "user", "content": self.test_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            # Try to parse JSON
            parsed = json.loads(content)
            
            return JSONTestResult(
                model_id=model_id,
                test_type="basic_json_object",
                success=True,
                response_time=response_time,
                raw_response=content
            )
            
        except Exception as e:
            return JSONTestResult(
                model_id=model_id,
                test_type="basic_json_object",
                success=False,
                response_time=time.time() - start_time,
                error_message=str(e)
            )

    def test_json_schema_no_strict(self, model_id: str) -> JSONTestResult:
        """Test JSON schema without strict enforcement"""
        start_time = time.time()
        
        schema = {
            "type": "object",
            "properties": {
                "is_match": {"type": "boolean"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"}
            },
            "required": ["is_match", "confidence", "reasoning"]
        }
        
        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "Analyze the job-candidate match carefully."},
                    {"role": "user", "content": self.test_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "match_analysis",
                        "schema": schema
                    }
                }
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            # Validate JSON against schema
            parsed = json.loads(content)
            required_fields = ["is_match", "confidence", "reasoning"]
            if all(field in parsed for field in required_fields):
                return JSONTestResult(
                    model_id=model_id,
                    test_type="json_schema_no_strict",
                    success=True,
                    response_time=response_time,
                    raw_response=content
                )
            else:
                return JSONTestResult(
                    model_id=model_id,
                    test_type="json_schema_no_strict",
                    success=False,
                    response_time=response_time,
                    error_message="Missing required fields in response"
                )
            
        except Exception as e:
            return JSONTestResult(
                model_id=model_id,
                test_type="json_schema_no_strict",
                success=False,
                response_time=time.time() - start_time,
                error_message=str(e)
            )

    def test_json_schema_with_strict(self, model_id: str) -> JSONTestResult:
        """Test JSON schema with strict enforcement"""
        start_time = time.time()
        
        schema = {
            "type": "object",
            "properties": {
                "is_match": {"type": "boolean"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"}
            },
            "required": ["is_match", "confidence", "reasoning"],
            "additionalProperties": False
        }
        
        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "Analyze the job-candidate match carefully."},
                    {"role": "user", "content": self.test_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "match_analysis",
                        "schema": schema,
                        "strict": True
                    }
                }
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            # Validate JSON against schema
            parsed = json.loads(content)
            required_fields = ["is_match", "confidence", "reasoning"]
            if all(field in parsed for field in required_fields):
                return JSONTestResult(
                    model_id=model_id,
                    test_type="json_schema_with_strict",
                    success=True,
                    response_time=response_time,
                    raw_response=content
                )
            else:
                return JSONTestResult(
                    model_id=model_id,
                    test_type="json_schema_with_strict",
                    success=False,
                    response_time=response_time,
                    error_message="Missing required fields in response"
                )
            
        except Exception as e:
            return JSONTestResult(
                model_id=model_id,
                test_type="json_schema_with_strict",
                success=False,
                response_time=time.time() - start_time,
                error_message=str(e)
            )

    def run_comprehensive_test(self) -> Dict[str, List[JSONTestResult]]:
        """Test all models with different JSON formats"""
        print("🧪 Testing Cerebras JSON Schema Compatibility Levels...")
        print("=" * 70)
        
        results = {}
        
        for model_id in self.models_to_test:
            print(f"\n🔍 Testing {model_id}...")
            model_results = []
            
            # Test 1: Basic JSON Object
            print("  📋 Testing basic JSON object...")
            result1 = self.test_basic_json_object(model_id)
            model_results.append(result1)
            if result1.success:
                print(f"    ✅ Basic JSON: SUCCESS ({result1.response_time:.2f}s)")
            else:
                print(f"    ❌ Basic JSON: FAILED - {result1.error_message}")
            
            # Test 2: JSON Schema (no strict)
            print("  📐 Testing JSON schema (no strict)...")
            result2 = self.test_json_schema_no_strict(model_id)
            model_results.append(result2)
            if result2.success:
                print(f"    ✅ JSON Schema: SUCCESS ({result2.response_time:.2f}s)")
            else:
                print(f"    ❌ JSON Schema: FAILED - {result2.error_message}")
            
            # Test 3: JSON Schema (strict)
            print("  🔒 Testing JSON schema (strict)...")
            result3 = self.test_json_schema_with_strict(model_id)
            model_results.append(result3)
            if result3.success:
                print(f"    ✅ JSON Schema Strict: SUCCESS ({result3.response_time:.2f}s)")
            else:
                print(f"    ❌ JSON Schema Strict: FAILED - {result3.error_message}")
            
            results[model_id] = model_results
            time.sleep(1)  # Rate limiting
        
        return results

    def generate_compatibility_report(self, results: Dict[str, List[JSONTestResult]]) -> None:
        """Generate comprehensive compatibility report"""
        print("\n" + "=" * 80)
        print("🎯 CEREBRAS JSON COMPATIBILITY ANALYSIS")
        print("=" * 80)
        
        # Analyze by capability level
        basic_json_models = []
        json_schema_models = []
        strict_schema_models = []
        
        for model_id, model_results in results.items():
            basic_success = any(r.test_type == "basic_json_object" and r.success for r in model_results)
            schema_success = any(r.test_type == "json_schema_no_strict" and r.success for r in model_results)
            strict_success = any(r.test_type == "json_schema_with_strict" and r.success for r in model_results)
            
            if strict_success:
                strict_schema_models.append(model_id)
            elif schema_success:
                json_schema_models.append(model_id)
            elif basic_success:
                basic_json_models.append(model_id)
        
        print(f"\n🏆 STRICT JSON SCHEMA MODELS ({len(strict_schema_models)}):")
        for model in strict_schema_models:
            print(f"  ✅ {model}")
        
        print(f"\n📐 JSON SCHEMA MODELS (no strict) ({len(json_schema_models)}):")
        for model in json_schema_models:
            print(f"  📋 {model}")
        
        print(f"\n📋 BASIC JSON ONLY MODELS ({len(basic_json_models)}):")
        for model in basic_json_models:
            print(f"  ⚠️  {model}")
        
        print(f"\n🚀 RECOMMENDATIONS FOR CURRENT VALIDATOR:")
        print("-" * 50)
        
        if strict_schema_models:
            print("✅ UPGRADE OPPORTUNITY: Strict schema models found!")
            print("  • Current validator can use strict mode")
            print("  • Perfect schema enforcement available")
            for model in strict_schema_models[:3]:  # Top 3
                print(f"  • ADD: {model}")
        elif json_schema_models:
            print("📐 CURRENT STATUS: JSON Schema (no strict) supported")
            print("  • Remove 'strict: true' from current implementation")
            print("  • Schema validation available but not enforced")
            print("  • All current models should work with schema (no strict)")
        else:
            print("⚠️  LIMITATION: Only basic JSON object support")
            print("  • Switch to json_object response format")
            print("  • Use prompt engineering for structure")
        
        print("\n💡 IMPLEMENTATION RECOMMENDATION:")
        print("-" * 50)
        if json_schema_models and not strict_schema_models:
            print("🔧 MODIFY current implementation:")
            print("  1. Remove 'strict: true' from response_format")
            print("  2. Keep json_schema structure")
            print("  3. Rely on prompt engineering for validation")
            print("  4. Current models will work better")
        
        print("\n" + "=" * 80)

def main():
    """Run the comprehensive Cerebras JSON compatibility test"""
    tester = CerebrasJSONCompatibilityTester()
    
    try:
        results = tester.run_comprehensive_test()
        tester.generate_compatibility_report(results)
        
        # Save detailed results
        detailed_results = {}
        for model_id, model_results in results.items():
            detailed_results[model_id] = {}
            for result in model_results:
                detailed_results[model_id][result.test_type] = {
                    "success": result.success,
                    "response_time": result.response_time,
                    "error_message": result.error_message,
                    "raw_response": result.raw_response
                }
        
        with open("cerebras_json_compatibility_results.json", "w") as f:
            json.dump(detailed_results, f, indent=2)
        
        print(f"\n💾 Detailed results saved to: cerebras_json_compatibility_results.json")
        
    except Exception as e:
        print(f"💥 Test suite failed: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())