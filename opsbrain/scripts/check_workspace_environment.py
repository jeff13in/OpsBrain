"""Offline OPU-93 environment preflight; never prints configuration values.

This does not contact Supabase, validate credentials, or certify deployment.
Run with environment variables supplied by the deployment's secret manager.
"""

import os
import sys
from urllib.parse import urlsplit


def origin_is_valid(value, local_allowed=False):
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return False
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return False
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            return False
        if any(char.isspace() for char in value) or "\\" in value:
            return False
        loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        return (parsed.scheme == "https" and (local_allowed or not loopback)) or (
            local_allowed and loopback and parsed.scheme == "http"
        )
    except ValueError:
        return False


def check_environment(env):
    """Return safe diagnostics containing variable names, never their values."""
    errors = []
    stage = env.get("APP_ENV", "")
    if stage not in ("development", "staging", "production"):
        errors.append("APP_ENV must be development, staging or production")
    local_allowed = stage == "development"
    for name in ("APP_ORIGIN", "SUPABASE_URL"):
        if not origin_is_valid(env.get(name, ""), local_allowed):
            errors.append(name + " must be an HTTPS origin; development permits loopback HTTP")
    # New projects use current Supabase keys; legacy JWT keys need explicit migration.
    key = env.get("SUPABASE_PUBLISHABLE_KEY", "")
    if not key.startswith("sb_publishable_") or len(key) <= len("sb_publishable_"):
        errors.append("SUPABASE_PUBLISHABLE_KEY requires a publishable key, never an administrative key")
    return errors


def main():
    errors = check_environment(os.environ)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Environment shape passed. Provider access, sessions, SMTP, migrations and RLS remain unverified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
