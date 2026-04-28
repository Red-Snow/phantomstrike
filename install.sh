#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# PhantomStrike AI — One-Line Installer
# Usage: curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/install.sh | bash
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() {
    echo -e "${RED}"
    echo "  ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗"
    echo "  ██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║"
    echo "  ██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║"
    echo "  ██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║"
    echo "  ██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║"
    echo "  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝"
    echo "  ███████╗████████╗██████╗ ██╗██╗  ██╗███████╗"
    echo "  ██╔════╝╚══██╔══╝██╔══██╗██║██║ ██╔╝██╔════╝"
    echo "  ███████╗   ██║   ██████╔╝██║█████╔╝ █████╗  "
    echo "  ╚════██║   ██║   ██╔══██╗██║██╔═██╗ ██╔══╝  "
    echo "  ███████║   ██║   ██║  ██║██║██║  ██╗███████╗"
    echo "  ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝"
    echo -e "${NC}"
    echo -e "  ${CYAN}AI-Powered MCP Cybersecurity Framework${NC}"
    echo ""
}

info() { echo -e "  ${CYAN}[*]${NC} $1"; }
success() { echo -e "  ${GREEN}[✓]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC} $1"; }
error() { echo -e "  ${RED}[✗]${NC} $1"; exit 1; }

# ── Main ─────────────────────────────────────────────────────────────────────

banner

# Check Python version
info "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    error "Python 3 is not installed. Install Python 3.10+ first."
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    error "Python 3.10+ required (found $PYTHON_VERSION)"
fi
success "Python $PYTHON_VERSION detected"

# Clone or update repository
INSTALL_DIR="${PHANTOMSTRIKE_DIR:-$HOME/phantomstrike}"

if [ -d "$INSTALL_DIR" ]; then
    info "Updating existing installation at $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    git pull --quiet
    success "Repository updated"
else
    info "Cloning PhantomStrike to $INSTALL_DIR..."
    git clone --depth=1 https://github.com/Red-Snow/phantomstrike.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    success "Repository cloned"
fi

# Create virtual environment
info "Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
success "Virtual environment created"

# Install package
info "Installing PhantomStrike..."
pip install --quiet --upgrade pip
pip install --quiet -e .
success "PhantomStrike installed"

# Check for security tools
echo ""
info "Checking installed security tools..."
TOOLS=("nmap" "nuclei" "gobuster" "sqlmap" "ffuf" "nikto" "subfinder" "amass" "hydra" "trivy" "rustscan" "masscan")
FOUND=0
MISSING=0

for tool in "${TOOLS[@]}"; do
    if command -v "$tool" &> /dev/null; then
        success "$tool found"
        ((FOUND++))
    else
        warn "$tool not found (optional — install for full functionality)"
        ((MISSING++))
    fi
done

echo ""
success "Installation complete! $FOUND tools available, $MISSING optional tools missing."
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
echo ""
echo -e "  ${CYAN}# Activate environment${NC}"
echo -e "  cd $INSTALL_DIR && source .venv/bin/activate"
echo ""
echo -e "  ${CYAN}# Start MCP server (for Claude Desktop / Cursor / Gemini CLI)${NC}"
echo -e "  phantomstrike-mcp"
echo ""
echo -e "  ${CYAN}# Start API server (for direct REST API access)${NC}"
echo -e "  phantomstrike --host 0.0.0.0 --port 8443"
echo ""
echo -e "  ${CYAN}# View API docs${NC}"
echo -e "  Open http://localhost:8443/docs"
echo ""
echo -e "  ${BOLD}To configure Claude Desktop, add to claude_desktop_config.json:${NC}"
echo -e "  ${YELLOW}{\"mcpServers\":{\"phantomstrike\":{\"command\":\"$INSTALL_DIR/.venv/bin/phantomstrike-mcp\"}}}${NC}"
echo ""
