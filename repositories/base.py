"""
Base repository untuk dependency injection Supabase client.
"""

from typing import Any

from clients.supabase import supabase as default_supabase


class BaseRepository:
    """Base class repository dengan Supabase client yang bisa di-inject."""

    def __init__(self, supabase_client: Any = None):
        self._supabase = supabase_client or default_supabase
