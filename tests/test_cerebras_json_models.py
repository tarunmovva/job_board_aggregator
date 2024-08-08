#!/usr/bin/env python3
"""
Test script to check which Cerebras models support strict JSON schema enforcement.
This will help us expand our model pool for the validation system.
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
    # python-dotenv not installed, skip .env loading
    pass

@dataclass
class ModelTestResult:
    model_id: str
    supports_json_schema: bool
    supports_strict_mode: bool
    response_time: float
    error_message: str = None
    raw_response: str = None

class CerebrasJSONTester:
    def __init__(self):
        # Use the same env var name as the existing code (typo preserved for consistency)
        api_key = os.environ.get("CERABRAS_API_KEY")
        if not api_key:
            raise ValueError("CERABRAS_API_KEY not found in environment variables. Please set it to run the test.")
        self.client = Cerebras(api_key=api_key)
        
        # All available Cerebras models from documentation
        self.models_to_test = [
            # Production models
            "llama-4-scout-17b-16e-instruct",
            "llama3.1-8b",
            "llama-3.3-70b",
            "gpt-oss-120b",
            "qwen-3-32b",
            
            # Preview models
            "llama-4-maverick-17b-128e-instruct", 
            "qwen-3-235b-a22b-instruct-2507",
            "qwen-3-235b-a22b-thinking-2507",
            "qwen-3-coder-480b"
        ]
        
        # Test JSON schema - simple validation schema similar to our use case
        self.test_schema = {
            "type": "object",
            "properties": {
                "is_valid": {"type": "boolean"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"}
            },
            "required": ["is_valid", "confidence", "reasoning"],
            "additionalProperties": False
        }
        
        # Test prompt
        self.test_prompt = """
        Analyze this job description and determine if it's a valid software engineering role:
        
        "Senior Python Developer - Build scalable web applications using Django and FastAPI."
        
        Respond with your analysis in the required JSON format.
        """

    def test_model_basic_json(self, model_id: str) -> ModelTestResult:
        """Test if model can respond with basic JSON format (no schema enforcement)"""
        start_time = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "You must respond only with valid JSON in this format: {\"is_valid\": boolean, \"confidence\": number, \"reasoning\": string}"},
                    {"role": "user", "content": self.test_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            # Try to parse JSON
            json.loads(content)
            
            return ModelTestResult(
                model_id=model_id,
                supports_json_schema=True,
                supports_strict_mode=False,
                response_time=response_time,
                raw_response=content
            )
            
        except Exception as e:
            return ModelTestResult(
                model_id=model_id,
                supports_json_schema=False,
                supports_strict_mode=False,
                response_time=time.time() - start_time,
                error_message=str(e)
            )

    def test_model_strict_json_schema(self, model_id: str) -> ModelTestResult:
        """Test if model supports strict JSON schema enforcement"""
        start_time = time.time()
        
        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "Analyze the job description and respond with your assessment."},
                    {"role": "user", "content": self.test_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "validation_result",
                        "schema": self.test_schema,
                        "strict": True
                    }
                }
            )
            
            response_time = time.time() - start_time
            content = response.choices[0].message.content
            
            # Validate JSON against schema
            parsed = json.loads(content)
            
            # Basic validation that required fields exist
            required_fields = ["is_valid", "confidence", "reasoning"]
            if all(field in parsed for field in required_fields):
                return ModelTestResult(
                    model_id=model_id,
                    supports_json_schema=True,
                    supports_strict_mode=True,
                    response_time=response_time,
                    raw_response=content
                )
            else:
                return ModelTestResult(
                    model_id=model_id,
                    supports_json_schema=True,
                    supports_strict_mode=False,
                    response_time=response_time,
                    error_message="Missing required fields in response"
                )
            
        except Exception as e:
            # If strict mode fails, fall back to basic JSON test
            basic_result = self.test_model_basic_json(model_id)
            basic_result.error_message = f"Strict mode failed: {str(e)}"
            return basic_result

    def run_comprehensive_test(self) -> Dict[str, ModelTestResult]:
        """Test all models and return results"""
        print("🧪 Testing Cerebras models for JSON schema support...")
        print("=" * 60)
        
        results = {}
        
        for model_id in self.models_to_test:
            print(f"\n🔍 Testing {model_id}...")
            
            try:
                result = self.test_model_strict_json_schema(model_id)
                results[model_id] = result
                
                if result.supports_strict_mode:
                    print(f"✅ {model_id}: STRICT JSON SCHEMA SUPPORTED ({result.response_time:.2f}s)")
                elif result.supports_json_schema:
                    print(f"⚠️  {model_id}: Basic JSON only ({result.response_time:.2f}s)")
                else:
                    print(f"❌ {model_id}: JSON FAILED - {result.error_message}")
                    
            except Exception as e:
                print(f"💥 {model_id}: TEST FAILED - {str(e)}")
                results[model_id] = ModelTestResult(
                    model_id=model_id,
                    supports_json_schema=False,
                    supports_strict_mode=False,
                    response_time=0,
                    error_message=str(e)
                )
            
            # Rate limiting - small delay between tests
            time.sleep(1)
        
        return results

    def generate_report(self, results: Dict[str, ModelTestResult]) -> None:
        """Generate comprehensive test report"""
        print("\n" + "=" * 80)
        print("🎯 CEREBRAS JSON SCHEMA COMPATIBILITY REPORT")
        print("=" * 80)
        
        strict_models = []
        basic_models = []
        failed_models = []
        
        for model_id, result in results.items():
            if result.supports_strict_mode:
                strict_models.append((model_id, result.response_time))
            elif result.supports_json_schema:
                basic_models.append((model_id, result.response_time))
            else:
                failed_models.append((model_id, result.error_message))
        
        print(f"\n✅ STRICT JSON SCHEMA MODELS ({len(strict_models)}):")
        print("-" * 50)
        for model_id, response_time in sorted(strict_models, key=lambda x: x[1]):
            print(f"  • {model_id:<35} ({response_time:.2f}s)")
        
        print(f"\n⚠️  BASIC JSON ONLY MODELS ({len(basic_models)}):")
        print("-" * 50)
        for model_id, response_time in sorted(basic_models, key=lambda x: x[1]):
            print(f"  • {model_id:<35} ({response_time:.2f}s)")
        
        print(f"\n❌ FAILED MODELS ({len(failed_models)}):")
        print("-" * 50)
        for model_id, error in failed_models:
            print(f"  • {model_id:<35} - {error}")
        
        print(f"\n🏆 RECOMMENDED FOR CEREBRAS VALIDATOR:")
        print("-" * 50)
        
        if strict_models:
            # Sort by speed for recommendations
            sorted_strict = sorted(strict_models, key=lambda x: x[1])
            
            current_models = [
                "llama-4-scout-17b-16e-instruct",
                "llama-3.3-70b", 
                "qwen-3-coder-480b"
            ]
            
            new_models = []
            for model_id, speed in sorted_strict:
                if model_id not in current_models:
                    new_models.append(model_id)
            
            print("Current models (already in use):")
            for model in current_models:
                if model in [m[0] for m in strict_models]:
                    speed = next(s for m, s in strict_models if m == model)
                    print(f"  ✓ {model} ({speed:.2f}s)")
                else:
                    print(f"  ⚠ {model} (needs retesting)")
            
            if new_models:
                print("\nRecommended additions:")
                for model in new_models[:3]:  # Top 3 new models
                    speed = next(s for m, s in sorted_strict if m == model)
                    print(f"  + {model} ({speed:.2f}s)")
        
        print("\n" + "=" * 80)

def main():
    """Run the comprehensive Cerebras JSON model test"""
    tester = CerebrasJSONTester()
    
    try:
        results = tester.run_comprehensive_test()
        tester.generate_report(results)
        
        # Save detailed results to JSON file
        detailed_results = {}
        for model_id, result in results.items():
            detailed_results[model_id] = {
                "supports_json_schema": result.supports_json_schema,
                "supports_strict_mode": result.supports_strict_mode,
                "response_time": result.response_time,
                "error_message": result.error_message,
                "raw_response": result.raw_response
            }
        
        with open("cerebras_model_test_results.json", "w") as f:
            json.dump(detailed_results, f, indent=2)
        
        print(f"\n💾 Detailed results saved to: cerebras_model_test_results.json")
        
    except Exception as e:
        print(f"💥 Test suite failed: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())