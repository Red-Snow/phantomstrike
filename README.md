<div align="center">

```
 ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗
 ██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║
 ██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║
 ██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║
 ██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║
 ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝
 ███████╗████████╗██████╗ ██╗██╗  ██╗███████╗
 ██╔════╝╚══██╔══╝██╔══██╗██║██║ ██╔╝██╔════╝
 ███████╗   ██║   ██████╔╝██║█████╔╝ █████╗
 ╚════██║   ██║   ██╔══██╗██║██╔═██╗ ██╔══╝
 ███████║   ██║   ██║  ██║██║██║  ██╗███████╗
 ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝
```

### 🔥 AI-Powered Pentesting — Run 600+ Kali Linux Tools from Claude Desktop

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple?style=for-the-badge)](https://modelcontextprotocol.io/)

**Works with: Claude Desktop · Cursor · VS Code Copilot · Gemini CLI · Any MCP Client**

</div>

---

## ⚡ What is PhantomStrike?

PhantomStrike connects your AI assistant to a **Kali Linux VM** via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). Instead of switching between terminals, just tell Claude what you want:

```
You:    "Scan 192.168.1.1 for open ports, then enumerate any web services you find."
Claude: Runs nmap → finds port 80 → runs nikto + gobuster → gives you a full report.
```

- **12 structured plugins** (nmap, nuclei, sqlmap, hydra, etc.) with parsed JSON output
- **Universal shell tool** — run literally *any* command installed on Kali (`wpscan`, `metasploit`, `enum4linux`, `aircrack-ng`, etc.)
- **AI-driven tool chaining** — Claude reads results and automatically decides what to run next

---

## 🚀 Setup Guide

PhantomStrike uses a **split architecture**: your AI agent runs on your host machine (Mac/Windows/Linux), and security tools execute on a **Kali Linux VM**.

```
┌──────────────┐    Unix Socket    ┌───────────────┐    HTTP/TCP    ┌──────────────┐
│  Claude       │ ◄──────────────► │  Proxy Daemon  │ ◄────────────► │  Kali VM     │
│  Desktop      │  (local IPC)     │  (on your Mac) │  (network)     │  API Server  │
└──────────────┘                   └───────────────┘                └──────────────┘
```

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| **Host machine** | macOS, Windows, or Linux with Python 3.10+ |
| **Kali Linux VM** | VMware, VirtualBox, or bare metal — with network access from host |
| **AI Client** | Claude Desktop, Cursor, VS Code Copilot, or any MCP client |

---

### Step 1 — Install on Kali VM

SSH into your Kali VM (or open a terminal) and run:

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Start the API server:

```bash
phantomstrike --host 0.0.0.0 --port 8443
```

You should see all 13 plugins registered with ✅. **Leave this terminal open.**

---

### Step 2 — Install on your Host Machine

Open a terminal on your **Mac / Windows / Linux** host:

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
```

**Activate the virtual environment:**

| OS | Command |
|----|---------|
| macOS / Linux | `source .venv/bin/activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (CMD) | `.venv\Scripts\activate.bat` |

Then install:

```bash
pip install -e .
```

---

### Step 3 — Start the Proxy Daemon

> **Why is this needed?** Claude Desktop sandboxes MCP processes and blocks their outbound network connections. The proxy daemon runs outside this sandbox and relays requests to the Kali VM via a local Unix socket (macOS/Linux) or named pipe (Windows).

In a **new terminal tab** on your host machine:

```bash
cd phantomstrike
source .venv/bin/activate        # or .venv\Scripts\Activate.ps1 on Windows
python3 proxy_daemon.py --remote http://YOUR_KALI_IP:8443
```

Replace `YOUR_KALI_IP` with your Kali VM's IP address (find it with `ip a` on Kali).

You should see:
```
🔌 PhantomStrike Proxy Daemon running
   Socket: /tmp/phantomstrike_proxy.sock
   Remote: http://YOUR_KALI_IP:8443
```

**Leave this terminal open.**

---

### Step 4 — Configure your AI Client

#### Claude Desktop

Open Settings → Developer → Edit Config, and set:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/full/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://YOUR_KALI_IP:8443"]
    }
  }
}
```

> **Tip:** Find the full path by running `which phantomstrike-mcp` (with the venv activated).

> **Windows users:** Use the full `.exe` path, e.g. `C:\\Users\\you\\phantomstrike\\.venv\\Scripts\\phantomstrike-mcp.exe`

#### Cursor / VS Code Copilot

Add to `.cursor/mcp.json`:

```json
{
  "servers": {
    "phantomstrike": {
      "command": "/full/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://YOUR_KALI_IP:8443"]
    }
  }
}
```

#### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/full/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote", "--server", "http://YOUR_KALI_IP:8443"]
    }
  }
}
```

**Restart your AI client** after saving the config.

---

### Step 5 — Verify

Open a new chat in your AI client and type:

```
Use run_kali_shell to run "whoami" on the Kali VM.
```

If you see `root` — **you're done!** 🎉

---

## ✅ Startup Checklist (Daily Use)

Every time you want to use PhantomStrike, make sure these 3 things are running:

