#!/usr/bin/env python3
"""
Migrate timestamps from last_fetch.json to Supabase database.
"""

import os
import json
import sys
from datetime import datetime
from job_board_aggregator.config import reload_environment, LAST_RUN_FILE, logger
from job_board_aggregator.database.supabase_client import SupabaseClient

def migrate_timestamps():
    """Migrate timestamps from JSON file to Supabase database."""
    print("🔄 Starting timestamp migration from JSON to Supabase...")
    
    # Reload environment to ensure we have the latest settings
    reload_environment()
    
    # Check if database mode is enabled
    use_db = os.environ.get('USE_SUPABASE_DATABASE', '').lower() == 'true'
    if not use_db:
        print("❌ Database mode is not enabled. Set USE_SUPABASE_DATABASE=true in .env file.")
        return False
    
    # Check if JSON file exists
    if not os.path.exists(LAST_RUN_FILE):
        print(f"❌ JSON file not found: {LAST_RUN_FILE}")
        return False
    
    try:
        # Initialize Supabase client
        print("🔌 Connecting to Supabase...")
        client = SupabaseClient()
        
        # Read timestamps from JSON file
        print(f"📖 Reading timestamps from {LAST_RUN_FILE}...")
        with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        
        company_timestamps = data.get('companies', {})
        default_start_date = data.get('default_start_date')
        
        print(f"📊 Found {len(company_timestamps)} company timestamps in JSON file")
        
        if default_start_date:
            print(f"📅 Default start date: {default_start_date}")
        
        # Migrate company timestamps
        migrated_count = 0
        failed_count = 0
        
        print("🚀 Migrating company timestamps...")
        for company_name, timestamp in company_timestamps.items():
            try:
                # Update timestamp in database
                success = client.update_fetch_time(company_name, timestamp)
                if success:
                    migrated_count += 1
                    if migrated_count % 50 == 0:
                        print(f"✅ Migrated {migrated_count}/{len(company_timestamps)} timestamps...")
                else:
                    failed_count += 1
                    print(f"⚠️  Failed to migrate timestamp for {company_name}")
            except Exception as e:
                failed_count += 1
                print(f"❌ Error migrating {company_name}: {e}")
        
        # Migrate default start date to system_config
        if default_start_date:
            try:
                print("📅 Migrating default start date...")
                client.set_config('default_start_date', default_start_date)
                print("✅ Default start date migrated successfully")
            except Exception as e:
                print(f"⚠️  Failed to migrate default start date: {e}")
        
        print(f"\n🎉 Migration completed!")
        print(f"✅ Successfully migrated: {migrated_count} timestamps")
        print(f"❌ Failed migrations: {failed_count}")
        
        if failed_count == 0:
            print(f"🎯 Perfect! All timestamps migrated successfully.")
        
        return failed_count == 0
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def verify_migration():
    """Verify that timestamps were migrated correctly."""
    print("\n🔍 Verifying migration...")
    
    try:
        # Initialize Supabase client
        client = SupabaseClient()
        
        # Read original data from JSON
        with open(LAST_RUN_FILE, 'r', encoding='utf-8-sig') as f:
            original_data = json.load(f)
        
        original_timestamps = original_data.get('companies', {})
        
        # Check a sample of companies
        sample_companies = list(original_timestamps.keys())[:10]
        
        print(f"📋 Checking {len(sample_companies)} sample companies...")
        
        all_match = True
        for company_name in sample_companies:
            original_time = original_timestamps[company_name]
            db_time = client.get_last_fetch_time(company_name)
            
            if db_time == original_time:
                print(f"✅ {company_name}: ✓")
            else:
                print(f"❌ {company_name}: Original={original_time}, DB={db_time}")
                all_match = False
        
        # Check total count
        all_companies = client.get_all_companies()
        companies_with_timestamps = 0
        for company in all_companies:
            if company.get('last_fetch_time'):
                companies_with_timestamps += 1
        
        print(f"📊 Companies with timestamps in DB: {companies_with_timestamps}/{len(all_companies)}")
        print(f"📊 Original timestamp count: {len(original_timestamps)}")
        
        if all_match and companies_with_timestamps >= len(original_timestamps):
            print("🎉 Verification successful! All timestamps migrated correctly.")
            return True
        else:
            print("⚠️  Verification found some issues. Please check the logs above.")
            return False
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def backup_json_file():
    """Create a backup of the JSON file before migration."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{LAST_RUN_FILE}.backup_{timestamp}"
        
        import shutil
        shutil.copy2(LAST_RUN_FILE, backup_file)
        print(f"📦 Created backup: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"⚠️  Failed to create backup: {e}")
        return None

def main():
    """Main migration function."""
    print("🚀 Timestamp Migration to Supabase")
    print("=" * 50)
    
    # Create backup
    backup_file = backup_json_file()
    
    # Run migration
    success = migrate_timestamps()
    
    if success:
        # Verify migration
        verified = verify_migration()
        
        if verified:
            print("\n🎉 Migration and verification completed successfully!")
            print("✅ Fetch operations will now use Supabase for timestamp tracking.")
            
            if backup_file:
                print(f"📦 JSON backup available at: {backup_file}")
        else:
            print("\n⚠️  Migration completed but verification failed.")
            print("Please check the database manually.")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
        
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
