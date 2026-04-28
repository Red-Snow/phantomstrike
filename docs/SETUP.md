# PhantomStrike — Complete Setup Guide

Choose the deployment option that best fits your setup. All three are fully supported.

---

## Quick Comparison

| | **Option A** — All-in-Kali | **Option B** — Split (Mac/Win + VM) | **Option C** — Docker |
|---|---|---|---|
| **Difficulty** | ⭐ Easiest | ⭐⭐⭐ Advanced | ⭐⭐ Easy |
| **Available tools** | 600+ (full Kali) | 600+ (full Kali) | ~10 core tools |
| **Networking required** | ❌ None | ✅ VM ↔ Host | ❌ None |
| **Needs a VM** | ✅ Yes | ✅ Yes | ❌ No |
| **Works on Windows** | ✅ Via WSL2 | ✅ Yes | ✅ Yes |
| **Works on macOS** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Best for** | Most users | Power users | Quick start / CI-CD |

> **Not sure which to pick?** → Start with **Option A**. It's the simplest and gives you access to every Kali tool.

---

## Option A — Everything Inside Kali ⭐ Recommended

Claude (or your AI agent) runs **inside the same Kali environment** as PhantomStrike. No networking between machines.

### How It Works

```
┌──────────────── Kali Linux VM / WSL2 ─────────────────┐
│                                                        │
│  Claude Desktop / Cursor / Gemini CLI                  │
│            │                                           │
│            │  MCP (local stdio pipe)                   │
│            ▼                                           │
│   PhantomStrike MCP Server                             │
│            │                                           │
│            ▼                                           │
│   nmap · nuclei · sqlmap · gobuster · hydra · ...      │
│   (all pre-installed on Kali Linux)                    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### ✅ Pros
- Simplest setup — no networking between machines needed
- Kali ships with 90%+ of tools already installed
- All attack traffic stays inside the isolated VM
- Fastest performance — MCP runs over a local pipe

### ❌ Cons
- Your AI agent (Claude/Cursor) must run inside the VM too
- VM needs a desktop environment for Claude Desktop
- Shares CPU/RAM with host machine

---

### Step 1 — Set Up Kali Linux

**On macOS (VMware Fusion / VirtualBox)**

1. Download the Kali VM image: [https://www.kali.org/get-kali/#kali-virtual-machines](https://www.kali.org/get-kali/#kali-virtual-machines)
2. Import the `.vmx` or `.ova` into VMware Fusion or VirtualBox
3. Recommended specs: 4 GB RAM, 40 GB disk, 2 CPUs

**On Windows (WSL2)**

Open PowerShell as Administrator:

```powershell
# Step 1 — Enable WSL2
wsl --install
wsl --set-default-version 2

# Step 2 — Install Kali Linux
wsl --install -d kali-linux

# Step 3 — Launch and update
kali
```

Inside the Kali terminal:

```bash
sudo apt update && sudo apt full-upgrade -y

# Install the core PhantomStrike tools
sudo apt install -y nmap masscan amass hydra ffuf gobuster nikto nuclei sqlmap subfinder

---

### Step 2 — Install PhantomStrike (Inside Kali)

```bash
# One-command install
curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/install.sh | bash
```

Or manually:

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

### Step 3 — Install Your AI Agent (Inside Kali)

> ⚠️ **Claude Desktop does NOT have a Linux version.** For Kali/Linux, use **Cursor** or **Gemini CLI** instead.

**Option 1 — Cursor (Recommended for Linux)**

```bash
# One-line installer
curl https://cursor.com/install -fsS | sh
```

