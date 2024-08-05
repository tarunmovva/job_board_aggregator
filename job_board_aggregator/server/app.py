"""FastAPI application for job board aggregator."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends
import os

from job_board_aggregator.config import reload_environment, get_environment_status, API_AUTH_HASH
from job_board_aggregator.server.routes import router

# Security scheme for authentication
security = HTTPBearer()

async def verify_auth_hash(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the authentication hash from the request header."""
    if not API_AUTH_HASH:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication not configured. API_AUTH_HASH environment variable is missing."
        )
    
    if credentials.credentials != API_AUTH_HASH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication hash. Please provide a valid API_AUTH_HASH in the Authorization header."
        )
    
    return credentials.credentials

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to handle startup and shutdown events."""
    # Startup
    print("🔄 Reloading environment variables on server startup...")
    if reload_environment():
        print("✅ Environment variables reloaded successfully")
        status = get_environment_status()
        print(f"🔐 API Auth Hash: {'✅ Found' if status['api_auth_hash'] else '❌ Missing'}")
        print(f"📌 Pinecone API Key: {'✅ Found' if status['pinecone_api_key'] else '❌ Missing'}")
        print(f"🤖 Groq API Key: {'✅ Found' if status['groq_api_key'] else '❌ Missing'}")
        print(f"🌐 Pinecone Environment: {status['pinecone_environment']}")
        print(f"📊 Pinecone Index: {status['pinecone_index_name']}")
        print(f"🧠 Groq Model: {status['groq_model']}")
        
        if not status['api_auth_hash']:
            print("⚠️  WARNING: API_AUTH_HASH not configured. Authentication will fail.")
    else:
        print("⚠️  Could not reload environment variables (dotenv not available)")
    
    yield
    
    # Shutdown (if needed)
    pass

# Reload environment variables on app creation
reload_environment()

# Create FastAPI app
app = FastAPI(
    title="Job Board Aggregator Server",
    description="Server for matching resumes with job postings",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes with authentication dependency
app.include_router(router, prefix="/server", dependencies=[Depends(verify_auth_hash)])

# Root route (no authentication required for basic health check)
@app.get("/")
async def root():
    """Root endpoint - health check without authentication."""
    return {"message": "Job Board Aggregator Server is running. Access API at /server/ with proper authentication."}

# Health check endpoint (no authentication required)
@app.get("/health")
async def health_check():
    """Health check endpoint - no authentication required."""
    status = get_environment_status()
    return {
        "status": "healthy",
        "api_auth_configured": status['api_auth_hash'],
        "pinecone_configured": status['pinecone_api_key'],
        "groq_configured": status['groq_api_key']
    }
