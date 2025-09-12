#!/usr/bin/env python3
"""
Debug GPT OSS 120B empty content issue.
"""

import logging
logging.basicConfig(level=logging.INFO)

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

def main():
    print("=== GPT OSS 120B DEBUGGING ===")
    
    validator = CerebrasSchemaValidator()
    
    # Check GPT OSS 120B configuration
    gpt_oss_model = None
    for model in validator.available_models:
        if model.name == 'gpt-oss-120b':
            gpt_oss_model = model
            break
    
    if not gpt_oss_model:
        print("❌ GPT OSS 120B not found in available models")
        return
    
    print(f"✅ Found GPT OSS 120B: {gpt_oss_model.display_name}")
    print(f"   Model name: {gpt_oss_model.name}")
    print(f"   Context tokens: {gpt_oss_model.context_tokens}")
    
    # Check model categorization
    is_plain_text = gpt_oss_model.name in validator.plain_text_models
    is_schema = gpt_oss_model.name in validator.schema_mode_models
    
    print(f"\n=== MODEL CONFIGURATION ===")
    print(f"Plain text mode: {is_plain_text}")
    print(f"Schema mode: {is_schema}")
    print(f"Default JSON mode: {not is_plain_text and not is_schema}")
    
    if is_plain_text:
        print("✅ Correctly configured for plain text mode")
    else:
        print("❌ Not in plain text mode - this could be the issue!")
    
    print(f"\n=== POSSIBLE ISSUES ===")
    print("1. Model doesn't understand the prompt format")
    print("2. Model requires different prompt structure")
    print("3. Model has limitations we're not aware of")
    print("4. API response format is different than expected")
    
    print(f"\n=== DEBUGGING STEPS ===")
    print("1. Enhanced logging added to capture response details")
    print("2. Simplified prompt structure for better compatibility")
    print("3. Next: Monitor production logs for GPT OSS 120B response details")
    
    print(f"\n=== IMPROVED PROMPT STRUCTURE ===")
    print("Old: Complex job validation instructions")
    print("New: Simple 'analyze and return JSON' instruction")
    print("This should be easier for the model to understand")
    
    print(f"\n🔍 Monitoring required for next production run!")

if __name__ == "__main__":
    main()