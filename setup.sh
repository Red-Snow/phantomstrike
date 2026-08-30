#!/usr/bin/env bash
# ==============================================================================
#  PhantomStrike — Automatic Setup
#
#  Installs everything and writes a start script so you never have to remember
#  the steps again.
#
#      curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/setup.sh | bash
#
#  Or, from a clone:  ./setup.sh
#
#  Safe to re-run. It skips work that is already done rather than reinstalling,
#  so if a step fails you can fix the cause and run it again.
#
#  Supports: Kali · Parrot · Debian · Ubuntu · Fedora · Arch · macOS · WSL2
# ==============================================================================

set -euo pipefail

# ── Appearance ─────────────────────────────────────────────────────────

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'
    B='\033[1m'; DIM='\033[2m'; N='\033[0m'
else
    R=''; G=''; Y=''; C=''; B=''; DIM=''; N=''
fi

step()    { echo -e "\n${B}${C}▸ $1${N}"; }
info()    { echo -e "  ${C}·${N} $1"; }
ok()      { echo -e "  ${G}✓${N} $1"; }
warn()    { echo -e "  ${Y}!${N} $1"; }
fail()    { echo -e "  ${R}✗${N} $1" >&2; exit 1; }
ask()     { echo -en "  ${B}?${N} $1"; }

banner() {
cat <<'EOF'

  +---------------------------------------------+
  |                                             |
  |        P H A N T O M S T R I K E            |
  |                                             |
  |   Kali & Parrot tools, driven by AI         |
  |                                             |
  +---------------------------------------------+

EOF
}

# ── Environment detection ───────────────────────────────────────────────

OS=""           # linux | macos
DISTRO=""       # kali | parrot | debian | ubuntu | fedora | arch | unknown
PKG=""          # apt | dnf | pacman | brew
IS_WSL="no"
SUDO=""

detect_environment() {
    step "Checking your system"

    case "$(uname -s)" in
        Linux*)  OS="linux" ;;
        Darwin*) OS="macos" ;;
        *)       fail "Unsupported system: $(uname -s). This script handles Linux and macOS; Windows users should run setup.ps1 instead." ;;
    esac

    if [ "$OS" = "linux" ]; then
        if grep -qi microsoft /proc/version 2>/dev/null; then
            IS_WSL="yes"
        fi

        if [ -r /etc/os-release ]; then
            # shellcheck disable=SC1091
            . /etc/os-release
            # Order matters: Parrot and Kali both set ID_LIKE=debian, so they
            # must be matched before the debian fallback.
            case "${ID:-}${ID_LIKE:-}" in
                *kali*)            DISTRO="kali" ;;
                *parrot*)          DISTRO="parrot" ;;
                *ubuntu*)          DISTRO="ubuntu" ;;
                *debian*)          DISTRO="debian" ;;
                *fedora*|*rhel*)   DISTRO="fedora" ;;
                *arch*)            DISTRO="arch" ;;
                *)                 DISTRO="unknown" ;;
            esac
        fi

        if   command -v apt-get >/dev/null 2>&1; then PKG="apt"
        elif command -v dnf     >/dev/null 2>&1; then PKG="dnf"
        elif command -v pacman  >/dev/null 2>&1; then PKG="pacman"
        fi
    else
        DISTRO="macos"
        command -v brew >/dev/null 2>&1 && PKG="brew"
    fi

    # Root already? Then no sudo needed. Otherwise use it if present.
    if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi

    local label="$DISTRO"
    [ "$IS_WSL" = "yes" ] && label="$label (WSL2)"
    ok "Detected: ${B}${label}${N}"
    [ -n "$PKG" ] && ok "Package manager: ${B}${PKG}${N}" || warn "No supported package manager found — security tools must be installed manually"
}

# ── Python ────────────────────────────────────────────────────────────

