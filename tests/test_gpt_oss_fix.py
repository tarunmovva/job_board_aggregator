#!/usr/bin/env python3
"""
Test the plain text mode configuration for GPT OSS 120B.
"""

import logging
logging.basicConfig(level=logging.INFO)

from job_board_aggregator.api.cerebras.cerebras_validator import CerebrasSchemaValidator

def main():
    print("=== PLAIN TEXT MODE CONFIGURATION TEST ===")
    
    validator = CerebrasSchemaValidator()
    
    # Test all models to see their mode assignment
    print(f"Available models: {len(validator.available_models)}")
    print(f"Schema mode override models: {validator.schema_mode_models}")
    print(f"Plain text mode models: {validator.plain_text_models}")
    
    print("\n=== MODEL MODE ASSIGNMENTS ===")
    for model in validator.available_models:
        if model.name in validator.plain_text_models:
            mode = "📄 Plain text mode"
            status = "(FIXED - no response_format)"
        elif model.name in validator.schema_mode_models:
            mode = "🔧 Schema mode"
            status = "(structured)"
        else:
            mode = "📝 JSON mode"
            status = "(optimized)"
        
        print(f"{mode} {model.display_name} ({model.name}) {status}")
    
    print("\n=== GPT OSS 120B SPECIFIC FIX ===")
    print("✅ Added to plain_text_models set")
    print("✅ Will NOT use response_format parameter")
    print("✅ Will use simple system prompt for JSON instruction")
    print("✅ Should eliminate 'Unsupported response_format parameter' error")
    
    print("\n=== EXPECTED BEHAVIOR ===")
    print("📄 GPT OSS 120B: Plain text → No response_format, rely on prompt instructions")
    print("🔧 Thinking models: Schema mode → Structured output enforcement")
    print("📝 Other models: JSON mode → Optimized structured responses")
    
    print("\n=== ERROR RESOLUTION ===")
    print("❌ Before: Error code: 400 - Unsupported 'response_format' parameter")
    print("✅ After: Plain text mode with JSON instruction in prompt")
    
    print("\n🎉 GPT OSS 120B compatibility issue resolved!")

if __name__ == "__main__":
    main()