# Local Supabase connection

The Python account backend reads `SUPABASE_URL` and
`SUPABASE_PUBLISHABLE_KEY` from `opsbrain/.env` through `AuthSettings`.
The `NEXT_PUBLIC_` equivalents are also saved for the user's requested
configuration; the current frontend is static JavaScript, not Next.js.
Its account requests use the same-origin Python API, so those public aliases
alone do not enable browser login.

From `opsbrain/`, verify the configured project's Auth endpoint:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-supabase-connection.ps1
```

The script reads the ignored `.env` and honors process overrides. It sends
only the publishable key to the fixed hosted project's Auth settings endpoint,
rejects redirects and prints no key or provider error body. No accounts,
migrations, provider settings or database records are changed.

On October 13, 2026, the configured project returned HTTP 200, email Auth
was enabled and email confirmation was required. Hosted/admin setup is
skipped at the user's request. Account login and workspace persistence still
require `APP_ENV`, `APP_ORIGIN`, `SESSION_ENCRYPTION_KEY` and the dedicated
`SUPABASE_SESSION_DATABASE_URL`, plus the existing migration/approval setup.
See [account setup](account-authentication.md). Do not substitute an in-memory
session store or expose provider tokens to bypass these requirements.