check_python() {
    step "Checking Python"

    command -v python3 >/dev/null 2>&1 || fail "Python 3 not found. Install Python 3.10 or newer, then run this again."

    local version major minor
    version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=${version%%.*}
    minor=${version##*.}

    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
        fail "Python 3.10+ required, found $version. Upgrade Python and run this again."
    fi
    ok "Python $version"

    # Debian-family systems ship venv separately and fail confusingly without it.
    if [ "$PKG" = "apt" ] && ! python3 -c 'import venv' >/dev/null 2>&1; then
        info "Installing python3-venv…"
        $SUDO apt-get install -y -qq python3-venv >/dev/null 2>&1 || fail "Could not install python3-venv"
        ok "python3-venv installed"
    fi
}

# ── Security tools ─────────────────────────────────────────────────────

TOOLS="nmap masscan amass hydra ffuf gobuster nikto nuclei sqlmap subfinder"

install_tools() {
    step "Installing security tools"

    local missing=""
    for t in $TOOLS; do
        command -v "$t" >/dev/null 2>&1 || missing="$missing $t"
    done

    if [ -z "$missing" ]; then
        ok "All tools already present — nothing to install"
        return
    fi

    info "Missing:${missing}"

    case "$PKG" in
        apt)
            info "Updating package lists (this can take a minute)…"
            $SUDO apt-get update -qq || warn "apt update reported problems; continuing"
            # Install individually: one unavailable package must not abort the rest.
            for t in $missing; do
                if $SUDO apt-get install -y -qq "$t" >/dev/null 2>&1; then
                    ok "$t"
                else
                    warn "$t unavailable via apt — install it manually if you need it"
                fi
            done
            ;;
        dnf)
            for t in $missing; do
                $SUDO dnf install -y -q "$t" >/dev/null 2>&1 && ok "$t" || warn "$t unavailable via dnf"
            done
            ;;
        pacman)
            for t in $missing; do
                $SUDO pacman -S --noconfirm --quiet "$t" >/dev/null 2>&1 && ok "$t" || warn "$t unavailable via pacman"
            done
            ;;
        brew)
            for t in $missing; do
                brew install "$t" >/dev/null 2>&1 && ok "$t" || warn "$t unavailable via brew"
            done
            ;;
        *)
            warn "Install these manually:${missing}"
            ;;
    esac

    if [ "$DISTRO" != "kali" ] && [ "$DISTRO" != "parrot" ]; then
        info "Tip: Kali and Parrot ship most of these preinstalled."
    fi
}

# ── PhantomStrike ─────────────────────────────────────────────────────

INSTALL_DIR=""

install_phantomstrike() {
    step "Installing PhantomStrike"

    # Running from inside a clone? Use it. Otherwise clone to a known location.
    if [ -f "./pyproject.toml" ] && grep -q 'name = "phantomstrike"' ./pyproject.toml 2>/dev/null; then
        INSTALL_DIR="$(pwd)"
        ok "Using this clone: $INSTALL_DIR"
    else
        INSTALL_DIR="${PHANTOMSTRIKE_DIR:-$HOME/phantomstrike}"
        if [ -d "$INSTALL_DIR/.git" ]; then
            info "Updating existing install at $INSTALL_DIR…"
            git -C "$INSTALL_DIR" pull --quiet || warn "Could not pull latest changes; using what is on disk"
        else
            command -v git >/dev/null 2>&1 || fail "git not found. Install git and run this again."
            info "Cloning to $INSTALL_DIR…"
            git clone --quiet --depth=1 https://github.com/Red-Snow/phantomstrike.git "$INSTALL_DIR"
        fi
        ok "Repository ready"
    fi

    cd "$INSTALL_DIR"

    if [ ! -d ".venv" ]; then
        info "Creating virtual environment…"
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate

    info "Installing Python package…"
    pip install --quiet --upgrade pip
    pip install --quiet -e . || fail "pip install failed. Scroll up for the reason."
    ok "PhantomStrike installed"
}

# ── API key ──────────────────────────────────────────────────────────

API_KEY=""

