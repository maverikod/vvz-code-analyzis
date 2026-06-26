"""
Database worker: socket send/receive and client connection handler.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
from pathlib import Path
from typing import Any, Dict, Optional, cast

from .runner_execute import execute_operation

logger = logging.getLogger(__name__)


def send_response(sock: socket.socket, response: Dict[str, Any]) -> None:
    """Send JSON response over socket."""
    try:
        data = json.dumps(response).encode("utf-8")
        length = struct.pack("!I", len(data))
        sock.sendall(length + data)
    except Exception as e:
        logger.error(f"Failed to send response: {e}", exc_info=True)


def receive_request(
    sock: socket.socket, timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """Receive JSON request from socket. Returns None if connection closed."""
    try:
        sock.settimeout(timeout)
        length_data = b""
        while len(length_data) < 4:
            chunk = sock.recv(4 - len(length_data))
            if not chunk:
                return None
            length_data += chunk
        length = struct.unpack("!I", length_data)[0]
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        decoded = json.loads(data.decode("utf-8"))
        if not isinstance(decoded, dict):
            logger.error("Received non-object JSON request payload")
            return None
        return cast(Dict[str, Any], decoded)
    except socket.timeout:
        return None
    except Exception as e:
        logger.error(f"Failed to receive request: {e}", exc_info=True)
        return None


def handle_client_connection(
    client_sock: socket.socket,
    db_path: str,
    jobs: Dict[str, Dict[str, Any]],
    jobs_lock: threading.Lock,
    job_timeout: float = 300.0,
) -> None:
    """Handle client connection: receive request, process, send response."""
    try:
        request = receive_request(client_sock, timeout=5.0)
        if not request:
            return

        command = request.get("command")

        if command == "sync_schema":
            params = request.get("params", {})
            schema_definition = params.get("schema_definition")
            backup_dir_str = params.get("backup_dir")
            if not schema_definition:
                send_response(
                    client_sock,
                    {"success": False, "error": "Missing schema_definition"},
                )
                return
            from code_analysis.core.database_driver_pkg.drivers.sqlite import (
                SQLiteDriver,
            )

            driver = SQLiteDriver()
            driver.connect({"path": db_path})
            try:
                backup_dir = Path(backup_dir_str) if backup_dir_str else None
                if not backup_dir:
                    db_path_obj = Path(db_path)
                    if db_path_obj.parent.name == "data":
                        project_root = db_path_obj.parent.parent
                        backup_dir = project_root / "backups"
                    else:
                        backup_dir = db_path_obj.parent / "backups"
                sync_result = driver.sync_schema(schema_definition, backup_dir)
                send_response(
                    client_sock,
                    {"success": True, "result": sync_result},
                )
            except Exception as e:
                logger.error(f"Schema sync failed: {e}", exc_info=True)
                send_response(
                    client_sock,
                    {"success": False, "error": str(e)},
                )
            finally:
                driver.disconnect()

        elif command == "submit":
            job_id = request.get("job_id")
            operation = request.get("operation")
            sql = request.get("sql")
            params = request.get("params")
            table_name = request.get("table_name")
            transaction_id = request.get("transaction_id")
            if not job_id:
                send_response(
                    client_sock,
                    {"success": False, "error": "Missing job_id"},
                )
                return
            if not isinstance(operation, str) or not operation:
                send_response(
                    client_sock,
                    {"success": False, "error": "Missing or invalid operation"},
                )
                return
            logger.debug(
                f"Received job submission: job_id={job_id}, operation={operation}"
            )
            with jobs_lock:
                from datetime import datetime

                jobs[job_id] = {
                    "status": "pending",
                    "operation": operation,
                    "created_at": datetime.now(),
                    "result": None,
                    "error": None,
                }

            def execute_job():
                """Return execute job."""
                try:
                    result = execute_operation(
                        operation=operation,
                        db_path=db_path,
                        sql=sql,
                        params=params,
                        table_name=table_name,
                        transaction_id=transaction_id,
                    )
                    with jobs_lock:
                        if job_id in jobs:
                            jobs[job_id].update(
                                {
                                    "status": "completed",
                                    "result": result.get("result"),
                                    "error": result.get("error"),
                                    "success": result.get("success", False),
                                }
                            )
                except Exception as e:
                    logger.error(f"Error executing job {job_id}: {e}", exc_info=True)
                    with jobs_lock:
                        if job_id in jobs:
                            jobs[job_id].update(
                                {
                                    "status": "failed",
                                    "error": {
                                        "type": type(e).__name__,
                                        "message": str(e),
                                    },
                                    "success": False,
                                }
                            )

            thread = threading.Thread(target=execute_job, daemon=True)
            thread.start()
            send_response(
                client_sock,
                {"success": True, "job_id": job_id},
            )

        elif command == "poll":
            job_id = request.get("job_id")
            if not job_id:
                send_response(
                    client_sock,
                    {"success": False, "error": "Missing job_id"},
                )
                return
            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    send_response(
                        client_sock,
                        {"success": False, "error": "Job not found"},
                    )
                    return
                status = job.get("status")
                if status == "pending":
                    send_response(
                        client_sock,
                        {"success": True, "status": "pending"},
                    )
                elif status in ("completed", "failed"):
                    send_response(
                        client_sock,
                        {
                            "success": job.get("success", False),
                            "status": status,
                            "result": job.get("result"),
                            "error": job.get("error"),
                        },
                    )
                else:
                    send_response(
                        client_sock,
                        {"success": False, "error": f"Unknown job status: {status}"},
                    )

        elif command == "delete":
            job_id = request.get("job_id")
            if not job_id:
                send_response(
                    client_sock,
                    {"success": False, "error": "Missing job_id"},
                )
                return
            with jobs_lock:
                if job_id in jobs:
                    del jobs[job_id]
                    send_response(client_sock, {"success": True})
                else:
                    send_response(
                        client_sock,
                        {"success": False, "error": "Job not found"},
                    )

        else:
            send_response(
                client_sock,
                {"success": False, "error": f"Unknown command: {command}"},
            )

    except Exception as e:
        logger.error(f"Error handling client connection: {e}", exc_info=True)
        try:
            send_response(client_sock, {"success": False, "error": str(e)})
        except Exception:
            pass
    finally:
        try:
            client_sock.close()
        except Exception:
            pass