Or download the AppImage from [https://cursor.com](https://cursor.com), then:

```bash
chmod +x cursor-*.AppImage
./cursor-*.AppImage
```

**Option 2 — Gemini CLI**

```bash
# Requires Node.js 18+
node --version   # check version first

# Install Node.js if needed
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install Gemini CLI
npm install -g @google/gemini-cli

# Run and authenticate
gemini
```

---

### Step 4 — Connect PhantomStrike to Your AI Agent

**Cursor** — open Settings → Features → MCP → Add New MCP Server

Or create `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/root/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "local"]
    }
  }
}
```

> Replace `/root/phantomstrike` with the actual path where you cloned the repo.

**Gemini CLI** — edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/root/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "local"]
    }
  }
}
```

---

### Step 5 — Test It

Open Cursor or Gemini CLI and ask:

> *"List all available PhantomStrike tools"*
> *"Scan 127.0.0.1 with nmap"*

---

## Option B — Split Setup: AI on Host, Tools on Kali VM

Your AI agent (Claude Desktop) runs on your **macOS or Windows host**. PhantomStrike sends tool requests over HTTP to a Kali VM.

### How It Works

```
┌────── macOS / Windows Host ──────┐     ┌──── Kali Linux VM ────┐
│                                  │     │                        │
│  Claude Desktop                  │     │  PhantomStrike API     │
│  Cursor / Gemini CLI             │     │  Server (:8443)        │
│            │                     │     │        │               │
│            │ MCP (stdio)         │     │        ▼               │
│            ▼                     │     │  nmap · nuclei · ...   │
│  PhantomStrike MCP Client        │     │                        │
│            │                     │     │                        │
│            │ HTTP ───────────────┼────▶│                        │
│                                  │     │                        │
└──────────────────────────────────┘     └────────────────────────┘
```

### ✅ Pros
- Claude Desktop runs natively on macOS/Windows — better experience
- Kali VM can be headless (no GUI needed, saves RAM)
- All attack traffic stays inside the VM
- Use Cursor/Copilot on your host with your normal dev workflow

### ❌ Cons
- Requires network connectivity between host and VM
- Slightly more complex setup (two installations)
- Must configure VM networking (Bridged or NAT)

---

### Step 1 — On Kali VM: Install and Start the API Server

```bash
# Install core tools
sudo apt update
sudo apt install -y nmap masscan amass hydra ffuf gobuster nikto nuclei sqlmap subfinder

# Install PhantomStrike
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Start the API server — bind to all interfaces so the host can reach it
phantomstrike --host 0.0.0.0 --port 8443
```

Get your Kali VM IP address:

```bash
ip addr show | grep "inet " | grep -v 127.0.0.1
# Example: inet 192.168.72.128/24  → IP is 192.168.72.128
```

Allow port 8443 through the firewall (if needed):

```bash
sudo ufw allow 8443
```

---

### Step 2 — Configure VM Networking

In **VMware Fusion** (macOS): VM → Settings → Network Adapter → **Bridged** or **NAT**

In **VirtualBox**: Settings → Network → Adapter 1 → **NAT** (default works) or **Bridged**

Test from your host machine:

```bash
curl http://192.168.72.128:8443/health
# Expected: {"status": "healthy", ...}
```

---

### Step 3 — On Your Host: Install PhantomStrike MCP Client

> 💡 **Why install it twice?** 
> In this split setup, the **Kali VM** runs the API Server (which executes the attacks), while your **Host machine** runs the MCP Client (which talks to Claude/Cursor via `stdio` and forwards the requests over HTTP to Kali). Both components are included in the same repository.

**macOS**

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Windows**

Open PowerShell:

```powershell
# Install Python 3.10+ if needed: https://www.python.org/downloads/
python --version   # verify

git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

---

### Step 4 — Install Your AI Agent on the Host

**Claude Desktop (macOS + Windows)**

1. Download from [https://claude.ai/download](https://claude.ai/download)
2. **macOS:** Open the `.dmg` → drag to Applications
3. **Windows:** Run the `.exe` installer → follow wizard
4. Sign in with your Anthropic account

> ⚠️ Claude Desktop is **not available on Linux**. Use Cursor or Gemini CLI on Linux hosts.

**Cursor (macOS + Windows + Linux)**

1. Go to [https://cursor.com](https://cursor.com)
2. Click **Download** — the site auto-detects your OS
3. **macOS:** Open `.dmg` → drag to Applications
4. **Windows:** Run the `.exe` installer
5. **Linux:** `curl https://cursor.com/install -fsS | sh`

**Gemini CLI (all platforms)**

```bash
# Requires Node.js 18+  →  https://nodejs.org/en/download
npm install -g @google/gemini-cli
gemini   # opens browser for Google account authentication
```

---

### Step 5 — Configure Your AI Agent (on the Host)

**Claude Desktop — macOS**

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/Users/YOUR_USERNAME/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://192.168.72.128:8443"]
    }
  }
}
```

**Claude Desktop — Windows**

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "C:\\Users\\YOUR_USERNAME\\phantomstrike\\.venv\\Scripts\\phantomstrike-mcp.exe",
      "args": ["--mode", "remote", "--server", "http://192.168.72.128:8443"]
    }
  }
}
```

> Tip: Press `Win + R`, paste `%APPDATA%\Claude`, press Enter to open the folder.

**Cursor — macOS**

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/Users/YOUR_USERNAME/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://192.168.72.128:8443"]
    }
  }
}
```

**Cursor — Windows**

Edit `%USERPROFILE%\.cursor\mcp.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "C:\\Users\\YOUR_USERNAME\\phantomstrike\\.venv\\Scripts\\phantomstrike-mcp.exe",
      "args": ["--mode", "remote", "--server", "http://192.168.72.128:8443"]
    }
  }
}
```

> Tip: In Cursor, go to **Settings → Features → MCP → Add New MCP Server** to configure via the UI.

**Gemini CLI — all platforms**

Edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://192.168.72.128:8443"]
    }
  }
}
```

