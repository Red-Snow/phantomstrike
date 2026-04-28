"""
PhantomStrike Logging — structured, colored, and professional.

Uses Python's `rich` library for beautiful terminal output.
"""

import logging
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# ── Custom theme ──────────────────────────────────────────────────────────────
PHANTOM_THEME = Theme(
    {
        "info": "cyan",
        "warning": "bold yellow",
        "error": "bold red",
        "critical": "bold white on red",
        "success": "bold green",
        "tool": "bold magenta",
        "target": "bold bright_white",
        "dim": "dim white",
        "banner": "bold bright_red",
    }
)

console = Console(theme=PHANTOM_THEME, stderr=True)

# ── Banner ────────────────────────────────────────────────────────────────────
BANNER = r"""[banner]
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
 ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝[/banner]
[dim]  AI-Powered MCP Cybersecurity Framework — v1.0.0
  Modular • Secure • Extensible[/dim]
"""


def print_banner() -> None:
    """Display the startup banner."""
    console.print(BANNER)


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    Configure the root logger with Rich handler.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional file path for persistent logging.

    Returns:
        Configured root logger.
    """
    handlers: list[logging.Handler] = [
        RichHandler(
            console=console,
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
            markup=True,
        )
    ]

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return logging.getLogger("phantomstrike")


def get_logger(name: str) -> logging.Logger:
    """Get a child logger scoped to a module."""
    return logging.getLogger(f"phantomstrike.{name}")
