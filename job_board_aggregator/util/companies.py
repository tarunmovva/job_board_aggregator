"""Database utilities for company operations - Supabase only."""

from typing import List, Tuple

from job_board_aggregator.config import logger


def read_companies_data(limit: int = None) -> List[Tuple[str, str]]:
    """
    Read companies from Supabase database.
    
    Args:
        limit: Maximum number of companies to return
        
    Returns:
        List of (company_name, api_url) tuples
        
    Raises:
        Exception: If database is not available or accessible
    """
    try:
        from job_board_aggregator.database import get_supabase_client
        db_client = get_supabase_client()
        
        companies = db_client.get_all_companies(limit=limit, active_only=True)
        logger.info(f"Read {len(companies)} companies from Supabase database")
        return companies
        
    except ImportError as e:
        logger.error("Supabase client not available")
        raise Exception("Supabase database client is not available. Please ensure the database module is properly installed.")
    except Exception as e:
        logger.error(f"Error reading companies from database: {e}")
        raise Exception(f"Failed to read companies from Supabase database: {e}")


def get_company_api_url(company_name: str) -> str:
    """
    Get the API URL for a specific company from Supabase database.
    
    Args:
        company_name: Name of the company
        
    Returns:
        API URL for the company
        
    Raises:
        Exception: If company not found or database error
    """
    try:
        from job_board_aggregator.database import get_supabase_client
        db_client = get_supabase_client()
        
        company_data = db_client.get_company_by_name(company_name)
        if not company_data:
            raise Exception(f"Company '{company_name}' not found in database")
            
        return company_data['api_url']
        
    except ImportError:
        raise Exception("Supabase database client is not available")
    except Exception as e:
        logger.error(f"Error getting API URL for {company_name}: {e}")
        raise


def add_company(company_name: str, api_url: str) -> bool:
    """
    Add a new company to the Supabase database.
    
    Args:
        company_name: Name of the company
        api_url: API URL for the company
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from job_board_aggregator.database import get_supabase_client
        db_client = get_supabase_client()
        
        return db_client.add_company(company_name, api_url)
        
    except ImportError:
        logger.error("Supabase client not available")
        return False
    except Exception as e:
        logger.error(f"Database error adding company {company_name}: {e}")
        return False


def update_company_status(company_name: str, is_active: bool) -> bool:
    """
    Update company active status in Supabase database.
    
    Args:
        company_name: Name of the company
        is_active: Whether the company should be active
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from job_board_aggregator.database import get_supabase_client
        db_client = get_supabase_client()
        
        return db_client.update_company_status(company_name, is_active)
        
    except ImportError:
        logger.error("Supabase client not available")
        return False
    except Exception as e:
        logger.error(f"Database error updating status for {company_name}: {e}")
        return False


def get_database_stats() -> dict:
    """
    Get statistics about the Supabase database.
    
    Returns:
        Dictionary with statistics
    """
    try:
        from job_board_aggregator.database import get_supabase_client
        db_client = get_supabase_client()
        
        company_count = db_client.get_company_count()
        fetch_stats = db_client.get_fetch_statistics()
        
        return {
            'data_source': 'supabase_database',
            'total_companies': company_count,
            **fetch_stats
        }
        
    except ImportError:
        logger.error("Supabase client not available")
        return {
            'data_source': 'error',
            'total_companies': 0,
            'fetched_last_24h': 0,
            'never_fetched': 0,
            'error': 'Supabase client not available'
        }
    except Exception as e:
        logger.error(f"Database error getting stats: {e}")
        return {
            'data_source': 'error',
            'total_companies': 0,
            'fetched_last_24h': 0,
            'never_fetched': 0,
            'error': str(e)
        }