setup_api_key() {
    step "Setting up your API key"

    if [ -f ".env" ] && grep -q "^PHANTOMSTRIKE_API_KEYS=" .env; then
        API_KEY=$(grep "^PHANTOMSTRIKE_API_KEYS=" .env | head -1 | cut -d= -f2- | tr -d '"')
        ok "Existing key found in .env — keeping it"
        return
    fi

    API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

    # .env is gitignored; the key must never reach the repository.
    {
        echo "# PhantomStrike configuration — generated by setup.sh"
        echo "# This file contains a secret. Do not commit it."
        echo "PHANTOMSTRIKE_API_KEYS=$API_KEY"
        echo "PHANTOMSTRIKE_ENFORCE_SCOPE=true"
        echo "PHANTOMSTRIKE_ALLOW_RAW_SHELL=true"
    } >> .env

    ok "Key generated and saved to .env"
    info "The server refuses to start without this key. setup.sh handles it for you."
}

# ── Start script ─────────────────────────────────────────────────────
#
# The point of this: after a reboot, novice users were reinstalling from scratch
# because they had no record of how to start things again. Now there is one file.

write_start_script() {
    step "Creating your start script"

    cat > start.sh <<'STARTEOF'
#!/usr/bin/env bash
# ==============================================================================
#  Start PhantomStrike
#
#  Run this after a reboot. You do NOT need to reinstall anything.
#
#      ./start.sh              start the API server
#      ./start.sh proxy        start the proxy daemon (Claude Desktop setups)
#      ./start.sh status       check what is already running
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; R='\033[0;31m'; B='\033[1m'; N='\033[0m'

[ -d .venv ] || { echo -e "${R}No .venv found. Run ./setup.sh first.${N}"; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate

if [ -f .env ]; then
    set -a; # shellcheck disable=SC1091
    source .env; set +a
else
    echo -e "${Y}No .env found — the server needs PHANTOMSTRIKE_API_KEYS. Run ./setup.sh${N}"
fi

MODE="${1:-server}"

case "$MODE" in
  server)
    echo -e "${B}${C}Starting PhantomStrike API server${N}"
    echo -e "  Listening on : ${B}http://0.0.0.0:8443${N}"
    echo -e "  API docs     : http://localhost:8443/docs"
    echo -e "  Stop with    : Ctrl+C"
    echo ""
    echo -e "  ${Y}Keep this window open while you work.${N}"
    echo ""
    exec phantomstrike --host 0.0.0.0 --port 8443
    ;;

  proxy)
    REMOTE="${2:-http://localhost:8443}"
    export PHANTOMSTRIKE_API_KEY="${PHANTOMSTRIKE_API_KEYS:-}"
    echo -e "${B}${C}Starting PhantomStrike proxy daemon${N}"
    echo -e "  Forwarding to : ${B}${REMOTE}${N}"
    echo -e "  Stop with     : Ctrl+C"
    echo ""
    echo -e "  ${Y}Keep this window open while you work.${N}"
    echo ""
    exec python3 proxy_daemon.py --remote "$REMOTE"
    ;;

  status)
    echo -e "${B}PhantomStrike status${N}"
    if curl -sf http://localhost:8443/health >/dev/null 2>&1; then
        echo -e "  ${G}✓${N} API server is running"
    else
        echo -e "  ${Y}·${N} API server not running   → ./start.sh"
    fi
    if [ -S /tmp/phantomstrike_proxy.sock ]; then
        echo -e "  ${G}✓${N} Proxy daemon is running"
    else
        echo -e "  ${Y}·${N} Proxy daemon not running → ./start.sh proxy"
    fi
    ;;

  *)
    echo "Usage: ./start.sh [server|proxy|status]"
    exit 1
    ;;
esac
STARTEOF

    chmod +x start.sh
    ok "Created ${B}start.sh${N}"
}

# ── Agent configuration ────────────────────────────────────────────────

