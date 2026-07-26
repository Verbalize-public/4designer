"""Entry point: python -m fourdesigner_daemon

Single-instance: if :PORT is already bound, exit 1 with a logged reason (bind-or-exit).
"""

from __future__ import annotations

import logging
import socket
import sys

import uvicorn

from . import PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("fourdesigner.main")

# Non-zero: another daemon owns the port (or bind raced). Scripts/check can detect this.
PORT_IN_USE_EXIT = 1


def _port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main() -> None:
    if not _port_available("0.0.0.0", PORT):
        log.error(
            "port %s in use — exiting %s (another 4designer daemon?)",
            PORT,
            PORT_IN_USE_EXIT,
        )
        sys.exit(PORT_IN_USE_EXIT)
    try:
        uvicorn.run(
            "fourdesigner_daemon.app:app",
            host="0.0.0.0",
            port=PORT,
            log_level="info",
        )
    except OSError as e:
        err = str(e).lower()
        if "address already in use" in err or getattr(e, "winerror", None) == 10048:
            log.error("port %s in use — exiting %s", PORT, PORT_IN_USE_EXIT)
            sys.exit(PORT_IN_USE_EXIT)
        raise


if __name__ == "__main__":
    main()
