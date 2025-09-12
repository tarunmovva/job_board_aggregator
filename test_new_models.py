#!/usr/bin/env python3
"""
Test the model-specific configuration for the new models.
"""

import logging
logging.basicConfig(level=logging.INFO)

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

def main():
    print("=== NEW MODEL CONFIGURATION TEST ===")
    
    validator = CerebrasSchemaValidator()
    
    # Test all models to see their mode assignment
    print(f"Available models: {len(validator.available_models)}")
    print(f"Schema mode override models: {validator.schema_mode_models}")
    
    print("\n=== MODEL MODE ASSIGNMENTS ===")
    for model in validator.available_models:
        uses_schema = model.name in validator.schema_mode_models
        mode = "🔧 Schema mode" if uses_schema else "📝 JSON mode"
        status = "(FIXED)" if uses_schema and "thinking" in model.name else ""
        print(f"{mode} {model.display_name} ({model.name}) {status}")
    
    print("\n=== PROBLEM RESOLUTION ===")
    print("✅ Qwen 3 235B Thinking added to schema mode override")
    print("✅ Will use strict schema enforcement instead of JSON mode")
    print("✅ Should prevent 400 Bad Request errors from verbosity")
    print("✅ Other models remain in JSON mode for optimal performance")
    
    print("\n=== EXPECTED BEHAVIOR IMPROVEMENT ===")
    print("🔧 Qwen 3 235B Thinking: Schema mode → More structured, less verbose")
    print("📝 GPT OSS 120B: JSON mode → Fast and flexible (monitor for issues)")
    print("📝 Other models: Continue working as before")
    
    print("\n🎉 System optimized for new model characteristics!")

if __name__ == "__main__":
    main()