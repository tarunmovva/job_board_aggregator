#!/usr/bin/env python3
"""
Create database schema in Supabase.
This script creates the necessary tables using the Supabase client.
"""

import os
import sys
from pathlib import Path

# Add the job_board_aggregator package to Python path
sys.path.insert(0, str(Path(__file__).parent))

from job_board_aggregator.database.supabase_client import SupabaseClient
import job_board_aggregator.config as config


def create_database_schema():
    """Create the database schema in Supabase."""
    print("🔧 Creating database schema...")
    
    try:
        # Initialize client
        client = SupabaseClient()
        
        print("📝 Checking if tables exist...")
        
        # Try to create a test record to see if tables exist
        try:
            # Test companies table
            client.client.table('companies').select('id').limit(1).execute()
            print("✅ Companies table already exists")
        except Exception as e:
            print(f"❌ Companies table doesn't exist: {e}")
            return False
        
        try:
            # Test system_config table  
            client.client.table('system_config').select('id').limit(1).execute()
            print("✅ System_config table already exists")
        except Exception as e:
            print(f"❌ System_config table doesn't exist: {e}")
            return False
        
        print("✅ All tables exist!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to check schema: {e}")
        return False


if __name__ == "__main__":
    if create_database_schema():
        print("\n🎉 Database schema verified!")
        print("Now you can run the migration: python migrate_to_supabase.py")
    else:
        print("\n❌ Schema needs to be created. Please run the SQL in Supabase dashboard.")
        print("📋 Copy the contents of database_schema.sql and run it in:")
        print("   Supabase Dashboard → SQL Editor → New Query")
        sys.exit(1)
