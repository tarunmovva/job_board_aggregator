"""Configuration constants for the job board aggregator."""

import os
import logging
import sys

"""Configuration constants for the job board aggregator."""

import os
import logging
import sys

def reload_environment():
    """Force reload environment variables from .env file."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        return True
    except ImportError:
        # python-dotenv not installed, skip .env loading
        return False

def get_environment_status():
    """Get status of key environment variables."""
    status = {
        'pinecone_api_key': bool(os.getenv('PINECONE_API_KEY')),
        'groq_api_key': bool(os.getenv('GROQ_API_KEY')),
        'api_auth_hash': bool(os.getenv('API_AUTH_HASH')),
        'pinecone_environment': os.getenv('PINECONE_ENVIRONMENT'),
        'pinecone_index_name': os.getenv('PINECONE_INDEX_NAME'),
        'groq_model': os.getenv('GROQ_MODEL'),
        'supabase_url': bool(os.getenv('SUPABASE_URL')),
        'supabase_service_key': bool(os.getenv('SUPABASE_SERVICE_KEY')),
    }
    return status

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass

# API Authentication configuration
API_AUTH_HASH = os.environ.get("API_AUTH_HASH")

# Pinecone configuration
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT", "us-east-1")  # Default to AWS us-east-1
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "job-board-index")
PINECONE_NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "jobs")  # Default namespace for jobs

# Legacy vector DB path (kept for potential cleanup)
VECTOR_DB_PATH = os.environ.get("JOB_AGGREGATOR_VECTOR_DB", "vector_db")

# Supabase configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# API client configuration
API_TIMEOUT = int(os.environ.get("JOB_AGGREGATOR_TIMEOUT", "10"))

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_FILE = os.environ.get("JOB_AGGREGATOR_LOG", "job_aggregator.log")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)