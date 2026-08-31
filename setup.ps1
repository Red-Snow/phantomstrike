# ==============================================================================
#  PhantomStrike - Automatic Setup for Windows
#
#  Installs everything, wires up your AI agent, and writes a start script so you
#  never have to remember the steps again.
#
#      irm https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/setup.ps1 | iex
#
#  Or, from a clone:  .\setup.ps1
#
#  ---------------------------------------------------------------------------
#  Pairing two machines (Windows host + Kali/Parrot VM or WSL)
#
#    1. Here on Windows:   .\setup.ps1 -Client
#    2. Paste the one line it prints into your Kali/Parrot VM or WSL.
#    3. On the VM:         ./start.sh server
#    4. Back here:         .\start.ps1 proxy
#
#  The key is generated HERE, not on the VM. Host-to-VM paste works reliably in
#  VMware and VirtualBox; the other direction often does not, so nothing ever
#  has to be copied out of the VM.
#  ---------------------------------------------------------------------------
#
#  Safe to re-run. It skips work that is already done rather than reinstalling,
#  so if a step fails you can fix the cause and run it again.
#
#  If PowerShell blocks this script, allow local scripts for this session:
#      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# ==============================================================================

[CmdletBinding()]
param(
    # This machine runs the AI agent; the tools live elsewhere. The default on
    # Windows, because the Linux security tools cannot run here natively.
    [switch]$Client,

    # This machine runs both halves. Only meaningful under WSL.
    [switch]$AllInOne,

    # Where the tools are, e.g. http://192.168.72.128:8443
    [string]$Server = '',

    # Use this key instead of generating one.
    [string]$ApiKey = '',

    [switch]$Help
)

$ErrorActionPreference = 'Stop'

if ($Help) {
    Write-Host @'
PhantomStrike setup for Windows

  .\setup.ps1                 Client mode (default): the agent is here,
                              the tools are on a Kali/Parrot VM or WSL.
  .\setup.ps1 -AllInOne       Both halves on this machine (WSL only).
  .\setup.ps1 -Server <url>   Where the tools are, e.g. http://192.168.72.128:8443
  .\setup.ps1 -ApiKey <key>   Use this key instead of generating one.

Pairing:
  1. .\setup.ps1 -Client
  2. Paste the printed line into your Kali/Parrot VM
  3. On the VM:  ./start.sh server
  4. Back here:  .\start.ps1 proxy
'@
    exit 0
}

# -- Appearance ----------------------------------------------------------------

function Write-Step { param($m) Write-Host "`n> $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "  [ok] $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host "  .   $m" -ForegroundColor Gray }
function Write-Warn { param($m) Write-Host "  [!] $m" -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host "  [x] $m" -ForegroundColor Red; exit 1 }

function Show-Banner {
    Write-Host ""
    Write-Host "  +---------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host "  |                                             |" -ForegroundColor DarkCyan
    Write-Host "  |        P H A N T O M S T R I K E            |" -ForegroundColor Cyan
    Write-Host "  |                                             |" -ForegroundColor DarkCyan
    Write-Host "  |   600+ security tools, driven by AI         |" -ForegroundColor Gray
    Write-Host "  |                                             |" -ForegroundColor DarkCyan
    Write-Host "  +---------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host ""
}

# -- State ---------------------------------------------------------------------

$script:HasWsl           = $false
$script:HasDocker        = $false
$script:Role             = ''      # client | allinone
$script:ApiKeyValue      = ''
$script:RemoteUrl        = $Server
$script:PairCommand      = ''
$script:ConfiguredAgents = @()

# -- Environment ---------------------------------------------------------------

function Test-Environment {
    Write-Step "Checking your system"
    Write-Ok "Windows $([System.Environment]::OSVersion.Version)"

    if (Get-Command wsl -ErrorAction SilentlyContinue) {
        $script:HasWsl = $true
        Write-Ok "WSL is available"
    } else {
        Write-Info "WSL not found (optional - one way to host the tools)"
    }

    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $script:HasDocker = $true
        Write-Ok "Docker is available"
    } else {
        Write-Info "Docker not found (optional - another way to host the tools)"
    }
}