| # | Where | Command |
|---|-------|---------|
| 1 | **Kali VM** | `cd ~/phantomstrike && source .venv/bin/activate && phantomstrike --host 0.0.0.0 --port 8443` |
| 2 | **Host (new tab)** | `cd ~/phantomstrike && source .venv/bin/activate && python3 proxy_daemon.py --remote http://KALI_IP:8443` |
| 3 | **Host** | Open Claude Desktop / Cursor / etc. |

---

## 🛠️ Supported Tools

### Structured Plugins (parsed JSON output)

| Category | Tools |
|----------|-------|
| 🌐 **Network** | `nmap` · `rustscan` · `masscan` |
| 🕸️ **Web App** | `nuclei` · `gobuster` · `sqlmap` · `ffuf` · `nikto` |
| 🔍 **OSINT** | `subfinder` · `amass` |
| 🔑 **Password** | `hydra` |
| ☁️ **Cloud** | `trivy` |

### Universal Shell (`run_kali_shell`)

Run **any** command on the Kali VM. The AI reads the raw output and interprets it for you:

| Just say... | Claude runs... |
|-------------|---------------|
| "Enumerate SMB shares on the target" | `enum4linux-ng -A 192.168.1.1` |
| "Scan for WordPress vulnerabilities" | `wpscan --url http://target --enumerate vp,vt,u` |
| "Check for SNMP misconfigs" | `snmpwalk -v2c -c public 192.168.1.1` |
| "Crack these hashes" | `hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt` |
| "Run a Metasploit scan" | `msfconsole -q -x "db_nmap -sV target; vulns"` |

---

## 💬 Usage Examples

```
"Scan 192.168.1.1 for open ports and services"
→ Runs nmap with service detection, returns structured findings

"Find subdomains of example.com"
→ Runs subfinder + amass, deduplicates results

"Do a full pentest recon on 10.0.0.5"
→ Chains nmap → nikto → gobuster → nuclei automatically

"Test https://target.com/login for SQL injection"
→ Runs sqlmap in batch mode with parsed results

"List all Kali tools related to WiFi hacking"
→ Runs dpkg -l | grep aircrack and shows available tools
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  AI Agent (Claude / Gemini / Copilot / Cursor)              │
│  "Scan example.com for vulnerabilities"                     │
└────────────────┬────────────────────────────────────────────┘
                 │ MCP Protocol (stdio)
┌────────────────▼────────────────────────────────────────────┐
│  PhantomStrike MCP Client (on your host machine)            │
│  ┌──────────────┐  ┌─────────────────────────────────────┐  │
│  │ Plugin        │  │ Unix Socket IPC                     │  │
│  │ Registry      │  │ → Proxy Daemon → HTTP → Kali VM    │  │
│  └──────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                 │ HTTP (your network)
┌────────────────▼────────────────────────────────────────────┐
│  PhantomStrike API Server (on Kali VM)                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │ Plugin       │ │ Async Job    │ │ Tool Runner          ││
│  │ Registry     │ │ Queue        │ │ (safe subprocess)    ││
│  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘│
│  ┌──────▼────────────────▼─────────────────────▼──────────┐│
│  │  nmap │ nuclei │ sqlmap │ gobuster │ hydra │ nikto     ││
│  │  ffuf │ subfinder │ amass │ rustscan │ masscan │ trivy  ││
│  │  kali_shell (universal — ANY command)                   ││
│  └────────────────────────────────────────────────────────┘│
│  ┌────────────────────────────────────────────────────────┐│
│  │  SQLite Database │ Structured Results │ Scan History   ││
│  └────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 🧩 Adding Custom Plugins

Create a new file in `src/phantomstrike/plugins/<category>/`:

```python
from pydantic import BaseModel, Field
from phantomstrike.plugins.base import (
    BaseToolPlugin, ToolCategory, ToolResult, ToolStatus,
)

class MyToolPlugin(BaseToolPlugin):
    name = "mytool"
    category = ToolCategory.WEBAPP
    description = "What my tool does"
    required_binaries = ["mytool"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target to scan")

    def build_command(self, params: InputSchema) -> list[str]:
        return ["mytool", "--target", params.target]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )
```

Drop it in, restart — it's automatically discovered and available as an MCP tool.

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| **Claude says "tool not found"** | Restart Claude Desktop (Cmd+Q / close fully and reopen) |
| **"All connection attempts failed"** | Make sure the **proxy daemon** is running on your host |
| **"Server disconnected"** in Claude settings | Check that the `command` path in your config is correct (`which phantomstrike-mcp`) |
| **Kali tools show ⚠️ unavailable** | Install missing tools on Kali: `apt install nmap nuclei sqlmap` etc. |
| **Scans return empty results** | Try adding `-Pn` flag (host may block ping probes) |

---

## 🛡️ Security

PhantomStrike is a **security tool** — use it responsibly.

- ⚠️ Only test systems you have **explicit written permission** to test
- 🔒 Run in an **isolated VM** or Docker container
- 🚫 Never expose the API server to the public internet
- 🔑 Always enable authentication in production

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ by [Red-Snow](https://github.com/Red-Snow) for the security community**

[Report Bug](https://github.com/Red-Snow/phantomstrike/issues) ·
[Request Feature](https://github.com/Red-Snow/phantomstrike/issues)

</div>
