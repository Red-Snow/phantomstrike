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

### 🔥 AI-Powered MCP Cybersecurity Framework

**The modular, secure, and extensible way to run pentesting tools from any AI agent.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple?style=for-the-badge)](https://modelcontextprotocol.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

**Works with: Claude Desktop • Cursor • VS Code Copilot • Gemini CLI • Any MCP Client**

[Getting Started](#-getting-started) •
[Architecture](#-architecture) •
[Supported Tools](#-supported-tools) •
[Configuration](#-configuration) •
[Contributing](#-contributing)

---

</div>

## ⚡ What is PhantomStrike?

PhantomStrike is an **MCP (Model Context Protocol) server** that gives AI agents the ability to run real cybersecurity tools — Nmap, Nuclei, SQLMap, and more — on your machine or VM and return **structured, parsed results**.

```
You → "Pentest example.com" → AI Agent → PhantomStrike MCP → Tools → Structured Results → AI Report
```

### 🎯 Why PhantomStrike?

| Feature | Traditional Approach | PhantomStrike |
|---------|---------------------|---------------|
| **Tool execution** | Manual terminal commands | AI-driven, automated |
| **Output format** | Raw text blobs | Structured JSON with findings |
| **Tool selection** | Human decides | AI intelligently chains tools |
| **Reporting** | Manual write-up | AI-generated professional reports |
| **Multi-tool workflows** | Scripted, fragile | Dynamic, adaptive |
| **Extensibility** | Edit core code | Drop-in plugin system |

---

## 🚀 Getting Started

### One-Command Install (Kali/Parrot/Ubuntu)

```bash
curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/install.sh | bash
```

### Manual Install

```bash
# Clone the repository
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike

# Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install PhantomStrike
pip install -e .
```

### Docker (Zero Setup)

```bash
git clone https://github.com/Red-Snow/phantomstrike.git
cd phantomstrike
docker compose up
```

---

## 🔌 Connect to Your AI Agent

### Claude Desktop

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "local"]
    }
  }
}
```

### Cursor / VS Code Copilot

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "phantomstrike": {
      "command": "/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "local"]
    }
  }
}
```

### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "phantomstrike": {
      "command": "/path/to/phantomstrike/.venv/bin/phantomstrike-mcp",
      "args": ["--mode", "local"]
    }
  }
}
```

### Any Other MCP Client

PhantomStrike uses the standard MCP stdio transport. Point your client to `phantomstrike-mcp` and you're done.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  AI Agent (Claude / Gemini / Copilot / Cursor)              │
│  "Scan example.com for vulnerabilities"                     │
└────────────────┬────────────────────────────────────────────┘
                 │ MCP Protocol (stdio)
┌────────────────▼────────────────────────────────────────────┐
│  PhantomStrike MCP Server                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │ Plugin       │ │ Async Job    │ │ Tool Runner          ││
│  │ Registry     │ │ Queue        │ │ (safe subprocess)    ││
│  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘│
│         │                │                     │            │
│  ┌──────▼────────────────▼─────────────────────▼──────────┐│
│  │  Plugins: nmap │ nuclei │ sqlmap │ gobuster │ hydra    ││
│  │           ffuf │ nikto  │ subfinder │ amass  │ trivy    ││
│  └────────────────────────────────────────────────────────┘│
│  ┌────────────────────────────────────────────────────────┐│
│  │  SQLite Database │ Structured Results │ Scan History   ││
│  └────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Key Design Principles

- **🔌 Plugin Architecture** — Each tool is a self-contained Python file. Adding a new tool = adding one file.
- **🔒 Secure by Default** — Input validation, no `shell=True`, API authentication.
- **⚡ Async Execution** — Tools run in the background with real-time output streaming.
- **📊 Structured Output** — Every tool returns parsed JSON, not raw text.
- **💾 Persistent History** — All scan results saved to SQLite for future reference.
- **🐳 Docker Ready** — Run everything in an isolated container.

---

## 🛠️ Supported Tools

| Category | Tools | Status |
|----------|-------|--------|
| **🌐 Network** | `nmap` · `rustscan` · `masscan` | ✅ Ready |
| **🕸️ Web App** | `nuclei` · `gobuster` · `sqlmap` · `ffuf` · `nikto` | ✅ Ready |
| **🔍 OSINT** | `subfinder` · `amass` | ✅ Ready |
| **🔑 Password** | `hydra` | ✅ Ready |
| **☁️ Cloud** | `trivy` | ✅ Ready |
| **📦 More** | _Community contributions welcome!_ | 🔜 Coming |

> **Don't see your tool?** Adding a new one takes ~50 lines of code. See [Plugin Development](#-plugin-development).

---

## 💬 Usage Examples

Once connected to your AI agent, just ask naturally:

```
"Scan 192.168.1.1 for open ports and services"
→ PhantomStrike runs nmap with XML output parsing