function Set-Role {
    if ($AllInOne) { $script:Role = 'allinone'; Write-Ok "Mode: all-in-one (from command line)"; return }
    if ($Client)   { $script:Role = 'client';   Write-Ok "Mode: client (from command line)";     return }

    # Windows cannot run the Linux security tools, so it is nearly always the
    # client half: the AI agent lives here, the tools live in a VM or WSL.
    $script:Role = 'client'
    Write-Ok "Mode: client (Windows can't run the Linux tools, so they live elsewhere)"
    Write-Info "Override with -AllInOne if that is wrong."
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

# -- Configuration -------------------------------------------------------------

function Get-EnvValue {
    param($Name)
    if (-not (Test-Path '.env')) { return '' }
    $line = Select-String -Path '.env' -Pattern "^$Name=" | Select-Object -First 1
    if (-not $line) { return '' }
    return $line.Line.Split('=', 2)[1].Trim().Trim('"')
}

function Set-Configuration {
    param($VenvPython)
    Write-Step "Setting up configuration"

    if ($script:Role -eq 'client') {
        $existing = Get-EnvValue 'PHANTOMSTRIKE_API_KEY'
        if ($existing) {
            $script:ApiKeyValue = $existing
            $script:RemoteUrl   = if ($script:RemoteUrl) { $script:RemoteUrl } else { Get-EnvValue 'PHANTOMSTRIKE_REMOTE' }
            Write-Ok "Existing config found in .env - keeping it"
            $script:PairCommand = "curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/setup.sh | bash -s -- --api-key $existing"
            return
        }

        # The CLIENT generates the key, not the server.
        #
        # Why this direction: in VMware and VirtualBox, host-to-guest paste
        # normally works while guest-to-host often does not. Generating on the
        # server would force a copy OUT of the VM - the direction that fails -
        # so we generate here and hand you one line to paste INTO the VM.
        $script:ApiKeyValue = if ($ApiKey) { $ApiKey } else { & $VenvPython -c "import secrets; print(secrets.token_urlsafe(32))" }

        if (-not $script:RemoteUrl) {
            Write-Host ""
            Write-Info "On your Kali/Parrot VM, run:  ip -4 addr | grep inet"
            Write-Info "It shows something like 192.168.72.128 - type it here."
            Write-Host ""
            $vmIp = Read-Host "  ? VM IP address (just the numbers, or press Enter to fill in later)"
            if ($vmIp) { $script:RemoteUrl = "http://${vmIp}:8443" }
        }
        if (-not $script:RemoteUrl) { $script:RemoteUrl = 'http://CHANGE-ME:8443' }

        @(
            "# PhantomStrike client configuration - generated by setup.ps1",
            "# This machine runs the AI agent. The tools run on the server below.",
            "",
            "# Must match PHANTOMSTRIKE_API_KEYS on that server, exactly.",
            "PHANTOMSTRIKE_API_KEY=$($script:ApiKeyValue)",
            "PHANTOMSTRIKE_REMOTE=$($script:RemoteUrl)"
        ) | Set-Content -Path '.env' -Encoding ascii

        Write-Ok "Client config written to .env"
        $script:PairCommand = "curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/setup.sh | bash -s -- --api-key $($script:ApiKeyValue)"
        return
    }

    # All-in-one: this machine runs the server, so it holds the key.
    #
    # An explicit -ApiKey always wins over whatever is already on disk, so a
    # box that was first set up standalone can still be paired later. If the
    # old key silently survived, every call would come back 401 with no clue why.
    $existing = Get-EnvValue 'PHANTOMSTRIKE_API_KEYS'
    if ($existing) {
        if ((-not $ApiKey) -or ($ApiKey -eq $existing)) {
            $script:ApiKeyValue = $existing
            Write-Ok "Existing key found in .env - keeping it"
            return
        }
        Copy-Item '.env' ".env.backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
        $lines = @(Get-Content '.env' | Where-Object { $_ -notmatch '^PHANTOMSTRIKE_API_KEYS=' })
        $lines += "PHANTOMSTRIKE_API_KEYS=$ApiKey"
        $lines | Set-Content -Path '.env' -Encoding ascii
        $script:ApiKeyValue = $ApiKey
        Write-Ok "Replaced the old key with the one you supplied"
        Write-Info "The previous .env was backed up next to it."
        return
    }

    $script:ApiKeyValue = if ($ApiKey) { $ApiKey } else { & $VenvPython -c "import secrets; print(secrets.token_urlsafe(32))" }
    @(
        "# PhantomStrike configuration - generated by setup.ps1",
        "# This file contains a secret. Do not commit it.",
        "PHANTOMSTRIKE_API_KEYS=$($script:ApiKeyValue)",
        "PHANTOMSTRIKE_ENFORCE_SCOPE=true",
        # Universal shell access is the whole point of the framework: it is what
        # makes all 600+ tools reachable instead of only the ones with dedicated
        # plugins. Auth plus the cross-origin guard is what protects it.
        "PHANTOMSTRIKE_ALLOW_RAW_SHELL=true"
    ) | Add-Content -Path '.env' -Encoding ascii

    Write-Ok "Key generated and saved to .env"
}

# -- Start script --------------------------------------------------------------
#
# The point of this: after a reboot, people were reinstalling from scratch
# because they had no record of how to start things again. Now there is one file.

function Write-StartScript {
    Write-Step "Creating your start script"

    $content = @'
# ==============================================================================
#  Start PhantomStrike
#
#  Run this after a reboot. You do NOT need to reinstall anything.
#
#      .\start.ps1              start the right piece for this machine
#      .\start.ps1 server       start the API server (the machine with the tools)
#      .\start.ps1 proxy        start the bridge (the machine with the AI agent)
#      .\start.ps1 status       check what is running and reachable
# ==============================================================================
param(
    [ValidateSet('', 'proxy', 'server', 'status')]
    [string]$Mode = '',
    [string]$Remote = ''
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
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"'), 'Process')
        }
    }
}

