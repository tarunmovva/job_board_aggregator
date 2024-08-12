#!/usr/bin/env python3
"""
Script to remove failed companies from companies.csv based on the failed_companies.txt file
"""

import csv
import re
import os
from typing import List

def parse_failed_companies_file(file_path: str) -> List[str]:
    """Parse the failed_companies.txt file to extract company names"""
    failed_companies = []
    
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            # Skip empty lines, headers, and separator lines
            if not line or line.startswith('Companies that failed') or line.startswith('='):
                continue
            
            # Extract company name from numbered list (e.g., "1. Company Name")
            match = re.match(r'^\d+\.\s*(.+)$', line)
            if match:
                company_name = match.group(1).strip()
                failed_companies.append(company_name)
                print(f"Found failed company: {company_name}")
    
    return failed_companies

def clean_companies_csv_from_file(csv_file: str, failed_companies_file: str, output_file: str):
    """Remove failed companies from the CSV file based on the failed_companies.txt file"""
    
    # Parse the failed companies file
    failed_companies = parse_failed_companies_file(failed_companies_file)
    failed_companies_set = set(failed_companies)
    
    print(f"\nFound {len(failed_companies)} failed companies to remove:")
    for i, company in enumerate(failed_companies, 1):
        print(f"{i:2d}. {company}")
    
    kept_companies = []
    removed_companies = []
    
    # Read the original CSV file
    with open(csv_file, 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        
        for row in csv_reader:
            company_name = row['Company Name']
            
            if company_name in failed_companies_set:
                removed_companies.append(company_name)
                print(f"❌ Removing: {company_name}")
            else:
                kept_companies.append(row)
    
    # Write the cleaned file
    with open(output_file, 'w', newline='', encoding='utf-8') as file:
        fieldnames = ['Company Name', 'API URL']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        
        writer.writeheader()
        for company in kept_companies:
            writer.writerow(company)
    
    print(f"\n📊 Summary:")
    print(f"Total companies in original file: {len(kept_companies) + len(removed_companies)}")
    print(f"Companies kept: {len(kept_companies)}")
    print(f"Companies removed: {len(removed_companies)}")
    print(f"Expected removals: {len(failed_companies)}")
    
    if len(removed_companies) != len(failed_companies):
        print(f"\n⚠️  Warning: Expected to remove {len(failed_companies)} companies but removed {len(removed_companies)}")
        
        # Show which failed companies were not found
        not_found = failed_companies_set - set(removed_companies)
        if not_found:
            print(f"Failed companies not found in CSV:")
            for company in sorted(not_found):
                print(f"  - {company}")
        
        # Show which companies were found and removed
        if removed_companies:
            print(f"\nCompanies successfully removed:")
            for company in sorted(removed_companies):
                print(f"  ✅ {company}")
    
    print(f"\n✅ Cleaned CSV saved as: {output_file}")
    
    return len(kept_companies), len(removed_companies)

def main():
    csv_file = 'companies.csv'
    failed_companies_file = 'failed_companies.txt'
    output_file = 'companies_cleaned.csv'
    backup_file = f'companies_backup_{int(__import__("time").time())}.csv'
    
    # Check if files exist
    if not os.path.exists(csv_file):
        print(f"❌ Error: {csv_file} not found!")
        return
    
    if not os.path.exists(failed_companies_file):
        print(f"❌ Error: {failed_companies_file} not found!")
        return
    
    # Create a backup of the original file
    print(f"📋 Creating backup: {backup_file}")
    with open(csv_file, 'r', encoding='utf-8') as src, open(backup_file, 'w', encoding='utf-8') as dst:
        dst.write(src.read())
    
    # Clean the CSV
    print("🧹 Cleaning companies.csv based on failed_companies.txt...")
    kept, removed = clean_companies_csv_from_file(csv_file, failed_companies_file, output_file)
    
    # Replace the original file with the cleaned version
    if os.path.exists(output_file):
        os.replace(output_file, csv_file)
        print(f"\n✅ Original companies.csv has been updated")
        print(f"📋 Backup saved as: {backup_file}")
        
        # Final verification
        print(f"\n🔍 Final verification:")
        with open(csv_file, 'r', encoding='utf-8') as file:
            final_count = len(file.readlines()) - 1  # Subtract header
            print(f"Final company count: {final_count}")

if __name__ == "__main__":
    main()
