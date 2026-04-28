"""
PhantomStrike Main — entry point for the API server.
"""

import argparse
import uvicorn

from phantomstrike.config import settings
from phantomstrike.utils.logging import print_banner, setup_logging


def main():
    """Start the PhantomStrike API server."""
    parser = argparse.ArgumentParser(description="PhantomStrike AI Server")
    parser.add_argument("--host", default=settings.server.host, help="Bind address")
    parser.add_argument("--port", type=int, default=settings.server.port, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--log-level", default=settings.logging.level, help="Log level")
    args = parser.parse_args()

    setup_logging(level=args.log_level, log_file=settings.logging.file)
    print_banner()

    uvicorn.run(
        "phantomstrike.server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