# A client install has PHANTOMSTRIKE_REMOTE; a server install has API_KEYS.
if (-not $Mode) {
    $Mode = if ($env:PHANTOMSTRIKE_REMOTE) { 'proxy' } else { 'server' }
}
if (-not $Remote) {
    $Remote = if ($env:PHANTOMSTRIKE_REMOTE) { $env:PHANTOMSTRIKE_REMOTE } else { 'http://localhost:8443' }
}

switch ($Mode) {
    'server' {
        if (-not $env:PHANTOMSTRIKE_API_KEYS) {
            Write-Host "No PHANTOMSTRIKE_API_KEYS set - the server will refuse to start." -ForegroundColor Yellow
            Write-Host "This looks like a client install. Did you mean: .\start.ps1 proxy" -ForegroundColor Yellow
            Write-Host ""
        }
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
        if (-not $env:PHANTOMSTRIKE_API_KEY) {
            $env:PHANTOMSTRIKE_API_KEY = $env:PHANTOMSTRIKE_API_KEYS
        }
        if (-not $env:PHANTOMSTRIKE_API_KEY) {
            Write-Host "No API key set." -ForegroundColor Red
            Write-Host "Run .\setup.ps1 -Client to generate one."
            exit 1
        }
        if ($Remote -like '*CHANGE-ME*') {
            Write-Host "Server URL not set." -ForegroundColor Red
            Write-Host "Edit .env and set PHANTOMSTRIKE_REMOTE to your Kali/Parrot box,"
            Write-Host "e.g. http://192.168.72.128:8443"
            Write-Host "Find the IP by running on the VM:  ip -4 addr | grep inet"
            exit 1
        }
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
            Invoke-RestMethod -Uri "$Remote/health" -TimeoutSec 3 | Out-Null
            Write-Host "  [ok] API server reachable at $Remote" -ForegroundColor Green
        } catch {
            Write-Host "  [ ]  API server NOT reachable at $Remote" -ForegroundColor Yellow
            if ($env:PHANTOMSTRIKE_REMOTE) {
                Write-Host "       Start it on that machine: ./start.sh server"
                Write-Host "       Then check the IP and that port 8443 is open."
            } else {
                Write-Host "       Start it here: .\start.ps1 server"
            }
        }
        $proxy = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
                 Where-Object { $_.CommandLine -like '*proxy_daemon*' }
        if ($proxy) {
            Write-Host "  [ok] Proxy daemon is running" -ForegroundColor Green
        } else {
            Write-Host "  [ ]  Proxy daemon not running  -> .\start.ps1 proxy" -ForegroundColor Yellow
        }
    }
}
'@

    Set-Content -Path 'start.ps1' -Value $content -Encoding ascii
    Write-Ok "Created start.ps1"
}

# -- Agent configuration -------------------------------------------------------
#
# Hand-editing claude_desktop_config.json is the step people get stuck on, and
# it is exactly the step a script can do perfectly: load, add one key, write
# back, keep everything else. The merge runs in Python rather than PowerShell
# because Windows PowerShell 5.1 has no ConvertFrom-Json -AsHashtable and its
# Set-Content -Encoding utf8 writes a BOM that some JSON readers reject.

$script:MergeScript = @'
import json, os, sys

