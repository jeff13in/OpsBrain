"""Optional auth configuration; incomplete settings fail closed."""

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    app_env: str = 'production'
    app_origin: str = ''
    beta_signup_enabled: bool = False
    supabase_url: str = ''
    supabase_publishable_key: SecretStr = SecretStr('')
    session_encryption_key: SecretStr = SecretStr('')
    supabase_session_database_url: SecretStr = SecretStr('')
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @property
    def secure_cookie(self):
        return self.app_env != 'development'

    @property
    def cookie_name(self):
        return '__Host-opsbrain_session' if self.secure_cookie else 'opsbrain_session_dev'

    def validate_setup(self):
        if self.app_env not in ('development', 'staging', 'production'):
            raise ValueError('Invalid auth environment')
        for value in (self.app_origin, self.supabase_url):
            url = urlsplit(value)
            _ = url.port  # Reject malformed ports without exposing the input.
            if (not url.hostname or url.username is not None or url.password is not None
                or url.query or url.fragment or url.path not in ('', '/')
                or any(char.isspace() for char in value) or '\\' in value):
                raise ValueError('Invalid auth origin')
            if url.scheme != 'https' and not (
                not self.secure_cookie and url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')
            ):
                raise ValueError('Auth requires HTTPS outside loopback development')
        if not self.supabase_publishable_key.get_secret_value().startswith('sb_publishable_'):
            raise ValueError('Publishable key required')
        if not self.session_encryption_key.get_secret_value() or not self.supabase_session_database_url.get_secret_value():
            raise ValueError('Private session configuration required')
        import psycopg.conninfo

        info = psycopg.conninfo.conninfo_to_dict(self.supabase_session_database_url.get_secret_value())
        if self.secure_cookie and info.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
            raise ValueError('Session database TLS required')


@lru_cache(maxsize=1)
def configured_boundary():
    from orchestrator.auth.provider import SupabaseProvider
    from orchestrator.auth.sessions import PostgresSessionStore, SessionManager

    settings = AuthSettings()
    settings.validate_setup()
    manager = SessionManager(
        PostgresSessionStore(settings.supabase_session_database_url.get_secret_value()),
        SupabaseProvider(settings.supabase_url, settings.supabase_publishable_key.get_secret_value()),
        settings.session_encryption_key.get_secret_value(),
    )
    return settings, manager
