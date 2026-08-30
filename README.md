# PhantomStrike

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Security Policy](https://img.shields.io/badge/security-policy-orange.svg)](SECURITY.md)

**Run Kali Linux security tools from an AI agent.** Ask Claude, Cursor, or Gemini CLI to scan a host, and PhantomStrike runs `nmap`, `nuclei`, `sqlmap` or `ffuf` for real and hands back parsed results.

> **For authorised testing only.** Point this at systems you own or have written permission to test. See [SECURITY.md](SECURITY.md).

---

## Pick one setup path

You only need **one**. Read the row, pick the path, and follow only that section — the three paths are self-contained and their commands are not interchangeable.

| | **Path A — All in Kali** | **Path B — Split** | **Path C — Docker** |
|---|---|---|---|
| **Best if** | You already work inside Kali | You want Claude Desktop on Mac/Windows | You want to avoid VMs |
| **AI agent runs on** | Kali | Your computer | Your computer |
| **Tools run on** | Kali | Kali VM | A container |
| **Claude Desktop?** | ❌ No Linux version | ✅ Yes | ✅ Yes |
| **Pieces to keep running** | 1 | 3 | 3 |
| **Difficulty** | Easiest | Hardest | Medium |

**Not sure?** Use **Path A** if you live in Kali. Use **Path C** if you're on macOS or Windows and want Claude Desktop.

---

## Before you start: what actually runs where

Most setup confusion comes from losing track of which machine a command belongs to. Every command block below is labelled:

> **🐉 Run in Kali** &nbsp;·&nbsp; **💻 Run on your computer**

There are only three moving pieces in this system:

| Piece | What it is | Paths |
|---|---|---|
| **API server** | Runs the actual security tools. Started with `phantomstrike` | B, C |
| **Proxy daemon** | Bridges Claude Desktop's network sandbox over a Unix socket | B, C |
| **MCP client** | Started automatically by your AI agent — you never run it by hand | A, B, C |

In **Path A** there is no API server and no proxy. The agent runs tools directly. That's why it's the simplest.

---

## Path A — Everything inside Kali

<details>
<summary><b>Open Path A setup</b> — agent and tools both in Kali. No API key needed.</summary>

### A1. Install the security tools

> **🐉 Run in Kali**

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y nmap masscan amass hydra ffuf gobuster nikto nuclei sqlmap subfinder
```

<details>
<summary>Don't have Kali yet?</summary>

**Windows (WSL2)** — in PowerShell as Administrator:

```powershell
wsl --install
wsl --set-default-version 2
wsl --install -d kali-linux
kali
```

**macOS** — download the [Kali VM image](https://www.kali.org/get-kali/#kali-virtual-machines) and import it into VMware Fusion or VirtualBox. Give it 4 GB RAM, 40 GB disk, 2 CPUs.

</details>

### A2. Install PhantomStrike

> **🐉 Run in Kali**

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Note the full path — you need it in step A4:

```bash
pwd
# e.g. /root/phantomstrike
```

### A3. Install an AI agent

> **🐉 Run in Kali**
>
> Claude Desktop has no Linux build. Use Cursor or Gemini CLI here.

**Cursor:**

```bash
curl https://cursor.com/install -fsS | sh
```

**Gemini CLI:**

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
npm install -g @google/gemini-cli
gemini          # sign in when prompted
```

### A4. Connect the agent

> **🐉 Run in Kali**

Create the config file for whichever agent you installed. **Replace `/root/phantomstrike` with the path from step A2.**

**Cursor** — `~/.cursor/mcp.json`
**Gemini CLI** — `~/.gemini/settings.json`

Both use the same content:

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

Restart your agent so it reads the new config.

### A5. Check it works

Ask your agent:

> *"List all available PhantomStrike tools"*

You should get a list of tools. If not, see [Troubleshooting](#troubleshooting).

### 🔄 Starting it again later

**Nothing.** Open your AI agent and use it — it starts PhantomStrike for you.

You never need to repeat steps A1–A4. If tools stop working, restart your agent first.

</details>

---

## Path B — AI on your computer, tools on a Kali VM

<details>
<summary><b>Open Path B setup</b> — Claude Desktop on Mac/Windows, tools on a Kali VM.</summary>

Three pieces stay running: the **API server** in Kali, the **proxy daemon** on your computer, and your **AI agent**.

### B1. Install and start the API server

> **🐉 Run in Kali**

```bash
sudo apt update
sudo apt install -y nmap masscan amass hydra ffuf gobuster nikto nuclei sqlmap subfinder

git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Generate an API key. The server will not start without one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy that value — you need it again in step B3. Then start the server:

```bash
export PHANTOMSTRIKE_API_KEYS="paste-your-key-here"
phantomstrike --host 0.0.0.0 --port 8443
```

**Leave this terminal open.** Now find your Kali IP, in a second Kali terminal:

```bash
ip addr show | grep "inet " | grep -v 127.0.0.1
# e.g. inet 192.168.72.128/24  →  your IP is 192.168.72.128
```

If your host can't reach it later: `sudo ufw allow 8443`

### B2. Install PhantomStrike on your computer

> **💻 Run on your computer**

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
pip install -e .
```

### B3. Start the proxy daemon

> **💻 Run on your computer, in a new terminal**
>
> Claude Desktop blocks MCP processes from making network connections — even to your own machine. The proxy relays over a Unix socket, which is permitted.

```bash
cd phantomstrike
source .venv/bin/activate          # or .venv\Scripts\Activate.ps1 on Windows

export PHANTOMSTRIKE_API_KEY="the-same-key-from-step-B1"
python3 proxy_daemon.py --remote http://192.168.72.128:8443
```

Replace the IP with yours from step B1. You should see:

```text
🔌 PhantomStrike Proxy Daemon running
   Socket: /tmp/phantomstrike_proxy.sock
   Auth:   API key loaded
```

If it says `NO KEY SET`, every tool call will fail with 401. Set the variable and restart it.

**Leave this terminal open.**

### B4. Connect Claude Desktop

> **💻 Run on your computer**

Edit your config file:

- **macOS** — `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** — `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/full/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote"]
    }
  }
}
```

Use the full path from step B2 (`pwd` prints it). Restart Claude Desktop completely — quit, don't just close the window.

### B5. Check it works

Ask Claude:

> *"List all available PhantomStrike tools"*

### 🔄 Starting it again later

After a reboot you do **not** reinstall anything. Start the two background pieces again:

| Order | Where | Command |
|---|---|---|
| 1 | **🐉 Kali** | `cd phantomstrike && source .venv/bin/activate`<br>`export PHANTOMSTRIKE_API_KEYS="your-key"`<br>`phantomstrike --host 0.0.0.0 --port 8443` |
| 2 | **💻 Your computer** | `cd phantomstrike && source .venv/bin/activate`<br>`export PHANTOMSTRIKE_API_KEY="your-key"`<br>`python3 proxy_daemon.py --remote http://YOUR_KALI_IP:8443` |
| 3 | **💻 Your computer** | Open Claude Desktop |

