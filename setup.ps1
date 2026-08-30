# ==============================================================================
#  PhantomStrike - Automatic Setup for Windows
#
#  Installs everything and writes a start script so you never have to remember
#  the steps again.
#
#      irm https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/setup.ps1 | iex
#
#  Or, from a clone:  .\setup.ps1
#
#  Safe to re-run. It skips work that is already done rather than reinstalling,
#  so if a step fails you can fix the cause and run it again.
#
#  If PowerShell blocks this script, allow local scripts for this session:
#      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# ==============================================================================

$ErrorActionPreference = 'Stop'

# -- Appearance ----------------------------------------------------------------

function Write-Step { param($m) Write-Host "`n> $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "  [ok] $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host "  ,  $m" -ForegroundColor Gray }
function Write-Warn { param($m) Write-Host "  [!] $m" -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host "  [x] $m" -ForegroundColor Red; exit 1 }

function Show-Banner {
    Write-Host ""
    Write-Host "  +---------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host "  |                                             |" -ForegroundColor DarkCyan
    Write-Host "  |        P H A N T O M S T R I K E            |" -ForegroundColor Cyan
    Write-Host "  |                                             |" -ForegroundColor DarkCyan
    Write-Host "  |   Kali security tools, driven by AI         |" -ForegroundColor Gray
    Write-Host "  |                                             |" -ForegroundColor DarkCyan
    Write-Host "  +---------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host ""
}

# -- Environment ---------------------------------------------------------------

$script:HasWsl    = $false
$script:HasDocker = $false

function Test-Environment {
    Write-Step "Checking your system"
    Write-Ok "Windows $([System.Environment]::OSVersion.Version)"

    if (Get-Command wsl -ErrorAction SilentlyContinue) {
        $script:HasWsl = $true
        Write-Ok "WSL is available"
    } else {
        Write-Info "WSL not found (optional - needed to run tools locally in Kali)"
    }

    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $script:HasDocker = $true
        Write-Ok "Docker is available"
    } else {
        Write-Info "Docker not found (optional - an alternative to WSL)"
    }

    # On Windows the security tools themselves live in WSL, a VM, or a container.
    # This script sets up the client side: the MCP client and the proxy daemon.
    if (-not $script:HasWsl -and -not $script:HasDocker) {
        Write-Warn "Neither WSL nor Docker found."
        Write-Info "PhantomStrike needs somewhere to run Linux tools. Install one:"
        Write-Info "  WSL2   : wsl --install -d kali-linux"
        Write-Info "  Docker : https://www.docker.com/products/docker-desktop"
        Write-Info "Setup will continue and configure the Windows side regardless."
    }
}

function Test-Python {
    Write-Step "Checking Python"

    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $py) {
        Write-Fail "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and tick 'Add Python to PATH'."
    }

    $version = & $py.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $parts = $version.Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
        Write-Fail "Python 3.10+ required, found $version."
    }
    Write-Ok "Python $version"
    return $py.Source
}

# -- Install -------------------------------------------------------------------

function Install-PhantomStrike {
    param($PythonExe)
    Write-Step "Installing PhantomStrike"

    # Running inside a clone? Use it. Otherwise clone to a known location.
    if ((Test-Path './pyproject.toml') -and (Select-String -Path './pyproject.toml' -Pattern 'name = "phantomstrike"' -Quiet)) {
        $installDir = (Get-Location).Path
        Write-Ok "Using this clone: $installDir"
    } else {
        $installDir = Join-Path $env:USERPROFILE 'phantomstrike'
        if (Test-Path (Join-Path $installDir '.git')) {
            Write-Info "Updating existing install at $installDir..."
            git -C $installDir pull --quiet
        } else {
            if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
                Write-Fail "git not found. Install it from https://git-scm.com/download/win and run this again."
            }
            Write-Info "Cloning to $installDir..."
            git clone --quiet --depth=1 https://github.com/Red-Snow/phantomstrike.git $installDir
        }
        Write-Ok "Repository ready"
    }

    Set-Location $installDir

    if (-not (Test-Path '.venv')) {
        Write-Info "Creating virtual environment..."
        & $PythonExe -m venv .venv
    }

    Write-Info "Installing Python package..."
    & '.\.venv\Scripts\python.exe' -m pip install --quiet --upgrade pip
    & '.\.venv\Scripts\python.exe' -m pip install --quiet -e .
    if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed. Scroll up for the reason." }
    Write-Ok "PhantomStrike installed"

    return $installDir
}

