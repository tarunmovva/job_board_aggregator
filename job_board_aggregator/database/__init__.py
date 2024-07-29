"""Database package for job board aggregator."""

from .supabase_client import SupabaseClient, get_supabase_client

__all__ = ['SupabaseClient', 'get_supabase_client']
