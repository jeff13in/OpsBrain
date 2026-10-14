param([string]$EnvFile = (Join-Path $PSScriptRoot '../.env'))
$ErrorActionPreference = 'Stop'

# Read only the public provider configuration; never display credential values.
$settings = @{}
foreach ($line in [IO.File]::ReadAllLines((Resolve-Path -LiteralPath $EnvFile).Path)) {
    if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=(.*)$') {
        $settings[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
    }
}
foreach ($name in @('SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY')) {
    $processValue = [Environment]::GetEnvironmentVariable($name)
    if ($processValue) { $settings[$name] = $processValue }
    if (-not $settings[$name]) { throw "Missing $name." }
}
$origin = $null
if (-not [Uri]::TryCreate($settings['SUPABASE_URL'], [UriKind]::Absolute, [ref]$origin) -or
    $origin.Scheme -ne 'https' -or $origin.Host -notmatch '^[a-z0-9]+\.supabase\.co$' -or
    $origin.UserInfo -or $origin.Query -or $origin.Fragment -or $origin.AbsolutePath -ne '/' -or
    -not $origin.IsDefaultPort) {
    throw 'SUPABASE_URL must be a hosted Supabase HTTPS origin.'
}
if ($settings['SUPABASE_PUBLISHABLE_KEY'] -notmatch '^sb_publishable_[A-Za-z0-9_-]+$') {
    throw 'SUPABASE_PUBLISHABLE_KEY must be a publishable key.'
}
try {
    $response = Invoke-WebRequest -Uri ($origin.AbsoluteUri.TrimEnd('/') + '/auth/v1/settings') -Headers @{
        apikey = $settings['SUPABASE_PUBLISHABLE_KEY']
    } -TimeoutSec 15 -MaximumRedirection 0 -UseBasicParsing
    $provider = $response.Content | ConvertFrom-Json
    if ($response.StatusCode -ne 200 -or $null -eq $provider.external.email) { throw 'Invalid settings response.' }
} catch {
    Write-Output 'Supabase connection failed. Check project availability, publishable key and network access. Provider details withheld.'
    exit 1
}
Write-Output 'Supabase Auth connection passed (HTTP 200).'
Write-Output ('Email authentication enabled: ' + $provider.external.email)
Write-Output ('Email confirmation required: ' + (-not $provider.mailer_autoconfirm))
$missing = @()
foreach ($name in @('APP_ENV', 'APP_ORIGIN', 'SESSION_ENCRYPTION_KEY', 'SUPABASE_SESSION_DATABASE_URL')) {
    if (-not [Environment]::GetEnvironmentVariable($name) -and -not $settings[$name]) { $missing += $name }
}
if ($missing.Count) {
    Write-Output ('Account runtime still needs: ' + ($missing -join ', '))
}
Write-Output 'This read-only check does not apply migrations or verify account login, workspace persistence or hosted acceptance.'