# -- API key -------------------------------------------------------------------

function Set-ApiKey {
    Write-Step "Setting up your API key"

    if ((Test-Path '.env') -and (Select-String -Path '.env' -Pattern '^PHANTOMSTRIKE_API_KEYS=' -Quiet)) {
        $line = Select-String -Path '.env' -Pattern '^PHANTOMSTRIKE_API_KEYS=' | Select-Object -First 1
        $key = $line.Line.Split('=', 2)[1].Trim('"')
        Write-Ok "Existing key found in .env - keeping it"
        return $key
    }

    $key = & '.\.venv\Scripts\python.exe' -c "import secrets; print(secrets.token_urlsafe(32))"

    # .env is gitignored; the key must never reach the repository.
    @(
        "# PhantomStrike configuration - generated by setup.ps1",
        "# This file contains a secret. Do not commit it.",
        "PHANTOMSTRIKE_API_KEYS=$key",
        "PHANTOMSTRIKE_ENFORCE_SCOPE=true",
        "PHANTOMSTRIKE_ALLOW_RAW_SHELL=false"
    ) | Add-Content -Path '.env' -Encoding utf8

    Write-Ok "Key generated and saved to .env"
    Write-Info "The server refuses to start without this key. Setup handles it for you."
    return $key
}

# -- Start script --------------------------------------------------------------
#
# The point of this: after a reboot, novice users were reinstalling from scratch
# because they had no record of how to start things again. Now there is one file.

function Write-StartScript {
    Write-Step "Creating your start script"

    $content = @'
# ==============================================================================
#  Start PhantomStrike
#
#  Run this after a reboot. You do NOT need to reinstall anything.
#
#      .\start.ps1                 start the proxy daemon (Claude Desktop)
#      .\start.ps1 -Mode server    start the API server on this machine
#      .\start.ps1 -Mode status    check what is already running
# ==============================================================================
param(
    [ValidateSet('proxy','server','status')]
    [string]$Mode = 'proxy',
    [string]$Remote = 'http://localhost:8443'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv')) {
    Write-Host "No .venv found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Load .env into the process environment
if (Test-Path '.env') {
    Get-Content '.env' | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim('"'), 'Process')
        }
    }
} else {
    Write-Host "No .env found - the server needs PHANTOMSTRIKE_API_KEYS. Run .\setup.ps1" -ForegroundColor Yellow
}

switch ($Mode) {
    'server' {
        Write-Host "Starting PhantomStrike API server" -ForegroundColor Cyan
        Write-Host "  Listening on : http://0.0.0.0:8443"
        Write-Host "  API docs     : http://localhost:8443/docs"
        Write-Host "  Stop with    : Ctrl+C"
        Write-Host ""
        Write-Host "  Keep this window open while you work." -ForegroundColor Yellow
        Write-Host ""
        & '.\.venv\Scripts\phantomstrike.exe' --host 0.0.0.0 --port 8443
    }
    'proxy' {
        $env:PHANTOMSTRIKE_API_KEY = $env:PHANTOMSTRIKE_API_KEYS
        Write-Host "Starting PhantomStrike proxy daemon" -ForegroundColor Cyan
        Write-Host "  Forwarding to : $Remote"
        Write-Host "  Stop with     : Ctrl+C"
        Write-Host ""
        Write-Host "  Keep this window open while you work." -ForegroundColor Yellow
        Write-Host ""
        & '.\.venv\Scripts\python.exe' proxy_daemon.py --remote $Remote
    }
    'status' {
        Write-Host "PhantomStrike status"
        try {
            Invoke-RestMethod -Uri 'http://localhost:8443/health' -TimeoutSec 3 | Out-Null
            Write-Host "  [ok] API server is reachable" -ForegroundColor Green
        } catch {
            Write-Host "  [ ]  API server not reachable  -> .\start.ps1 -Mode server" -ForegroundColor Yellow
        }
        $proxy = Get-Process python -ErrorAction SilentlyContinue |
                 Where-Object { $_.CommandLine -like '*proxy_daemon*' }
        if ($proxy) {
            Write-Host "  [ok] Proxy daemon is running" -ForegroundColor Green
        } else {
            Write-Host "  [ ]  Proxy daemon not running  -> .\start.ps1" -ForegroundColor Yellow
        }
    }
}
'@

    Set-Content -Path 'start.ps1' -Value $content -Encoding utf8
    Write-Ok "Created start.ps1"
}

