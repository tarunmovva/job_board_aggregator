"""Supabase database client for job board aggregator."""

import os
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError("supabase package not installed. Run: pip install supabase")

from job_board_aggregator.config import logger


class SupabaseClient:
    """Handles all database operations for companies and system configuration."""
    
    def __init__(self):
        """Initialize Supabase client with environment variables."""
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables must be set. "
                "Please check your .env file."
            )
        
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            # Simple query to test connection
            result = self.client.table('system_config').select('id').limit(1).execute()
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    # Company Management Methods (replaces CSV operations)
    
    def get_all_companies(self, limit: Optional[int] = None, active_only: bool = True) -> List[Tuple[str, str]]:
        """
        Get all companies from database (replaces _read_csv_file function).
        
        Args:
            limit: Maximum number of companies to return
            active_only: If True, only return active companies
            
        Returns:
            List of (company_name, api_url) tuples
        """
        try:
            query = self.client.table('companies').select('name, api_url')
            
            if active_only:
                query = query.eq('is_active', True)
            
            if limit:
                query = query.limit(limit)
            
            result = query.execute()
            
            # Convert to list of tuples to match existing CSV format
            companies = [(row['name'], row['api_url']) for row in result.data]
            logger.info(f"Retrieved {len(companies)} companies from database")
            return companies
            
        except Exception as e:
            logger.error(f"Error retrieving companies from database: {e}")
            return []
    
    def get_company_by_name(self, name: str) -> Optional[Dict]:
        """Get single company details by name."""
        try:
            result = self.client.table('companies').select('*').eq('name', name).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving company {name}: {e}")
            return None
    
    def add_company(self, name: str, api_url: str, is_active: bool = True) -> bool:
        """Add new company to database."""
        try:
            data = {
                'name': name,
                'api_url': api_url,
                'is_active': is_active
            }
            
            result = self.client.table('companies').insert(data).execute()
            
            if result.data:
                logger.info(f"Successfully added company: {name}")
                return True
            else:
                logger.error(f"Failed to add company: {name}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding company {name}: {e}")
            return False
    
    def update_company_status(self, name: str, is_active: bool) -> bool:
        """Enable/disable company."""
        try:
            result = self.client.table('companies').update({
                'is_active': is_active
            }).eq('name', name).execute()
            
            if result.data:
                status = "activated" if is_active else "deactivated"
                logger.info(f"Successfully {status} company: {name}")
                return True
            else:
                logger.warning(f"Company not found: {name}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating company {name} status: {e}")
            return False
    
    # Timestamp Management Methods (replaces last_fetch.json operations)
    
    def get_last_fetch_time(self, company_name: str) -> Optional[str]:
        """
        Get the last fetch time for a specific company (replaces timestamp.py function).
        
        Args:
            company_name: Name of the company
            
        Returns:
            ISO format datetime string or None if no previous fetch
        """
        try:
            result = self.client.table('companies').select('last_fetch_time').eq('name', company_name).execute()
            
            if result.data and result.data[0]['last_fetch_time']:
                return result.data[0]['last_fetch_time']
            else:
                # If no company-specific timestamp, return default start date
                return self.get_default_start_date()
                
        except Exception as e:
            logger.error(f"Error getting last fetch time for {company_name}: {e}")
            return None
    
    def update_fetch_time(self, company_name: str, timestamp: Optional[str] = None) -> bool:
        """
        Update the last fetch time for a company (replaces timestamp.py function).
        
        Args:
            company_name: Name of the company
            timestamp: ISO format timestamp (uses current time if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if timestamp is None:
                timestamp = datetime.now(timezone.utc).isoformat()
            
            result = self.client.table('companies').update({
                'last_fetch_time': timestamp
            }).eq('name', company_name).execute()
            
            if result.data:
                logger.info(f"Updated fetch time for {company_name}: {timestamp}")
                return True
            else:
                logger.warning(f"Company not found when updating fetch time: {company_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating fetch time for {company_name}: {e}")
            return False
    
    def get_default_start_date(self) -> Optional[str]:
        """Get default start date from system_config table."""
        try:
            result = self.client.table('system_config').select('config_value').eq('config_key', 'default_start_date').execute()
            
            if result.data:
                return result.data[0]['config_value']
            return None
            
        except Exception as e:
            logger.error(f"Error getting default start date: {e}")
            return None
    
    def set_default_start_date(self, date: str) -> bool:
        """Update default start date in system_config table."""
        try:
            # Use upsert to insert or update
            result = self.client.table('system_config').upsert({
                'config_key': 'default_start_date',
                'config_value': date,
                'description': 'Default start date for fetching jobs when no company-specific timestamp exists'
            }).execute()
            
            if result.data:
                logger.info(f"Updated default start date: {date}")
                return True
            else:
                logger.error("Failed to update default start date")
                return False
                
        except Exception as e:
            logger.error(f"Error setting default start date: {e}")
            return False
    
    # Batch Operations for Performance
    
    def batch_update_fetch_times(self, updates: Dict[str, str]) -> bool:
        """
        Update multiple company fetch times in one transaction.
        
        Args:
            updates: Dictionary of company_name -> timestamp
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Build batch update data
            update_data = []
            for company_name, timestamp in updates.items():
                update_data.append({
                    'name': company_name,
                    'last_fetch_time': timestamp
                })
            
            # Perform batch upsert
            result = self.client.table('companies').upsert(update_data).execute()
            
            if result.data:
                logger.info(f"Batch updated fetch times for {len(updates)} companies")
                return True
            else:
                logger.error("Failed to batch update fetch times")
                return False
                
        except Exception as e:
            logger.error(f"Error in batch update fetch times: {e}")
            return False
    
    def get_companies_needing_fetch(self, hours_since_last: int = 24) -> List[Dict]:
        """
        Get companies that haven't been fetched recently.
        
        Args:
            hours_since_last: Hours since last fetch to consider "needing fetch"
            
        Returns:
            List of company dictionaries
        """
        try:
            # Calculate cutoff time
            cutoff_time = datetime.now(timezone.utc).replace(
                hour=datetime.now(timezone.utc).hour - hours_since_last
            ).isoformat()
            
            result = self.client.table('companies').select('*').or_(
                f'last_fetch_time.is.null,last_fetch_time.lt.{cutoff_time}'
            ).eq('is_active', True).execute()
            
            logger.info(f"Found {len(result.data)} companies needing fetch")
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting companies needing fetch: {e}")
            return []
    
    # Analytics and Utility Methods
    
    def get_company_count(self, active_only: bool = True) -> int:
        """Get total number of companies."""
        try:
            query = self.client.table('companies').select('id', count='exact')
            
            if active_only:
                query = query.eq('is_active', True)
            
            result = query.execute()
            return result.count or 0
            
        except Exception as e:
            logger.error(f"Error getting company count: {e}")
            return 0
    
    def get_fetch_statistics(self) -> Dict:
        """Get statistics about fetch times."""
        try:
            # Get companies with recent fetches (last 24 hours)
            recent_cutoff = datetime.now(timezone.utc).replace(
                hour=datetime.now(timezone.utc).hour - 24
            ).isoformat()
            
            recent_result = self.client.table('companies').select('id', count='exact').gte(
                'last_fetch_time', recent_cutoff
            ).execute()
            
            # Get total active companies
            total_result = self.client.table('companies').select('id', count='exact').eq(
                'is_active', True
            ).execute()
            
            # Get companies never fetched
            never_fetched_result = self.client.table('companies').select('id', count='exact').is_(
                'last_fetch_time', 'null'
            ).eq('is_active', True).execute()
            
            return {
                'total_active_companies': total_result.count or 0,
                'fetched_last_24h': recent_result.count or 0,
                'never_fetched': never_fetched_result.count or 0
            }
            
        except Exception as e:
            logger.error(f"Error getting fetch statistics: {e}")
            return {
                'total_active_companies': 0,
                'fetched_last_24h': 0,
                'never_fetched': 0
            }


# Global instance (will be initialized when first imported)
_supabase_client = None

def get_supabase_client() -> SupabaseClient:
    """Get global Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client
