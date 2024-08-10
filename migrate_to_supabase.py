#!/usr/bin/env python3
"""
Migration script to transfer data from CSV and JSON files to Supabase database.

This script will:
1. Read companies.csv and populate the companies table
2. Read last_fetch.json and update company fetch times
3. Verify the migration was successful
4. Create backups of original files

Run this script AFTER setting up your Supabase database with the schema.
"""

import os
import csv
import json
import shutil
from datetime import datetime
from typing import Dict, List, Tuple

# Add the project root to Python path
import sys
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from job_board_aggregator.database.supabase_client import SupabaseClient


class MigrationManager:
    """Handles migration from files to Supabase database."""
    
    def __init__(self):
        """Initialize migration manager."""
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.csv_file = os.path.join(self.project_root, 'companies.csv')
        self.json_file = os.path.join(self.project_root, 'last_fetch.json')
        
        # Initialize Supabase client
        try:
            self.db = SupabaseClient()
            print("✅ Supabase client initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize Supabase client: {e}")
            print("Please check your .env file contains SUPABASE_URL and SUPABASE_SERVICE_KEY")
            sys.exit(1)
    
    def create_backups(self) -> bool:
        """Create backup copies of original files."""
        print("\n📦 Creating backups of original files...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            # Backup companies.csv
            if os.path.exists(self.csv_file):
                backup_csv = f"{self.csv_file}.backup_{timestamp}"
                shutil.copy2(self.csv_file, backup_csv)
                print(f"✅ Created backup: {backup_csv}")
            
            # Backup last_fetch.json
            if os.path.exists(self.json_file):
                backup_json = f"{self.json_file}.backup_{timestamp}"
                shutil.copy2(self.json_file, backup_json)
                print(f"✅ Created backup: {backup_json}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating backups: {e}")
            return False
    
    def read_companies_csv(self) -> List[Tuple[str, str]]:
        """Read companies from CSV file."""
        print(f"\n📖 Reading companies from {self.csv_file}...")
        
        if not os.path.exists(self.csv_file):
            print(f"❌ CSV file not found: {self.csv_file}")
            return []
        
        companies = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    company_name = row.get('Company Name', '').strip()
                    api_url = row.get('API URL', '').strip()
                    
                    if company_name and api_url:
                        companies.append((company_name, api_url))
                    else:
                        print(f"⚠️  Skipping invalid row: {row}")
            
            print(f"✅ Read {len(companies)} companies from CSV")
            return companies
            
        except Exception as e:
            print(f"❌ Error reading CSV file: {e}")
            return []
    
    def read_last_fetch_json(self) -> Dict:
        """Read last fetch data from JSON file."""
        print(f"\n📖 Reading fetch times from {self.json_file}...")
        
        if not os.path.exists(self.json_file):
            print(f"❌ JSON file not found: {self.json_file}")
            return {}
        
        try:
            with open(self.json_file, 'r', encoding='utf-8') as file:
                data = json.load(file)
            
            companies_data = data.get('companies', {})
            default_start_date = data.get('default_start_date', '')
            
            print(f"✅ Read fetch times for {len(companies_data)} companies")
            print(f"✅ Default start date: {default_start_date}")
            
            return {
                'companies': companies_data,
                'default_start_date': default_start_date
            }
            
        except Exception as e:
            print(f"❌ Error reading JSON file: {e}")
            return {}
    
    def migrate_companies(self, companies: List[Tuple[str, str]]) -> bool:
        """Migrate companies to database."""
        print(f"\n🚀 Migrating {len(companies)} companies to database...")
        
        success_count = 0
        failed_companies = []
        
        for company_name, api_url in companies:
            try:
                if self.db.add_company(company_name, api_url):
                    success_count += 1
                    if success_count % 50 == 0:  # Progress indicator
                        print(f"   📈 Migrated {success_count}/{len(companies)} companies...")
                else:
                    failed_companies.append(company_name)
                    
            except Exception as e:
                print(f"⚠️  Failed to migrate {company_name}: {e}")
                failed_companies.append(company_name)
        
        print(f"✅ Successfully migrated {success_count} companies")
        
        if failed_companies:
            print(f"⚠️  Failed to migrate {len(failed_companies)} companies:")
            for company in failed_companies[:10]:  # Show first 10
                print(f"   - {company}")
            if len(failed_companies) > 10:
                print(f"   ... and {len(failed_companies) - 10} more")
        
        return success_count > 0
    
    def migrate_fetch_times(self, fetch_data: Dict) -> bool:
        """Migrate fetch times to database."""
        companies_data = fetch_data.get('companies', {})
        default_start_date = fetch_data.get('default_start_date', '')
        
        print(f"\n🕒 Migrating fetch times for {len(companies_data)} companies...")
        
        # Migrate default start date
        if default_start_date:
            if self.db.set_default_start_date(default_start_date):
                print(f"✅ Set default start date: {default_start_date}")
            else:
                print(f"⚠️  Failed to set default start date")
        
        # Migrate company fetch times in batches
        batch_size = 100
        total_companies = len(companies_data)
        success_count = 0
        
        companies_list = list(companies_data.items())
        
        for i in range(0, total_companies, batch_size):
            batch = dict(companies_list[i:i + batch_size])
            
            if self.db.batch_update_fetch_times(batch):
                success_count += len(batch)
                print(f"   📈 Migrated fetch times: {success_count}/{total_companies}")
            else:
                print(f"⚠️  Failed to migrate batch {i//batch_size + 1}")
        
        print(f"✅ Successfully migrated fetch times for {success_count} companies")
        return success_count > 0
    
    def verify_migration(self, original_companies: List[Tuple[str, str]], original_fetch_data: Dict) -> bool:
        """Verify that migration was successful."""
        print(f"\n🔍 Verifying migration...")
        
        errors = []
        
        # Check company count
        db_company_count = self.db.get_company_count()
        csv_company_count = len(original_companies)
        
        if db_company_count != csv_company_count:
            errors.append(f"Company count mismatch: CSV has {csv_company_count}, DB has {db_company_count}")
        else:
            print(f"✅ Company count matches: {db_company_count}")
        
        # Check default start date
        db_default_date = self.db.get_default_start_date()
        json_default_date = original_fetch_data.get('default_start_date', '')
        
        if db_default_date != json_default_date:
            errors.append(f"Default start date mismatch: JSON has '{json_default_date}', DB has '{db_default_date}'")
        else:
            print(f"✅ Default start date matches: {db_default_date}")
        
        # Sample check of companies
        sample_companies = original_companies[:5]  # Check first 5 companies
        for company_name, api_url in sample_companies:
            db_company = self.db.get_company_by_name(company_name)
            if not db_company:
                errors.append(f"Company not found in DB: {company_name}")
            elif db_company['api_url'] != api_url:
                errors.append(f"API URL mismatch for {company_name}")
        
        if not errors:
            print("✅ Sample company verification passed")
        
        # Check fetch times for sample
        original_companies_data = original_fetch_data.get('companies', {})
        sample_fetch_companies = list(original_companies_data.keys())[:5]
        
        for company_name in sample_fetch_companies:
            original_time = original_companies_data[company_name]
            db_time = self.db.get_last_fetch_time(company_name)
            
            if db_time != original_time:
                errors.append(f"Fetch time mismatch for {company_name}: JSON has '{original_time}', DB has '{db_time}'")
        
        if not errors:
            print("✅ Sample fetch time verification passed")
        
        # Print verification results
        if errors:
            print(f"\n❌ Verification failed with {len(errors)} errors:")
            for error in errors:
                print(f"   - {error}")
            return False
        else:
            print(f"\n🎉 Migration verification successful!")
            return True
    
    def run_migration(self) -> bool:
        """Run the complete migration process."""
        print("🚀 Starting migration from files to Supabase database")
        print("=" * 60)
        
        # Test database connection
        if not self.db.test_connection():
            print("❌ Database connection failed. Please check your Supabase configuration.")
            return False
        
        # Create backups
        if not self.create_backups():
            print("❌ Failed to create backups. Aborting migration.")
            return False
        
        # Read original data
        companies = self.read_companies_csv()
        fetch_data = self.read_last_fetch_json()
        
        if not companies:
            print("❌ No companies found in CSV file. Aborting migration.")
            return False
        
        # Perform migration
        companies_migrated = self.migrate_companies(companies)
        fetch_times_migrated = self.migrate_fetch_times(fetch_data) if fetch_data else True
        
        if not companies_migrated:
            print("❌ Company migration failed. Aborting.")
            return False
        
        # Verify migration
        verification_passed = self.verify_migration(companies, fetch_data)
        
        if verification_passed:
            print("\n🎉 Migration completed successfully!")
            print("\nNext steps:")
            print("1. Update your .env file with Supabase credentials")
            print("2. Install supabase package: pip install supabase")
            print("3. Test the new database integration")
            print("4. Original files have been backed up")
            return True
        else:
            print("\n❌ Migration completed but verification failed.")
            print("Please check the errors above and run verification again.")
            return False


def main():
    """Main migration script."""
    print("Job Board Aggregator - Database Migration Tool")
    print("=" * 50)
    
    # Check environment variables
    if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_SERVICE_KEY'):
        print("❌ Missing environment variables!")
        print("\nPlease add to your .env file:")
        print("SUPABASE_URL=https://your-project-ref.supabase.co")
        print("SUPABASE_SERVICE_KEY=your-service-role-key")
        sys.exit(1)
    
    try:
        migration_manager = MigrationManager()
        success = migration_manager.run_migration()
        
        if success:
            print("\n✅ Migration completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Migration failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