# -- Claude Desktop ------------------------------------------------------------

function Set-AgentConfig {
    param($InstallDir)
    Write-Step "Configuring your AI agent"

    $mcpBin = Join-Path $InstallDir '.venv\Scripts\phantomstrike-mcp.exe'
    $configDir = Join-Path $env:APPDATA 'Claude'
    $configPath = Join-Path $configDir 'claude_desktop_config.json'

    # Only touch agents that are actually installed.
    if (-not (Test-Path $configDir)) {
        Write-Warn "Claude Desktop not found on this machine."
        Write-Info "Install it, then add this to claude_desktop_config.json:"
        Write-Host "    {`"mcpServers`":{`"phantomstrike`":{`"command`":`"$mcpBin`",`"args`":[`"--mode`",`"remote`"]}}}" -ForegroundColor DarkGray
        return
    }

    if (Test-Path $configPath) {
        if (Select-String -Path $configPath -Pattern 'phantomstrike' -Quiet) {
            Write-Ok "Claude Desktop already configured"
            return
        }
        Copy-Item $configPath "$configPath.backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Warn "claude_desktop_config.json exists and has other servers in it."
        Write-Info "Backed it up. Add this entry to `"mcpServers`" yourself:"
        Write-Host "    `"phantomstrike`": {`"command`": `"$mcpBin`", `"args`": [`"--mode`", `"remote`"]}" -ForegroundColor DarkGray
        return
    }

    $config = @{ mcpServers = @{ phantomstrike = @{ command = $mcpBin; args = @('--mode','remote') } } }
    $config | ConvertTo-Json -Depth 6 | Set-Content -Path $configPath -Encoding utf8
    Write-Ok "Wrote claude_desktop_config.json"
}

# -- Summary -------------------------------------------------------------------

function Show-Summary {
    param($InstallDir)

    Write-Host ""
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "   Setup complete" -ForegroundColor Green
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Installed at  $InstallDir"
    Write-Host "  API key       saved in .env"
    Write-Host ""
    Write-Host "  What to do now" -ForegroundColor White
    Write-Host ""
    Write-Host "  1. Start the tools backend (pick the one you use):"
    if ($script:HasDocker) {
        Write-Host "       Docker : docker compose up -d" -ForegroundColor Cyan
    }
    if ($script:HasWsl) {
        Write-Host "       WSL    : wsl -d kali-linux" -ForegroundColor Cyan
        Write-Host "                then inside Kali: ./setup.sh && ./start.sh" -ForegroundColor DarkGray
    }
    Write-Host "  2. Start the bridge:  .\start.ps1" -ForegroundColor Cyan
    Write-Host "  3. Restart Claude Desktop (quit fully, then reopen)"
    Write-Host "  4. Ask it: 'List all available PhantomStrike tools'"
    Write-Host ""
    Write-Host "  Next time you reboot" -ForegroundColor White
    Write-Host ""
    Write-Host "  Do not reinstall. Just run:" -ForegroundColor DarkGray
    Write-Host "     cd $InstallDir" -ForegroundColor White
    Write-Host "     .\start.ps1 -Mode status" -ForegroundColor White
    Write-Host ""
    Write-Host "  Before scanning anything" -ForegroundColor White
    Write-Host ""
    Write-Host "  Limit what can be targeted by copying engagement.example.yaml"
    Write-Host "  to engagement.yaml and listing only hosts you are authorised"
    Write-Host "  to test. See SECURITY.md."
    Write-Host ""
}

# -- Run -----------------------------------------------------------------------

Show-Banner
Test-Environment
$python = Test-Python
$installDir = Install-PhantomStrike -PythonExe $python
Set-ApiKey | Out-Null
Write-StartScript
Set-AgentConfig -InstallDir $installDir
Show-Summary -InstallDir $installDir