Both terminals must stay open while you work. Tip: put steps 1 and 2 in a shell script so it's one command each.

</details>

---

## Path C — Docker

<details>
<summary><b>Open Path C setup</b> — no VM required.</summary>

Three pieces stay running: the **container**, the **proxy daemon**, and your **AI agent**.

### C1. Install Docker

> **💻 Run on your computer**

Install [Docker Desktop](https://www.docker.com/products/docker-desktop), then confirm it's running:

```bash
docker --version
```

### C2. Start the container

> **💻 Run on your computer**

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
```

Generate an API key — the server won't start without one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save it into a `.env` file that Docker Compose reads automatically:

```bash
echo 'PHANTOMSTRIKE_API_KEYS=paste-your-key-here' >> .env
docker compose up -d
```

First build takes about 3 minutes. Check it:

```bash
curl http://localhost:8443/health
# {"status":"healthy", ...}
```

### C3. Install the MCP client

> **💻 Run on your computer, same folder**

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows PowerShell
pip install -e .
```

### C4. Start the proxy daemon

> **💻 Run on your computer, in a new terminal**
>
> Needed even though the container is on localhost — Claude Desktop's sandbox blocks localhost TCP too.

```bash
cd phantomstrike
source .venv/bin/activate

export PHANTOMSTRIKE_API_KEY="the-same-key-from-step-C2"
python3 proxy_daemon.py --remote http://localhost:8443
```

Confirm it prints `Auth: API key loaded`. **Leave this terminal open.**

### C5. Connect Claude Desktop

> **💻 Run on your computer**

- **macOS** — `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** — `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/full/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "remote"]
    }
  }
}
```

Quit Claude Desktop completely and reopen it.

### C6. Check it works

Ask Claude:

> *"List all available PhantomStrike tools"*

### 🔄 Starting it again later

You do **not** rebuild or reinstall. The container restarts itself with Docker; you only restart the proxy.

| Order | Where | Command |
|---|---|---|
| 1 | **💻 Your computer** | `cd phantomstrike && docker compose up -d` |
| 2 | **💻 Your computer** | `cd phantomstrike && source .venv/bin/activate`<br>`export PHANTOMSTRIKE_API_KEY="your-key"`<br>`python3 proxy_daemon.py --remote http://localhost:8443` |
| 3 | **💻 Your computer** | Open Claude Desktop |