> ⚠️ Replace `192.168.72.128` with your actual Kali VM IP. Replace `YOUR_USERNAME` with your system username.

---

### Step 6 — Test It

Restart your AI agent (required after config changes), then ask:

> *"List available PhantomStrike tools"*
> *"Run an nmap scan on 10.0.0.1"*

### Troubleshooting

| Problem | Fix |
|---|---|
| `Connection refused` | Ensure `phantomstrike` server is running on Kali |
| `No route to host` | Switch VM to Bridged networking mode |
| Port 8443 blocked | Run `sudo ufw allow 8443` on Kali |
| Wrong path in config | Run `which phantomstrike-mcp` on the host to get the correct path |
| MCP timeout | Increase timeout in the tool — some scans take 5+ minutes |

---

## Option C — Docker (No VM Required)

Everything runs in a Docker container on your machine. No VM needed.

### How It Works

```
┌───────────── Your Machine (macOS / Windows / Linux) ──────────────┐
│                                                                    │
│  Claude Desktop / Cursor / Gemini CLI                              │
│            │                                                       │
│            │  MCP (stdio)                                          │
│            ▼                                                       │
│  PhantomStrike MCP Client                                          │
│            │                                                       │
│            │  HTTP (localhost:8443)                                │
│            ▼                                                       │
│  ┌────────────── Docker Container ──────────────────┐              │
│  │  PhantomStrike API Server                        │              │
│  │  nmap · nuclei · sqlmap · nikto · hydra · ...    │              │
│  └──────────────────────────────────────────────────┘              │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### ✅ Pros
- No VM required — runs on macOS, Windows, or Linux
- One-command startup: `docker compose up -d`
- Reproducible environment
- Easy cleanup: `docker compose down`

### ❌ Cons
- Fewer tools than a full Kali install (~10 core tools in the container)
- Docker image is ~1 GB, takes a few minutes to build on first run
- Some network scanning tools may have limitations inside a container

---

### Step 1 — Install Docker Desktop

- **macOS / Windows:** Download from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
- **Linux:** Follow the [Docker Engine install guide](https://docs.docker.com/engine/install/)

Verify Docker is running:

```bash
docker --version
# Docker version 27.x.x, build ...
```

---

### Step 2 — Start PhantomStrike

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike

# Build and start the container (takes ~3 minutes on first run)
docker compose up -d

# Verify it's running
curl http://localhost:8443/health
# Expected: {"status": "healthy", ...}
```

---

### Step 3 — Install the MCP Client Locally

```bash
# In the same phantomstrike directory
python3 -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows PowerShell
pip install -e .
```

---

### Step 4 — Configure Your AI Agent

**Claude Desktop — macOS**

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/Users/YOUR_USERNAME/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://localhost:8443"]
    }
  }
}
```

**Claude Desktop — Windows**

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "C:\\Users\\YOUR_USERNAME\\phantomstrike\\.venv\\Scripts\\phantomstrike-mcp.exe",
      "args": ["--mode", "remote", "--server", "http://localhost:8443"]
    }
  }
}
```

**Cursor — macOS** (`~/.cursor/mcp.json`) **/ Windows** (`%USERPROFILE%\.cursor\mcp.json`):

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://localhost:8443"]
    }
  }
}
```

**Gemini CLI** (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://localhost:8443"]
    }
  }
}
```

---

### Step 5 — Manage the Container

```bash
# Start
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f

# Rebuild after code changes
docker compose up -d --build
```

---

## Which Option Should I Use?

```
Do you have (or want) a Kali VM?
├── No  → Option C — Docker (quickest start, fewer tools)
└── Yes → Where do you want your AI agent to run?
          ├── Inside the VM  → Option A ⭐ (simplest, all tools)
          └── On my host Mac/Windows → Option B (split setup)
```

---

## Verifying Your Installation

After any setup, confirm PhantomStrike is working:

```bash
# Activate the environment
source /path/to/phantomstrike/.venv/bin/activate

# Check the MCP server starts without errors
phantomstrike-mcp --help
```

Or open the API docs in your browser (Options B & C):

```
http://localhost:8443/docs
```

You'll see an interactive OpenAPI page listing all 12 tool endpoints.

---

## Need Help?

- 📖 [README](../README.md) — Project overview
- 🐛 [Report a Bug](https://github.com/Red-Snow/phantomstrike/issues)
- 💬 [Discussions](https://github.com/Red-Snow/phantomstrike/discussions)
