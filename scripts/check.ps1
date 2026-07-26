# Local v1 gate for 4designer (no CI wiring).
# Usage from repository root: pwsh scripts/check.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VersionFile = Join-Path $Root "VERSION"
$Expected = (Get-Content $VersionFile -Raw).Trim().Split("`n")[0].Trim()

Write-Host "== 4designer check (VERSION=$Expected) =="

function Assert-Version([string]$label, [string]$got) {
  if ($got -ne $Expected) {
    throw "VERSION mismatch: $label is '$got', expected '$Expected'"
  }
  Write-Host "  ok $label = $got"
}

# --- Version consistency ---
$daemonPy = Join-Path $Root "daemon\.venv\Scripts\python.exe"
if (-not (Test-Path $daemonPy)) {
  $daemonPy = "python"
}
Push-Location (Join-Path $Root "daemon")
try {
  $gotDaemon = & $daemonPy -c "from fourdesigner_daemon import __version__; print(__version__)"
  Assert-Version "daemon" $gotDaemon.Trim()
} finally {
  Pop-Location
}

$pkg = Get-Content (Join-Path $Root "frontend\package.json") -Raw | ConvertFrom-Json
Assert-Version "frontend/package.json" $pkg.version

# --- Python unit tests ---
Write-Host "== unittest discover =="
Push-Location (Join-Path $Root "daemon")
try {
  & $daemonPy -m unittest discover -s . -p "test_*.py" -q
  if ($LASTEXITCODE -ne 0) { throw "unittest failed ($LASTEXITCODE)" }
} finally {
  Pop-Location
}

# --- SHM parity ---
Write-Host "== shm parity =="
Push-Location (Join-Path $Root "shm")
try {
  & $daemonPy -m unittest discover -s tests -p "test_*.py" -q
  if ($LASTEXITCODE -ne 0) { throw "shm parity failed ($LASTEXITCODE)" }
} finally {
  Pop-Location
}

# --- Frontend typecheck + e2e ---
Write-Host "== frontend typecheck =="
Push-Location (Join-Path $Root "frontend")
try {
  npm run typecheck
  if ($LASTEXITCODE -ne 0) { throw "typecheck failed ($LASTEXITCODE)" }
  Write-Host "== frontend e2e =="
  npm run test:e2e
  if ($LASTEXITCODE -ne 0) { throw "e2e failed ($LASTEXITCODE)" }
} finally {
  Pop-Location
}

Write-Host "== ALL OK (4designer v$Expected) =="
