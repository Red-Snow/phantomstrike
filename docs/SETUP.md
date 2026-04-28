# PhantomStrike — Complete Setup Guide

Choose the deployment option that fits your workflow. All three are fully supported.

---

## Quick Comparison

| | Option A: All-in-Kali | Option B: Split (Mac + VM) | Option C: Docker |
|---|---|---|---|
| **Difficulty** | ⭐ Easiest | ⭐⭐⭐ Advanced | ⭐⭐ Easy |
| **Pre-installed tools** | 90%+ on Kali | 90%+ on Kali | ~10 core tools |
| **Networking required** | ❌ None | ✅ VM↔Host | ❌ None |
| **Performance** | Fast (native) | Slight latency | Fast (native) |
| **Security isolation** | ✅ VM sandboxed | ✅ VM sandboxed | ⚠️ Container only |
| **Needs Kali/Parrot VM** | ✅ Yes | ✅ Yes | ❌ No |
| **Best for** | Pentesters, CTF | Multi-machine setups | Quick demos, CI/CD |

---

## Option A: Everything Inside Kali VM ⭐ Recommended

> **Best for:** Most users. Simple, secure, and all tools pre-installed.

### How It Works

```
┌──────────────────── Kali Linux VM ────────────────────┐
│                                                        │
│  Claude Desktop / Cursor / Gemini CLI                  │
│       │                                                │
│       │ MCP (stdio — local pipe)                       │
│       ▼                                                │
│  PhantomStrike MCP Server                              │
│       │                                                │
│       ▼                                                │
│  nmap, nuclei, sqlmap, gobuster, hydra, ...            │
│  (all pre-installed on Kali)                           │
│                                                        │
└────────────────────────────────────────────────────────┘
```

Everything runs inside a single Kali/Parrot VM. No networking between machines.

### Step-by-Step Installation

#### 1. Set Up Your Kali VM

If you don't have one yet:
- Download [Kali Linux](https://www.kali.org/get-kali/) (VM image for VMware/VirtualBox)
- Import into VMware Fusion / VirtualBox / UTM
- Recommended: 4GB+ RAM, 40GB+ disk

#### 2. Install PhantomStrike (Inside Kali Terminal)

```bash
# One-command install
curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/install.sh | bash
```

Or manually:

```bash
# Clone
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike

# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### 3. Install Your AI Agent (Inside Kali)

**Claude Desktop:**
```bash
# Download Claude Desktop for Linux
# https://claude.ai/download
# Install the .deb package:
sudo dpkg -i claude-desktop_*.deb
```

**Cursor:**
```bash
# Download from https://cursor.sh
# Install the AppImage or .deb
```

**Gemini CLI:**
```bash
npm install -g @anthropic-ai/gemini-cli
```

#### 4. Connect PhantomStrike to Your AI Agent

**For Claude Desktop**, edit `~/.config/claude/claude_desktop_config.json`:

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

**For Cursor**, create `.cursor/mcp.json` in your project:

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

**For Gemini CLI**, edit `~/.gemini/settings.json`:

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

#### 5. Test It!

Open Claude Desktop (or your AI agent) and type:

> "List all available PhantomStrike tools"

You should see the 12 registered tools. Then try:

> "Scan 127.0.0.1 with nmap"

### Pros
- ✅ **Simplest setup** — no networking between machines
- ✅ **All tools pre-installed** — Kali ships with nmap, sqlmap, hydra, nikto, etc.
- ✅ **Fully isolated** — all attack traffic stays inside the VM
- ✅ **Best performance** — everything communicates over local pipes

### Cons
- ❌ Need to run your AI agent (Claude) inside the VM
- ❌ VM needs a GUI desktop environment for Claude Desktop
- ❌ VM resource overhead (RAM/CPU shared with host)

---

## Option B: Split Setup — AI on macOS, Tools on Kali VM

> **Best for:** Users who want Claude Desktop on their Mac while running tools in Kali.

### How It Works

```
┌──────── macOS Host ────────┐     ┌────────── Kali VM ──────────┐
│                            │     │                              │
│  Claude Desktop / Cursor   │     │  PhantomStrike API Server    │
│       │                    │     │       │                      │
│       │ MCP (stdio)        │     │       ▼                      │
│       ▼                    │     │  nmap, nuclei, sqlmap, ...   │
│  PhantomStrike MCP Client  │     │                              │
│       │                    │     │  Listening on port 8443      │
│       │ HTTP ──────────────┼────▶│                              │
│                            │     │                              │
└────────────────────────────┘     └──────────────────────────────┘
```

The MCP client runs on Mac and forwards requests over the network to the API server on Kali.

### Step-by-Step Installation

#### 1. On Your Kali VM — Install & Start the API Server

```bash
# Install PhantomStrike
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Start the API server (bind to all interfaces so Mac can reach it)
phantomstrike --host 0.0.0.0 --port 8443
```

The server is now listening at `http://KALI_IP:8443`.

#### 2. Find Your Kali VM's IP Address

```bash
# Inside Kali
ip addr show | grep "inet " | grep -v 127.0.0.1
# Example output: inet 192.168.72.128/24
```

#### 3. Configure VM Networking

Your VM must be reachable from macOS. In VMware Fusion:
- Go to **VM → Settings → Network Adapter**
- Choose **Bridged** (shares your host network) or **NAT** (default, also works)

Test from macOS terminal:
```bash
# Replace with your Kali IP
curl http://192.168.72.128:8443/health
# Should return: {"status": "healthy", ...}
```

#### 4. On Your Mac — Install PhantomStrike MCP Client

```bash
# Clone (just for the MCP client)
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### 5. Configure Claude Desktop on Mac

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

> ⚠️ Replace `192.168.72.128` with your Kali VM's actual IP address.
> ⚠️ Replace `YOUR_USERNAME` with your macOS username.

#### 6. Test It!

Open Claude Desktop on Mac and try:

> "Scan 10.0.0.1 with nmap using PhantomStrike"

The request flows: Claude Desktop (Mac) → MCP Client (Mac) → HTTP → API Server (Kali) → nmap (Kali) → results back.

### Pros
- ✅ **Claude Desktop runs natively on macOS** — better UI experience
- ✅ **Tools fully isolated in VM** — Mac never touches attack traffic
- ✅ **Can use Cursor/Copilot on Mac** with your normal dev workflow
- ✅ **Kali VM can be headless** — no GUI needed, SSH is enough

### Cons
- ❌ **Network configuration required** — VM must be reachable from host
- ❌ **Slight latency** — HTTP between host and VM (usually <10ms)
- ❌ **Two installations** — MCP client on Mac + API server on Kali
- ❌ **Firewall issues possible** — must ensure port 8443 is accessible
- ❌ **API security** — should enable authentication in production

### Troubleshooting

| Problem | Solution |
|---|---|
| `curl: Connection refused` | Check Kali firewall: `sudo ufw allow 8443` |
| `curl: No route to host` | Switch VM network to Bridged mode |
| MCP timeout | Increase timeout: `--server http://IP:8443 --timeout 300` |
| Tools not found on Kali | Run `sudo apt install nmap nuclei sqlmap` |

---

## Option C: Docker — No VM Required

> **Best for:** Quick demos, CI/CD pipelines, or users without a Kali VM.

### How It Works

```
┌──────────────────── Your Machine ─────────────────────┐
│                                                        │
│  Claude Desktop / Cursor / Gemini CLI                  │
│       │                                                │
│       │ MCP (stdio)                                    │
│       ▼                                                │
│  PhantomStrike MCP Client                              │
│       │                                                │
│       │ HTTP (localhost:8443)                           │
│       ▼                                                │
│  ┌──────────── Docker Container ──────────────────┐    │
│  │  PhantomStrike API Server                      │    │
│  │  nmap, nuclei, sqlmap, nikto, hydra, ...       │    │
│  └────────────────────────────────────────────────┘    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

Tools run inside a Docker container on your machine. No VM needed.

### Step-by-Step Installation

#### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Python 3.10+ (for the MCP client)

#### 2. Start PhantomStrike with Docker

```bash
# Clone the repo
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike

# Start the container (builds automatically on first run)
docker compose up -d
```

That's it! The API server is now running at `http://localhost:8443`.

Verify:
```bash
curl http://localhost:8443/health
# {"status": "healthy", ...}
```

#### 3. Install the MCP Client Locally

```bash
# In the same phantomstrike directory
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### 4. Configure Your AI Agent

**Claude Desktop** — edit `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `~/.config/claude/claude_desktop_config.json` (Linux):

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://localhost:8443"]
    }
  }
}
```

#### 5. Test It!

```
"List all available PhantomStrike tools"
"Scan scanme.nmap.org with nmap"
```

### Managing the Container

```bash
# Start
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f

