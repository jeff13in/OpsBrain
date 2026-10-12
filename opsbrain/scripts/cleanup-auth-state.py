"""Explicit maintenance; print counts/credentials neither here nor in logs."""

import sys
import time

import psycopg

from orchestrator.auth.flows import PostgresAuthStore
from orchestrator.auth.settings import AuthSettings

if __name__ == '__main__':
    try:
        settings = AuthSettings()
        settings.validate_setup()
        PostgresAuthStore(settings.supabase_session_database_url.get_secret_value()).cleanup(int(time.time()))
    except (ValueError, psycopg.Error):
        print('Auth cleanup unavailable; check private configuration and database access', file=sys.stderr)
        sys.exit(1)
    print('Expired auth state cleanup completed; saved client work unchanged')