**Container commands:**

```bash
docker compose up -d        # start
docker compose down         # stop
docker compose logs -f      # watch logs
docker compose up -d --build   # rebuild after code changes
```

</details>

---

## Safety controls

Three settings decide how much this tool can do. Defaults are conservative on purpose.

| Setting | Default | What it does |
|---|---|---|
| `PHANTOMSTRIKE_API_KEYS` | **required** | The server refuses to start without a key. Paths B and C only. |
| `PHANTOMSTRIKE_ENGAGEMENT` | unset | Path to a scope file. Targets outside it are refused. |
| `PHANTOMSTRIKE_ALLOW_RAW_SHELL` | `false` | Enables arbitrary shell commands. Leave off unless you need it. |

### Limiting what can be scanned

Without a scope file, PhantomStrike will scan anything it's asked to. To constrain it, copy `engagement.example.yaml` to `engagement.yaml`:

```yaml
client: Example Corp
in_scope:
  - 10.10.0.0/16
  - "*.staging.example.com"
out_of_scope:
  - 10.10.99.0/24
```

Then point the server at it:

```bash
export PHANTOMSTRIKE_ENGAGEMENT=./engagement.yaml
```

Anything outside `in_scope` is refused before the command is built — including when the AI agent is the one asking. That matters more than it sounds: an agent decides what to run next based on tool output, and tool output comes from the host being scanned. See [SECURITY.md](SECURITY.md) for the full threat model.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Server exits with "no API keys are configured" | Working as designed | `export PHANTOMSTRIKE_API_KEYS="<key>"` before starting |
| Proxy prints `Auth: NO KEY SET` | Key not exported in that terminal | `export PHANTOMSTRIKE_API_KEY="<key>"`, restart the proxy |
| Every tool returns 401 | Proxy key ≠ server key | Make both variables the same value |
| Agent shows no PhantomStrike tools | Config not loaded | Check the path in your config, then fully quit and reopen the agent |
| `kali_shell` missing from the tool list | Disabled by default | `export PHANTOMSTRIKE_ALLOW_RAW_SHELL=true` and restart |
| "out of scope" refusals | Engagement file active | Add the target to `in_scope`, or unset `PHANTOMSTRIKE_ENGAGEMENT` |
| Tool reports "binary not found" | Not installed in Kali | `sudo apt install -y <tool>` |
| Host can't reach the Kali API | Firewall or wrong IP | `sudo ufw allow 8443`; re-check the IP with `ip addr show` |

**Still stuck?** Open an [issue](https://github.com/Red-Snow/phantomstrike/issues) with your path (A/B/C), the command you ran, and the output.

---

## Available tools

**Parsed output** — results come back structured, not as raw text:

| Category | Tools |
|---|---|
| Network | `nmap`, `masscan`, `rustscan` |
| Web | `nuclei`, `nikto`, `ffuf`, `gobuster`, `sqlmap` |
| OSINT | `amass`, `subfinder` |
| Cloud | `trivy` |
| Credentials | `hydra` |

**Raw shell** — `kali_shell` runs any command and returns raw output. Disabled by default; see [Safety controls](#safety-controls).

---

## Example prompts

> *"Scan 10.10.0.5 for open ports and tell me what's exposed"*
> *"Run nuclei against https://staging.example.com and summarise anything high severity"*
> *"Enumerate subdomains of example.com, then check which resolve"*

---

## Contributing

Adding a tool means writing one plugin class — see [CONTRIBUTING.md](CONTRIBUTING.md).

Security issues: please report privately via [SECURITY.md](SECURITY.md) rather than opening an issue.

---

## License

[MIT](LICENSE) © Farman Ullah Khan