# Rebuild (after code changes)
docker compose up -d --build
```

### Pros
- ✅ **No VM required** — runs on Mac, Linux, or Windows
- ✅ **One command startup** — `docker compose up -d`
- ✅ **Reproducible** — same environment everywhere
- ✅ **Easy cleanup** — `docker compose down` removes everything
- ✅ **Great for CI/CD** — automate security testing in pipelines

### Cons
- ❌ **Fewer tools** — Docker image has ~10 core tools vs Kali's 600+
- ❌ **Container limitations** — some tools may need `--privileged` mode
- ❌ **Docker overhead** — image is ~1GB, takes time to build first run
- ❌ **Not a full pentest OS** — missing many specialized Kali tools
- ❌ **Network scanning limits** — container networking may affect scan results

---

## Summary: Which Option Should I Choose?

```
Are you a pentester / security professional?
├── Yes → Do you want Claude on your Mac or inside the VM?
│   ├── Inside VM → Option A ⭐ (simplest, most tools)
│   └── On Mac    → Option B (split setup)
└── No / Just trying it out
    └── Option C (Docker, quickest start)
```

### Still Unsure?

**Start with Option A.** It's the simplest, most complete, and most secure. You can always switch later — the PhantomStrike codebase is the same for all three options.

---

## Verify Your Installation

After any option, run this quick check:

```bash
# Activate the environment
source /path/to/phantomstrike/.venv/bin/activate

# Check registered plugins
phantomstrike-mcp --help

# Or start the API server and check the docs
phantomstrike --host 127.0.0.1 --port 8443
# Then open http://localhost:8443/docs in your browser
```

You should see the interactive OpenAPI documentation listing all available tool endpoints.

---

## Need Help?

- 📖 [README](../README.md) — Project overview and quick start
- 🐛 [Report a Bug](https://github.com/Red-Snow/phantomstrike/issues)
- 💬 [Discussions](https://github.com/Red-Snow/phantomstrike/discussions)
