<#
  Garmin Lifetime Analyzer without Docker (Windows).

  .\start.ps1            set up what is missing, then start the app and the daily sync
  .\start.ps1 -Update    get the newest version first (git pull), then start
  .\start.ps1 -NoSync    start the app without the daily sync
  .\start.ps1 -Port 8010 use another port

  The first run creates a Python environment in .venv and builds the web page; later runs start in seconds.
  Settings come from .env in this folder, as with Docker. Data lives in the data folder here.
  If Windows refuses to run this script, use start.cmd instead (double-click it).
#>
param([switch]$Update, [switch]$NoSync, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail($text) { Write-Host $text -ForegroundColor Red; exit 1 }
function Step($text) { Write-Host "== $text" -ForegroundColor Cyan }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Run($exe, [string[]]$argList) { & $exe @argList; if ($LASTEXITCODE -ne 0) { Fail "Failed: $exe $($argList -join ' ')" } }

if ($Update) {
    if (-not (Has git)) { Fail "Git not found. Install it from git-scm.com." }
    Step "Getting the newest version"
    Run git @("pull")
}

# 1. Python environment
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Step "Creating the Python environment (.venv)"
    if (Has py) { Run py @("-3", "-m", "venv", ".venv") }
    elseif (Has python) { Run python @("-m", "venv", ".venv") }
    else { Fail "Python not found. Install Python 3.12 or newer from python.org and tick 'Add python.exe to PATH'." }
}
& $py -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { Fail "Python 3.12 or newer is needed. Install it, delete the .venv folder, and run this again." }

$stamp = Join-Path $PSScriptRoot ".venv\.gla-installed"
$pyproject = Join-Path $PSScriptRoot "backend\pyproject.toml"
if ($Update -or -not (Test-Path $stamp) -or (Get-Item $pyproject).LastWriteTime -gt (Get-Item $stamp).LastWriteTime) {
    Step "Installing the app into .venv"
    Run $py @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
    Run $py @("-m", "pip", "install", "--quiet", "-e", ".\backend")
    New-Item $stamp -ItemType File -Force | Out-Null
}

# 2. The web page
if ($Update -or -not (Test-Path "frontend\dist\index.html")) {
    if (-not (Has npm)) { Fail "Node.js not found. Install Node.js 20 or newer from nodejs.org (needed once, to build the web page)." }
    Step "Building the web page"
    Push-Location frontend
    try { Run npm @("install", "--no-audit", "--no-fund"); Run npm @("run", "build") } finally { Pop-Location }
}

if (-not (Test-Path ".env")) { Write-Host "No .env file yet: copy .env.example to .env and fill in your Garmin key for the daily sync." -ForegroundColor Yellow }
$gla = Join-Path $PSScriptRoot ".venv\Scripts\gla.exe"
if ($Update) { Step "Analyzing with the new version"; Run $gla @("analyze", "--full") }

# 3. Start: the daily sync in a small window of its own, the app here
$worker = $null
if (-not $NoSync) {
    $worker = Start-Process -FilePath $gla -ArgumentList "worker" -WorkingDirectory $PSScriptRoot -WindowStyle Minimized -PassThru
    Write-Host "Daily sync running (minimized window, closes with the app)." -ForegroundColor DarkGray
}
try {
    & $gla serve --port $Port
} finally {
    if ($worker -and -not $worker.HasExited) { Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue }
}
