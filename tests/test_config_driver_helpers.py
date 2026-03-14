"""
Shared helpers for driver config tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import subprocess
from pathlib import Path

import pytest


def create_dummy_ssl_certs_in_dir(dir_path: Path) -> None:
    """Create minimal valid PEM cert/key in dir_path for file-based validation tests.

    Generates a CA and a server cert signed by that CA so base validator
    (cert chain validation) passes.
    """
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(dir_path / "ca.key"),
                "-out",
                str(dir_path / "ca.crt"),
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=TestCA",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(dir_path / "server.key"),
                "-out",
                str(dir_path / "server.csr"),
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(dir_path / "server.csr"),
                "-CA",
                str(dir_path / "ca.crt"),
                "-CAkey",
                str(dir_path / "ca.key"),
                "-CAcreateserial",
                "-out",
                str(dir_path / "server.crt"),
                "-days",
                "1",
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"openssl not available or failed: {e}")