"Find subdomains of example.com"
→ PhantomStrike runs subfinder + amass

"Test https://target.com/login for SQL injection"
→ PhantomStrike runs sqlmap in batch mode

"Run a comprehensive vulnerability scan on https://target.com"
→ PhantomStrike chains: nmap → nuclei → gobuster → nikto

"Scan the Docker image nginx:latest for CVEs"
→ PhantomStrike runs trivy with JSON output
```

The AI agent decides which tools to use and interprets the results — you get a complete analysis with findings and recommendations.

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `PHANTOMSTRIKE_HOST` | `127.0.0.1` | Server bind address |
| `PHANTOMSTRIKE_PORT` | `8443` | Server port |
| `PHANTOMSTRIKE_AUTH_ENABLED` | `true` | Enable API authentication |
| `PHANTOMSTRIKE_MAX_JOBS` | `5` | Max concurrent tool executions |
| `PHANTOMSTRIKE_TIMEOUT` | `600` | Default tool timeout (seconds) |
| `PHANTOMSTRIKE_LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 🧩 Plugin Development

Creating a new tool plugin is simple. Create a new file in `src/phantomstrike/plugins/<category>/`:

```python
from pydantic import BaseModel, Field
from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)

class MyToolPlugin(BaseToolPlugin):
    name = "mytool"
    category = ToolCategory.WEBAPP
    description = "What my tool does"
    required_binaries = ["mytool"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target to scan")
        # Add your parameters here

    def build_command(self, params: InputSchema) -> list[str]:
        return ["mytool", "--target", params.target]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="",
            stdout=stdout,
            stderr=stderr,
        )
        # Parse stdout into structured findings
        return result
```

That's it. The plugin is automatically discovered and registered as an MCP tool.

---

## 📁 Project Structure

```
phantomstrike/
├── src/phantomstrike/
│   ├── config.py              # Centralized configuration
│   ├── main.py                # API server entry point
│   ├── mcp/
│   │   └── client.py          # MCP client (auto-generates tools)
│   ├── server/
│   │   ├── app.py             # FastAPI application
│   │   └── routes/            # REST API endpoints
│   ├── plugins/
│   │   ├── base.py            # Plugin base class
│   │   ├── registry.py        # Auto-discovery registry
│   │   ├── network/           # nmap, rustscan, masscan
│   │   ├── webapp/            # nuclei, gobuster, sqlmap, ffuf, nikto
│   │   ├── osint/             # subfinder, amass
│   │   ├── password/          # hydra
│   │   └── cloud/             # trivy
│   ├── execution/
│   │   ├── runner.py          # Safe subprocess execution
│   │   └── queue.py           # Async job queue
│   ├── storage/
│   │   └── database.py        # SQLite persistence
│   └── utils/
│       ├── logging.py         # Rich terminal output
│       └── validation.py      # Input sanitization
├── install.sh                 # One-line installer
├── Dockerfile                 # Container deployment
├── docker-compose.yml         # Docker stack
├── pyproject.toml             # Python packaging
└── phantomstrike-mcp.json     # MCP client configuration
```

---

## 🤝 Contributing

Contributions are welcome! The easiest way to contribute is by adding new tool plugins.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/add-wpscan`
3. Add your plugin in `src/phantomstrike/plugins/<category>/`
4. Test it locally
5. Submit a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 🛡️ Security

PhantomStrike is a **security tool** — use it responsibly.

- ⚠️ Only test systems you have **explicit permission** to test
- 🔒 Run in an **isolated VM** or Docker container
- 🚫 Never expose the API server to the public internet
- 🔑 Always enable authentication in production

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ for the security community**

[Report Bug](https://github.com/Red-Snow/phantomstrike/issues) •
[Request Feature](https://github.com/Red-Snow/phantomstrike/issues) •
[Contribute](CONTRIBUTING.md)

</div>
