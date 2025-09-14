"""Run the server."""

import os
import uvicorn

# Force reload environment variables from .env file
try:
    from dotenv import load_dotenv
    print("🔄 Reloading environment variables from .env file...")
    load_dotenv(override=True)  # override=True forces reload of existing variables
    print("✅ Environment variables reloaded successfully")
    
    # Verify key environment variables are loaded
    pinecone_key = os.getenv('PINECONE_API_KEY')
    groq_key = os.getenv('GROQ_API_KEY')
    
    if pinecone_key:
        print(f"📌 PINECONE_API_KEY: {pinecone_key[:15]}...{pinecone_key[-10:]}")
    else:
        print("⚠️  PINECONE_API_KEY: Not found!")
    
    if groq_key:
        print(f"🤖 GROQ_API_KEY: {groq_key[:15]}...{groq_key[-10:]}")
    else:
        print("⚠️  GROQ_API_KEY: Not found!")
    
    print(f"🌐 PINECONE_ENVIRONMENT: {os.getenv('PINECONE_ENVIRONMENT')}")
    print(f"📊 PINECONE_INDEX_NAME: {os.getenv('PINECONE_INDEX_NAME')}")
    print(f"🧠 GROQ_MODEL: {os.getenv('GROQ_MODEL')}")
    
except ImportError:
    print("⚠️  python-dotenv not installed, skipping .env file reload")

if __name__ == "__main__":
    # Check for minimal logging mode
    minimal_logging = os.getenv('MINIMAL_LOGGING', 'false').lower() == 'true'
    
    if minimal_logging:
        print("🔇 Minimal logging mode enabled - Starting server...")
        # Configure uvicorn for minimal output
        uvicorn.run(
            "job_board_aggregator.server.app:app", 
            host="0.0.0.0", 
            port=8080, 
            reload=True,
            log_level="warning",  # Only warnings and errors
            access_log=False      # Disable access logs
        )
    else:
        print("🚀 Starting Job Board Aggregator Server...")
        uvicorn.run("job_board_aggregator.server.app:app", host="0.0.0.0", port=8080, reload=True)