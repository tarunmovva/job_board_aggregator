#!/usr/bin/env python3
"""
Quick start script for Supabase migration.

This script helps you quickly set up and test the Supabase integration.
"""

import os
import sys
import subprocess

def print_header(title):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_step(step, description):
    """Print a formatted step."""
    print(f"\n📍 Step {step}: {description}")
    print("-" * 40)

def check_dependencies():
    """Check if required dependencies are installed."""
    print("🔍 Checking dependencies...")
    
    missing = []
    
    try:
        import supabase
        print("✅ supabase package installed")
    except ImportError:
        missing.append("supabase")
    
    try:
        import psycopg2
        print("✅ psycopg2 package installed")
    except ImportError:
        missing.append("psycopg2-binary")
    
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("\n📦 Installing missing packages...")
        
        for package in missing:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✅ Installed {package}")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {package}")
                return False
    
    return True

def check_environment():
    """Check environment configuration."""
    print("🔍 Checking environment configuration...")
    
    env_file = ".env"
    if not os.path.exists(env_file):
        print(f"❌ {env_file} file not found")
        print("\n📋 Creating .env.example as template...")
        print("Please copy .env.example to .env and fill in your Supabase credentials")
        return False
    
    # Load environment
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("⚠️  python-dotenv not available, using system environment")
    
    # Check required variables
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_SERVICE_KEY',
        'GROQ_API_KEY',
        'PINECONE_API_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var} is set")
        else:
            missing_vars.append(var)
            print(f"❌ {var} is missing")
    
    if missing_vars:
        print(f"\n❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please add them to your .env file")
        return False
    
    return True

def test_connection():
    """Test database connection."""
    print("🔌 Testing Supabase connection...")
    
    try:
        # Add project root to path
        project_root = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, project_root)
        
        from job_board_aggregator.database.supabase_client import SupabaseClient
        
        client = SupabaseClient()
        if client.test_connection():
            print("✅ Supabase connection successful")
            return True
        else:
            print("❌ Supabase connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def run_migration():
    """Run the migration script."""
    print("🚀 Running migration script...")
    
    try:
        # Run migration script
        result = subprocess.run([
            sys.executable, "migrate_to_supabase.py"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Migration completed successfully")
            print(result.stdout)
            return True
        else:
            print("❌ Migration failed")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False

def run_tests():
    """Run integration tests."""
    print("🧪 Running integration tests...")
    
    try:
        result = subprocess.run([
            sys.executable, "test_supabase_integration.py"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All tests passed")
            print(result.stdout)
            return True
        else:
            print("❌ Some tests failed")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

def enable_database_mode():
    """Enable database mode in environment."""
    print("🔄 Enabling database mode...")
    
    env_file = ".env"
    if not os.path.exists(env_file):
        print("❌ .env file not found")
        return False
    
    # Read current .env file
    with open(env_file, 'r') as f:
        lines = f.readlines()
    
    # Update or add USE_SUPABASE_DATABASE line
    updated = False
    for i, line in enumerate(lines):
        if line.startswith('USE_SUPABASE_DATABASE='):
            lines[i] = 'USE_SUPABASE_DATABASE=true\n'
            updated = True
            break
    
    if not updated:
        lines.append('USE_SUPABASE_DATABASE=true\n')
    
    # Write back to file
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    print("✅ Database mode enabled")
    return True

def main():
    """Main quick start process."""
    print_header("Supabase Migration Quick Start")
    
    print("This script will help you migrate from CSV/JSON files to Supabase database.")
    print("\nWhat this script does:")
    print("1. Check and install required dependencies")
    print("2. Verify environment configuration")
    print("3. Test Supabase connection")
    print("4. Run migration from files to database")
    print("5. Run integration tests")
    print("6. Enable database mode")
    
    input("\nPress Enter to continue or Ctrl+C to exit...")
    
    # Step 1: Check dependencies
    print_step(1, "Checking Dependencies")
    if not check_dependencies():
        print("❌ Dependency check failed. Please install missing packages manually.")
        return False
    
    # Step 2: Check environment
    print_step(2, "Checking Environment")
    if not check_environment():
        print("❌ Environment check failed. Please configure your .env file.")
        print("\nRequired variables:")
        print("- SUPABASE_URL=https://your-project-ref.supabase.co")
        print("- SUPABASE_SERVICE_KEY=your_service_role_key")
        print("- GROQ_API_KEY=your_groq_key")
        print("- PINECONE_API_KEY=your_pinecone_key")
        return False
    
    # Step 3: Test connection
    print_step(3, "Testing Database Connection")
    if not test_connection():
        print("❌ Connection test failed. Please check your Supabase credentials.")
        return False
    
    # Step 4: Run migration
    print_step(4, "Running Migration")
    if not run_migration():
        print("❌ Migration failed. Please check the error messages above.")
        return False
    
    # Step 5: Run tests
    print_step(5, "Running Integration Tests")
    if not run_tests():
        print("❌ Tests failed. Migration may have issues.")
        print("You can run tests manually: python test_supabase_integration.py")
    
    # Step 6: Enable database mode
    print_step(6, "Enabling Database Mode")
    if not enable_database_mode():
        print("❌ Failed to enable database mode. Please manually set USE_SUPABASE_DATABASE=true in .env")
        return False
    
    # Success!
    print_header("Migration Complete!")
    print("🎉 Supabase migration completed successfully!")
    print("\nWhat happened:")
    print("✅ Dependencies installed")
    print("✅ Environment configured")
    print("✅ Database connection tested")
    print("✅ Data migrated to Supabase")
    print("✅ Integration tests passed")
    print("✅ Database mode enabled")
    
    print("\nNext steps:")
    print("1. Your original files have been backed up")
    print("2. The application now uses Supabase database")
    print("3. Test your application: python run_server.py")
    print("4. Monitor usage in Supabase dashboard")
    
    print("\nNeed help? Check SUPABASE_MIGRATION_GUIDE.md for detailed instructions.")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Quick start interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
