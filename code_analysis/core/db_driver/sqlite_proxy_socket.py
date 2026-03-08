"""
Socket send/receive for SQLite proxy driver (IPC with DB worker).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import socket
import struct
from pathlib import Path
from typing import Any, Dict, cast

from ..exceptions import DatabaseOperationError

logger = logging.getLogger(__name__)


def send_request_via_socket(
    socket_path: str,
    request: Dict[str, Any],
    socket_timeout: float,
    db_path_str: str = "",
) -> Dict[str, Any]:
    """
    Send request to worker via Unix socket and receive response.

    Args:
        socket_path: Path to Unix socket.
        request: Request dict (JSON-serializable).
        socket_timeout: Socket timeout in seconds.
        db_path_str: Database path string for error messages.

    Returns:
        Response dict from worker.

    Raises:
        DatabaseOperationError: If socket missing, timeout, or connection fails.
    """
    socket_file = Path(socket_path)
    if not socket_file.exists():
        raise DatabaseOperationError(
            message=f"Socket file does not exist: {socket_path}",
            operation=request.get("command", "unknown"),
            db_path=db_path_str or None,
        )

    logger.debug("Connecting to socket: %s", socket_path)
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(socket_timeout)
        sock.connect(socket_path)
        logger.debug("Successfully connected to socket")

        data = json.dumps(request).encode("utf-8")
        length = struct.pack("!I", len(data))
        sock.sendall(length + data)

        length_data = b""
        while len(length_data) < 4:
            chunk = sock.recv(4 - len(length_data))
            if not chunk:
                raise DatabaseOperationError(
                    message="Connection closed by worker",
                    operation=request.get("command", "unknown"),
                    db_path=db_path_str or None,
                )
            length_data += chunk

        length = struct.unpack("!I", length_data)[0]
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise DatabaseOperationError(
                    message="Connection closed by worker",
                    operation=request.get("command", "unknown"),
                    db_path=db_path_str or None,
                )
            data += chunk

        return cast(Dict[str, Any], json.loads(data.decode("utf-8")))

    except socket.timeout:
        raise DatabaseOperationError(
            message=f"Socket timeout after {socket_timeout}s",
            operation=request.get("command", "unknown"),
            db_path=db_path_str or None,
        )
    except DatabaseOperationError:
        raise
    except Exception as e:
        raise DatabaseOperationError(
            message=f"Error communicating with worker: {e}",
            operation=request.get("command", "unknown"),
            db_path=db_path_str or None,
            cause=e,
        ) from e
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass
