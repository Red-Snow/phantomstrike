#!/usr/bin/env bash
# ==============================================================================
#  PhantomStrike — Automatic Setup
#
#  Two roles, because two very different machines run this:
#
#    All-in-one   Tools AND the AI agent on the same box (Kali / Parrot).
#                 ./setup.sh
#
#    Client       The AI agent is here; the tools are on another machine
#                 (a Kali/Parrot VM, or Docker). Typical on a Mac or Windows
#                 host running Claude Desktop.
#                 ./setup.sh --client --server http://<vm-ip>:8443
#
#  From the internet:
#      curl -sSL https://raw.githubusercontent.com/Red-Snow/phantomstrike/main/setup.sh | bash
#      curl -sSL .../setup.sh | bash -s -- --client --server http://192.168.72.128:8443
#
#  Safe to re-run. It skips work that is already done rather than reinstalling.
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

usage() {
cat <<'EOF'
  Usage: ./setup.sh [options]

    (no options)      All-in-one: tools and agent on this machine.
                      The right choice on Kali or Parrot.

    --client          Client only: the AI agent is here, the tools are on
                      another machine. The right choice on a Mac or Windows
                      host talking to a Kali/Parrot VM.

    --server <url>    Where the tools are, e.g. http://192.168.72.128:8443
                      (client mode only)

    --api-key <key>   The key the server was started with. Must match exactly.
                      (client mode only)

    -h, --help        Show this.

  Examples:
    ./setup.sh
    ./setup.sh --client --server http://192.168.72.128:8443 --api-key abc123

EOF
exit 0
}

# ── Options ──────────────────────────────────────────────────────────

ROLE=""                 # allinone | client
REMOTE_URL=""
PROVIDED_KEY=""

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --client)        ROLE="client" ;;
            --all-in-one)    ROLE="allinone" ;;
            --server)        REMOTE_URL="${2:-}"; shift ;;
            --server=*)      REMOTE_URL="${1#*=}" ;;
            --api-key)       PROVIDED_KEY="${2:-}"; shift ;;
            --api-key=*)     PROVIDED_KEY="${1#*=}" ;;
            -h|--help)       usage ;;
            *)               fail "Unknown option: $1 (try --help)" ;;
        esac
        shift
    done
}

# ── Environment detection ────────────────────────────────────────────────

OS=""           # linux | macos
DISTRO=""       # kali | parrot | debian | ubuntu | fedora | arch | macos | unknown
PKG=""          # apt | dnf | pacman | brew
IS_WSL="no"
SUDO=""

detect_environment() {
    step "Checking your system"

    case "$(uname -s)" in
        Linux*)  OS="linux" ;;
        Darwin*) OS="macos" ;;
        *)       fail "Unsupported system: $(uname -s). Windows users should run setup.ps1 instead." ;;
    esac

    if [ "$OS" = "linux" ]; then
        grep -qi microsoft /proc/version 2>/dev/null && IS_WSL="yes"

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

    if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi

    local label="$DISTRO"
    [ "$IS_WSL" = "yes" ] && label="$label (WSL2)"
    ok "Detected: ${B}${label}${N}"
}

# ── Role ─────────────────────────────────────────────────────────────

decide_role() {
    if [ -n "$ROLE" ]; then
        ok "Mode: ${B}${ROLE}${N} (from command line)"
        return
    fi

    # Kali and Parrot are pentest distros: the tools are already here, so
    # all-in-one is almost always what is wanted.
    if [ "$DISTRO" = "kali" ] || [ "$DISTRO" = "parrot" ]; then
        ROLE="allinone"
        ok "Mode: ${B}all-in-one${N} (tools and agent both on this machine)"
        return
    fi

    # macOS cannot run the Linux security tools at all, so a Mac is nearly
    # always the client half of a split setup.
    if [ "$OS" = "macos" ]; then
        ROLE="client"
        ok "Mode: ${B}client${N} (macOS can't run the Linux tools, so they live elsewhere)"
        info "Override with --all-in-one if that is wrong."
        return
    fi

    ROLE="allinone"
    ok "Mode: ${B}all-in-one${N}"
    info "Running the AI agent here but the tools elsewhere? Re-run with --client."
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
        fail "Python 3.10+ required, found $version."
    fi
    ok "Python $version"

    if [ "$PKG" = "apt" ] && ! python3 -c 'import venv' >/dev/null 2>&1; then
        info "Installing python3-venv…"
        $SUDO apt-get install -y -qq python3-venv >/dev/null 2>&1 || fail "Could not install python3-venv"
        ok "python3-venv installed"
    fi
}

# ── Security tools ─────────────────────────────────────────────────────

TOOLS="nmap masscan amass hydra ffuf gobuster nikto nuclei sqlmap subfinder"

install_tools() {
    # In client mode the tools belong on the other machine. Installing them
    # here would take a long time and change nothing about how it works.
    if [ "$ROLE" = "client" ]; then
        step "Security tools"
        ok "Skipped — they run on your Kali/Parrot box, not here"
        return
    fi

    step "Installing security tools"

    local missing=""
    for t in $TOOLS; do
        command -v "$t" >/dev/null 2>&1 || missing="$missing $t"
    done

    if [ -z "$missing" ]; then
        ok "All tools already present"
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

# ── Configuration ─────────────────────────────────────────────────────

API_KEY=""

setup_config() {
    step "Setting up configuration"

    if [ "$ROLE" = "client" ]; then
        # The server owns the key. Generating one here would produce a
        # mismatch, and every tool call would come back 401.
        if [ -f ".env" ] && grep -q "^PHANTOMSTRIKE_API_KEY=" .env; then
            ok "Existing config found in .env — keeping it"
            return
        fi

        API_KEY="$PROVIDED_KEY"
        if [ -z "$API_KEY" ] && [ -t 0 ]; then
            echo -en "  ${B}?${N} API key from your Kali/Parrot box (blank to fill in later): "
            read -r API_KEY || true
        fi
        if [ -z "$REMOTE_URL" ] && [ -t 0 ]; then
            echo -en "  ${B}?${N} Server URL, e.g. http://192.168.72.128:8443 : "
            read -r REMOTE_URL || true
        fi
        [ -n "$REMOTE_URL" ] || REMOTE_URL="http://CHANGE-ME:8443"

        {
            echo "# PhantomStrike client configuration — generated by setup.sh"
            echo "# This machine runs the AI agent. The tools run on the server below."
            echo ""
            echo "# Must match PHANTOMSTRIKE_API_KEYS on that server, exactly."
            echo "PHANTOMSTRIKE_API_KEY=${API_KEY:-CHANGE_ME_key_from_your_server}"
            echo "PHANTOMSTRIKE_REMOTE=$REMOTE_URL"
        } > .env

        if [ -z "$API_KEY" ] || [ "$REMOTE_URL" = "http://CHANGE-ME:8443" ]; then
            warn "Config incomplete — edit .env before starting"
            info "You need the API key and the IP from your Kali/Parrot box."
        else
            ok "Client config written to .env"
        fi
        return
    fi

    # All-in-one: this machine runs the server, so it owns the key.
    if [ -f ".env" ] && grep -q "^PHANTOMSTRIKE_API_KEYS=" .env; then
        API_KEY=$(grep "^PHANTOMSTRIKE_API_KEYS=" .env | head -1 | cut -d= -f2- | tr -d '"')
        ok "Existing key found in .env — keeping it"
        return
    fi

    API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    {
        echo "# PhantomStrike configuration — generated by setup.sh"
        echo "# This file contains a secret. Do not commit it."
        echo "PHANTOMSTRIKE_API_KEYS=$API_KEY"
        echo "PHANTOMSTRIKE_ENFORCE_SCOPE=true"
        echo "PHANTOMSTRIKE_ALLOW_RAW_SHELL=true"
    } >> .env
    ok "Key generated and saved to .env"
    info "Your client machine needs this exact key. Show it later with:"
    info "  grep API_KEYS .env"
}

# ── Start script ─────────────────────────────────────────────────────
#
# The point of this: after a reboot, people were reinstalling from scratch
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
#      ./start.sh              start the right piece for this machine
#      ./start.sh server       start the API server (the machine with the tools)
#      ./start.sh proxy        start the bridge (the machine with the AI agent)
#      ./start.sh status       check what is running and reachable
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
fi

# A client install has PHANTOMSTRIKE_REMOTE; a server install has API_KEYS.
if [ -n "${PHANTOMSTRIKE_REMOTE:-}" ]; then DEFAULT_MODE="proxy"; else DEFAULT_MODE="server"; fi
MODE="${1:-$DEFAULT_MODE}"

case "$MODE" in
  server)
    if [ -z "${PHANTOMSTRIKE_API_KEYS:-}" ]; then
        echo -e "${Y}No PHANTOMSTRIKE_API_KEYS set — the server will refuse to start.${N}"
        echo -e "${Y}This looks like a client install. Did you mean: ./start.sh proxy${N}"
        echo ""
    fi
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
    REMOTE="${2:-${PHANTOMSTRIKE_REMOTE:-http://localhost:8443}}"
    export PHANTOMSTRIKE_API_KEY="${PHANTOMSTRIKE_API_KEY:-${PHANTOMSTRIKE_API_KEYS:-}}"
    if [ -z "$PHANTOMSTRIKE_API_KEY" ] || [ "$PHANTOMSTRIKE_API_KEY" = "CHANGE_ME_key_from_your_server" ]; then
        echo -e "${R}No API key set.${N}"
        echo -e "Edit .env and set PHANTOMSTRIKE_API_KEY to the same value your"
        echo -e "server was started with (PHANTOMSTRIKE_API_KEYS over there)."
        exit 1
    fi
    case "$REMOTE" in
      *CHANGE-ME*)
        echo -e "${R}Server URL not set.${N}"
        echo -e "Edit .env and set PHANTOMSTRIKE_REMOTE to your Kali/Parrot box,"
        echo -e "e.g. http://192.168.72.128:8443"
        exit 1 ;;
    esac
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
    TARGET="${PHANTOMSTRIKE_REMOTE:-http://localhost:8443}"
    if curl -sf "$TARGET/health" >/dev/null 2>&1; then
        echo -e "  ${G}✓${N} API server reachable at $TARGET"
    else
        echo -e "  ${Y}·${N} API server NOT reachable at $TARGET"
        if [ -n "${PHANTOMSTRIKE_REMOTE:-}" ]; then
            echo -e "      Start it on that machine: ${B}./start.sh server${N}"
            echo -e "      Then check the IP and that port 8443 is open."
        else
            echo -e "      Start it here: ${B}./start.sh server${N}"
        fi
    fi
    if [ -S /tmp/phantomstrike_proxy.sock ]; then
        echo -e "  ${G}✓${N} Proxy daemon is running"
    else
        echo -e "  ${Y}·${N} Proxy daemon not running → ${B}./start.sh proxy${N}"
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

    # local  = run the tools right here.
    # remote = send them to the server; the proxy daemon carries the request.
    local mcp_mode="local"
    [ "$ROLE" = "client" ] && mcp_mode="remote"

    local mcp_bin="$INSTALL_DIR/.venv/bin/phantomstrike-mcp"
    local snippet="{\"mcpServers\":{\"phantomstrike\":{\"command\":\"$mcp_bin\",\"args\":[\"--mode\",\"$mcp_mode\"]}}}"

    local claude_cfg cursor_cfg gemini_cfg written="no"
    if [ "$OS" = "macos" ]; then
        claude_cfg="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    else
        claude_cfg="$HOME/.config/Claude/claude_desktop_config.json"
    fi
    cursor_cfg="$HOME/.cursor/mcp.json"
    gemini_cfg="$HOME/.gemini/settings.json"

    for cfg in "$claude_cfg" "$cursor_cfg" "$gemini_cfg"; do
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
            warn "$(basename "$cfg") already has other MCP servers in it."
            info "Backed it up. Add this entry to \"mcpServers\" yourself:"
            echo -e "${DIM}    \"phantomstrike\": {\"command\": \"$mcp_bin\", \"args\": [\"--mode\", \"$mcp_mode\"]}${N}"
        else
            echo "$snippet" > "$cfg"
            ok "Wrote $(basename "$cfg") ${DIM}(--mode $mcp_mode)${N}"
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
                echo "args = [\"--mode\", \"$mcp_mode\"]"
            } >> "$codex_cfg"
            ok "Updated config.toml (Codex)"
            written="yes"
        fi
    fi

    if [ "$written" = "no" ]; then
        warn "No AI agent detected on this machine."
        info "PhantomStrike works with any MCP-compatible agent. Install one"
        info "(Claude Desktop, Cursor, Codex, Gemini CLI), then add:"
        echo -e "${DIM}    $snippet${N}"
    fi
}

# ── Summary ──────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo -e "${G}${B}  ==============================================${N}"
    echo -e "${G}${B}   Setup complete${N}"
    echo -e "${G}${B}  ==============================================${N}"
    echo ""
    echo -e "  Installed at  ${B}$INSTALL_DIR${N}"
    echo -e "  Mode          ${B}$ROLE${N}"
    echo ""

    if [ "$ROLE" = "client" ]; then
        echo -e "${B}  This machine runs the AI agent. The tools run elsewhere.${N}"
        echo ""
        echo -e "${B}  What to do now${N}"
        echo ""
        echo -e "  ${C}1.${N} On your Kali/Parrot box, start the server:"
        echo -e "        ${DIM}cd phantomstrike && ./start.sh server${N}"
        echo -e "  ${C}2.${N} Back here, start the bridge and leave it open:"
        echo -e "        ${B}cd $INSTALL_DIR && ./start.sh proxy${N}"
        echo -e "  ${C}3.${N} Quit your AI agent completely, then reopen it"
        echo -e "  ${C}4.${N} Ask it: ${DIM}\"List all available PhantomStrike tools\"${N}"
        echo ""
        echo -e "${B}  Check before you start${N}"
        echo ""
        echo -e "     ${B}./start.sh status${N}   ${DIM}— says whether the server is reachable${N}"
        echo ""
        echo -e "${B}  Next time you reboot${N}"
        echo ""
        echo -e "  ${DIM}Do not reinstall. Start the server on the VM, then here:${N}"
        echo -e "     ${B}cd $INSTALL_DIR && ./start.sh proxy${N}"
    else
        local found=0
        for t in $TOOLS; do
            command -v "$t" >/dev/null 2>&1 && found=$((found+1))
        done
        echo -e "  Tools found   ${B}$found${N}${DIM} of 10 core tools${N}"
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
    fi

    echo ""
    echo -e "${B}  Before scanning anything${N}"
    echo ""
    echo -e "  Limit what can be targeted by copying ${B}engagement.example.yaml${N}"
    echo -e "  to ${B}engagement.yaml${N} on the machine running the server, listing"
    echo -e "  only hosts you are authorised to test. See SECURITY.md."
    echo ""
}

# ── Run ──────────────────────────────────────────────────────────────

main() {
    parse_args "$@"
    banner
    detect_environment
    decide_role
    check_python
    install_tools
    install_phantomstrike
    setup_config
    write_start_script
    configure_agent
    print_summary
}

main "$@"