configure_agent() {
    step "Configuring your AI agent"

    local mcp_bin="$INSTALL_DIR/.venv/bin/phantomstrike-mcp"
    local snippet="{\"mcpServers\":{\"phantomstrike\":{\"command\":\"$mcp_bin\",\"args\":[\"--mode\",\"local\"]}}}"

    local claude_cfg cursor_cfg gemini_cfg written="no"
    if [ "$OS" = "macos" ]; then
        claude_cfg="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    else
        claude_cfg="$HOME/.config/Claude/claude_desktop_config.json"
    fi
    cursor_cfg="$HOME/.cursor/mcp.json"
    gemini_cfg="$HOME/.gemini/settings.json"

    for cfg in "$cursor_cfg" "$gemini_cfg" "$claude_cfg"; do
        local dir; dir="$(dirname "$cfg")"
        # Only touch agents that are actually installed — never create config
        # directories for software the user does not have.
        [ -d "$dir" ] || continue

        if [ -f "$cfg" ]; then
            if grep -q "phantomstrike" "$cfg" 2>/dev/null; then
                ok "Already configured: $(basename "$cfg")"
                written="yes"; continue
            fi
            cp "$cfg" "$cfg.backup-$(date +%s)"
            warn "$(basename "$cfg") exists and has other servers in it."
            info "Backed it up. Add this entry to \"mcpServers\" yourself:"
            echo -e "${DIM}    \"phantomstrike\": {\"command\": \"$mcp_bin\", \"args\": [\"--mode\", \"local\"]}${N}"
        else
            echo "$snippet" > "$cfg"
            ok "Wrote $(basename "$cfg")"
            written="yes"
        fi
    done

    # Codex CLI uses TOML rather than JSON, so it needs its own block.
    local codex_cfg="$HOME/.codex/config.toml"
    if [ -d "$HOME/.codex" ]; then
        if [ -f "$codex_cfg" ] && grep -q "phantomstrike" "$codex_cfg" 2>/dev/null; then
            ok "Already configured: config.toml (Codex)"
            written="yes"
        else
            [ -f "$codex_cfg" ] && cp "$codex_cfg" "$codex_cfg.backup-$(date +%s)"
            {
                echo ""
                echo "[mcp_servers.phantomstrike]"
                echo "command = \"$mcp_bin\""
                echo "args = [\"--mode\", \"local\"]"
            } >> "$codex_cfg"
            ok "Updated config.toml (Codex)"
            written="yes"
        fi
    fi

    if [ "$written" = "no" ]; then
        warn "No AI agent detected on this machine."
        info "PhantomStrike works with any MCP-compatible agent. Install one"
        info "(Cursor, Codex, Gemini CLI, Claude Desktop), then add:"
        echo -e "${DIM}    $snippet${N}"
        info "Codex uses TOML instead — see the README."
    fi
}

# ── Summary ──────────────────────────────────────────────────────────

print_summary() {
    local found=0 missing=0
    for t in $TOOLS; do
        command -v "$t" >/dev/null 2>&1 && found=$((found+1)) || missing=$((missing+1))
    done

    echo ""
    echo -e "${G}${B}  ==============================================${N}"
    echo -e "${G}${B}   Setup complete${N}"
    echo -e "${G}${B}  ==============================================${N}"
    echo ""
    echo -e "  Installed at    ${B}$INSTALL_DIR${N}"
    echo -e "  Security tools  ${B}$found available${N}${DIM}, $missing missing${N}"
    echo -e "  API key         ${B}saved in .env${N}"
    echo ""
    echo -e "${B}  What to do now${N}"
    echo ""
    echo -e "  ${C}1.${N} Restart your AI agent so it picks up the new config"
    echo -e "  ${C}2.${N} Ask it: ${DIM}\"List all available PhantomStrike tools\"${N}"
    echo ""
    echo -e "${B}  Next time you reboot${N}"
    echo ""
    echo -e "  ${DIM}Do not reinstall. Just run:${N}"
    echo -e "     ${B}cd $INSTALL_DIR && ./start.sh status${N}"
    echo ""
    echo -e "  ${DIM}For Claude Desktop setups, also start the bridge:${N}"
    echo -e "     ${B}./start.sh proxy${N}"
    echo ""
    echo -e "${B}  Before scanning anything${N}"
    echo ""
    echo -e "  Limit what can be targeted by copying ${B}engagement.example.yaml${N}"
    echo -e "  to ${B}engagement.yaml${N} and listing only hosts you are authorised"
    echo -e "  to test. See SECURITY.md."
    echo ""
}

# ── Run ──────────────────────────────────────────────────────────────

main() {
    banner
    detect_environment
    check_python
    install_tools
    install_phantomstrike
    setup_api_key
    write_start_script
    configure_agent
    print_summary
}

main "$@"