path, mcp_bin, mode = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    if os.path.exists(path):
        # utf-8-sig tolerates a BOM left by an earlier hand-edit in Notepad.
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read().strip()
        config = json.loads(text) if text else {}
    else:
        config = {}
except (json.JSONDecodeError, OSError):
    # Malformed or unreadable: refuse to guess. A backup already exists and the
    # caller prints the manual snippet when this exits non-zero.
    sys.exit(1)

if not isinstance(config, dict):
    sys.exit(1)

servers = config.setdefault("mcpServers", {})
if not isinstance(servers, dict):
    sys.exit(1)

servers["phantomstrike"] = {"command": mcp_bin, "args": ["--mode", mode]}

parent = os.path.dirname(path)
if parent:
    os.makedirs(parent, exist_ok=True)
with open(path, "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2)
    fh.write("\n")

print(len(servers) - 1)
'@

function Set-AgentConfig {
    param($InstallDir, $VenvPython)
    Write-Step "Configuring your AI agent"

    # local  = run the tools right here.
    # remote = send them to the server; the proxy daemon carries the request.
    $mcpMode = if ($script:Role -eq 'client') { 'remote' } else { 'local' }
    $mcpBin  = Join-Path $InstallDir '.venv\Scripts\phantomstrike-mcp.exe'

    $mergePy = Join-Path ([System.IO.Path]::GetTempPath()) 'phantomstrike-merge.py'
    Set-Content -Path $mergePy -Value $script:MergeScript -Encoding ascii

    $targets = @(
        @{ Label = 'Claude Desktop'; Path = (Join-Path $env:APPDATA    'Claude\claude_desktop_config.json') },
        @{ Label = 'Cursor';         Path = (Join-Path $env:USERPROFILE '.cursor\mcp.json') },
        @{ Label = 'Gemini CLI';     Path = (Join-Path $env:USERPROFILE '.gemini\settings.json') }
    )

    foreach ($t in $targets) {
        $dir = Split-Path $t.Path -Parent

        # Claude Desktop only creates %APPDATA%\Claude after its first launch.
        # A freshly installed copy that has never been opened would otherwise
        # be skipped as "not installed", so look for the program itself too.
        if ($t.Label -eq 'Claude Desktop' -and -not (Test-Path $dir)) {
            $installed = (Test-Path (Join-Path $env:LOCALAPPDATA 'AnthropicClaude')) -or
                         (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\Claude'))
            if ($installed) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        }

        # Only touch agents that are actually installed - never create config
        # directories for software you do not have.
        if (-not (Test-Path $dir)) { continue }

        $existed = Test-Path $t.Path
        if ($existed) {
            Copy-Item $t.Path "$($t.Path).backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
        }

        $others = & $VenvPython $mergePy $t.Path $mcpBin $mcpMode 2>$null
        if ($LASTEXITCODE -eq 0) {
            $verb = if ($existed) { 'Merged into' } else { 'Created' }
            if ([int]$others -gt 0) {
                Write-Ok "$verb $(Split-Path $t.Path -Leaf)  (--mode $mcpMode, kept $others other server(s))"
            } else {
                Write-Ok "$verb $(Split-Path $t.Path -Leaf)  (--mode $mcpMode)"
            }
            Write-Info "  $($t.Path)"
            $script:ConfiguredAgents += $t.Label
        } else {
            Write-Warn "$(Split-Path $t.Path -Leaf) is not valid JSON - not touching it."
            Write-Info "Backup saved. Add this inside `"mcpServers`" by hand:"
            Write-Host "      `"phantomstrike`": { `"command`": `"$mcpBin`", `"args`": [`"--mode`", `"$mcpMode`"] }" -ForegroundColor DarkGray
        }
    }

    Remove-Item $mergePy -ErrorAction SilentlyContinue

    # Codex CLI uses TOML rather than JSON, so it needs its own block.
    $codexDir = Join-Path $env:USERPROFILE '.codex'
    $codexCfg = Join-Path $codexDir 'config.toml'
    if (Test-Path $codexDir) {
        if ((Test-Path $codexCfg) -and (Select-String -Path $codexCfg -Pattern 'phantomstrike' -Quiet)) {
            Write-Ok "Already configured: config.toml (Codex)"
            $script:ConfiguredAgents += 'Codex'
        } else {
            if (Test-Path $codexCfg) {
                Copy-Item $codexCfg "$codexCfg.backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
            }
            $toml = @(
                "",
                "[mcp_servers.phantomstrike]",
                "command = `"$($mcpBin -replace '\\', '\\')`"",
                "args = [`"--mode`", `"$mcpMode`"]"
            )
            $toml | Add-Content -Path $codexCfg -Encoding ascii
            Write-Ok "Updated config.toml (Codex)"
            $script:ConfiguredAgents += 'Codex'
        }
    }

    if ($script:ConfiguredAgents.Count -eq 0) {
        Write-Warn "No AI agent found on this machine - nothing was configured."
        Write-Info "PhantomStrike works with any MCP-compatible agent."
        Write-Info "If Claude Desktop is installed, open it once so it creates its"
        Write-Info "settings folder, then run this script again."
        Write-Info "Looked for:"
        foreach ($t in $targets) { Write-Info "  $($t.Path)" }
        Write-Info "  $codexCfg"
    }
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
    Write-Host "  Mode          $($script:Role)"
    Write-Host ""

    if ($script:Role -eq 'client') {
        Write-Host "  This machine runs the AI agent. The tools run elsewhere." -ForegroundColor White
        Write-Host ""
        Write-Host "  What to do now" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Copy the line below and paste it into your Kali/Parrot VM." -ForegroundColor White
        Write-Host "     (Windows-to-VM paste works; that is why the key is generated here.)" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "     $($script:PairCommand)" -ForegroundColor Green
        Write-Host ""
        Write-Host "     Then on the VM:  cd ~/phantomstrike && ./start.sh server" -ForegroundColor DarkGray
        if ($script:HasWsl) {
            Write-Host "     Using WSL instead of a VM? Run the same line inside:  wsl" -ForegroundColor DarkGray
        }
        Write-Host ""
        Write-Host "  2. Back here, start the bridge and leave it open:"
        Write-Host "       cd $InstallDir" -ForegroundColor White
        Write-Host "       .\start.ps1 proxy" -ForegroundColor White
        if ($script:ConfiguredAgents.Count -gt 0) {
            Write-Host "  3. Fully quit and reopen: $($script:ConfiguredAgents -join ', ')"
            Write-Host "     Its config is already written; you do not edit any JSON." -ForegroundColor DarkGray
        } else {
            Write-Host "  3. Quit your AI agent completely, then reopen it"
        }
        Write-Host "  4. Ask it: 'List all available PhantomStrike tools'"
        Write-Host ""
        Write-Host "  Check before you start" -ForegroundColor White
        Write-Host ""
        Write-Host "     .\start.ps1 status   - says whether the server is reachable" -ForegroundColor White
        Write-Host ""
        Write-Host "  Next time you reboot" -ForegroundColor White
        Write-Host ""
        Write-Host "  Do not reinstall. Start the server on the VM, then here:" -ForegroundColor DarkGray
        Write-Host "     cd $InstallDir" -ForegroundColor White
        Write-Host "     .\start.ps1 proxy" -ForegroundColor White
    } else {
        Write-Host "  What to do now" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Start the server and leave it open:"
        Write-Host "       cd $InstallDir" -ForegroundColor White
        Write-Host "       .\start.ps1 server" -ForegroundColor White
        Write-Host "  2. Fully quit and reopen your AI agent"
        Write-Host "  3. Ask it: 'List all available PhantomStrike tools'"
        Write-Host ""
        Write-Host "  Next time you reboot" -ForegroundColor White
        Write-Host ""
        Write-Host "  Do not reinstall. Just run:" -ForegroundColor DarkGray
        Write-Host "     cd $InstallDir" -ForegroundColor White
        Write-Host "     .\start.ps1 status" -ForegroundColor White
    }

    Write-Host ""
    Write-Host "  Before scanning anything" -ForegroundColor White
    Write-Host ""
    Write-Host "  Limit what can be targeted by copying engagement.example.yaml"
    Write-Host "  to engagement.yaml on the machine running the server, listing"
    Write-Host "  only hosts you are authorised to test. See SECURITY.md."
    Write-Host ""
}

# -- Run -----------------------------------------------------------------------

Show-Banner
Test-Environment
Set-Role
$python = Test-Python
$installDir = Install-PhantomStrike -PythonExe $python
$venvPython = Join-Path $installDir '.venv\Scripts\python.exe'
Set-Configuration -VenvPython $venvPython
Write-StartScript
Set-AgentConfig -InstallDir $installDir -VenvPython $venvPython
Show-Summary -InstallDir $installDir
