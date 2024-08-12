#!/usr/bin/env python3
"""
Script to remove failed companies from companies.csv based on the test results
"""

import csv
import os
from typing import List

def get_failed_companies() -> List[str]:
    """Get the list of failed companies from our test results"""
    failed_companies = [
        "Cruise Automation",
        "Deliveroo", 
        "Watershed",
        "Luna",
        "Bynder",
        "Punchh",
        "Sentry",
        "Snyk",
        "Outlier",
        "Mux",
        "Teach for America",
        "KIPP Foundation",
        "Success Academy",
        "BetterLesson",
        "Brooke Charter Schools",
        "New Teacher Center",
        "Jobs for the Future",
        "Macy's",
        "Buck Mason",
        "Cotopaxi",
        "Gong",
        "DocuSign",
        "Booking.com",
        "Away",
        "Klarna",
        "Plaid",
        "Teladoc Health",
        "Moderna",
        "Illumina",
        "Legend Biotech"
    ]
    return failed_companies

def clean_companies_csv(input_file: str, output_file: str):
    """Remove failed companies from the CSV file"""
    
    failed_companies = get_failed_companies()
    failed_companies_set = set(failed_companies)
    
    kept_companies = []
    removed_companies = []
    
    # Read the original file
    with open(input_file, 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        
        for row in csv_reader:
            company_name = row['Company Name']
            
            if company_name in failed_companies_set:
                removed_companies.append(company_name)
                print(f"❌ Removing: {company_name}")
            else:
                kept_companies.append(row)
                print(f"✅ Keeping: {company_name}")
    
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
            print(f"Failed companies not found in CSV: {list(not_found)}")
    
    print(f"\n✅ Cleaned CSV saved as: {output_file}")
    
    return len(kept_companies), len(removed_companies)

def main():
    input_file = 'companies.csv'
    output_file = 'companies_cleaned.csv'
    backup_file = 'companies_backup.csv'
    
    # Create a backup of the original file
    if os.path.exists(input_file):
        print(f"📋 Creating backup: {backup_file}")
        with open(input_file, 'r', encoding='utf-8') as src, open(backup_file, 'w', encoding='utf-8') as dst:
            dst.write(src.read())
    
    # Clean the CSV
    print("🧹 Cleaning companies.csv...")
    kept, removed = clean_companies_csv(input_file, output_file)
    
    # Replace the original file with the cleaned version
    if os.path.exists(output_file):
        os.replace(output_file, input_file)
        print(f"✅ Original companies.csv has been updated")
        print(f"📋 Backup saved as: {backup_file}")

if __name__ == "__main__":
    main()
