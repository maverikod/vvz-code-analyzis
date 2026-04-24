"""
File existence validation (SSL files, database path, etc.).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .result import ValidationResult


def validate_file_existence_impl(
    config_data: Dict[str, Any],
    results: List[ValidationResult],
    config_path: Optional[str],
) -> None:
    """Validate that referenced files exist."""
    if not config_path:
        return

    config_dir = Path(config_path).parent

    server = config_data.get("server", {})
    ssl = server.get("ssl")
    if ssl:
        for field in ["cert", "key", "ca", "crl"]:
            if field in ssl and ssl[field]:
                file_path = Path(ssl[field])
                if not file_path.is_absolute():
                    file_path = config_dir / file_path
                if not file_path.exists():
                    results.append(
                        ValidationResult(
                            level="error",
                            message=f"SSL file not found: {ssl[field]}",
                            section="server",
                            key=f"ssl.{field}",
                            suggestion=f"Ensure file exists at {file_path}",
                        )
                    )

    registration = config_data.get("registration", {})
    if registration.get("enabled"):
        reg_ssl = registration.get("ssl")
        if reg_ssl:
            for field in ["cert", "key", "ca", "crl"]:
                if field in reg_ssl and reg_ssl[field]:
                    file_path = Path(reg_ssl[field])
                    if not file_path.is_absolute():
                        file_path = config_dir / file_path
                    if not file_path.exists():
                        results.append(
                            ValidationResult(
                                level="error",
                                message=f"Registration SSL file not found: {reg_ssl[field]}",
                                section="registration",
                                key=f"ssl.{field}",
                                suggestion=f"Ensure file exists at {file_path}",
                            )
                        )

    code_analysis = config_data.get("code_analysis", {})
    if code_analysis:
        chunker = code_analysis.get("chunker", {})
        if chunker:
            for field in ["cert_file", "key_file", "ca_cert_file", "crl_file"]:
                if field in chunker and chunker[field]:
                    file_path = Path(chunker[field])
                    if not file_path.is_absolute():
                        file_path = config_dir / file_path
                    if not file_path.exists():
                        results.append(
                            ValidationResult(
                                level="error",
                                message=f"Chunker SSL file not found: {chunker[field]}",
                                section="code_analysis",
                                key=f"chunker.{field}",
                                suggestion=f"Ensure file exists at {file_path}",
                            )
                        )

        embedding = code_analysis.get("embedding", {})
        if embedding:
            for field in ["cert_file", "key_file", "ca_cert_file", "crl_file"]:
                if field in embedding and embedding[field]:
                    file_path = Path(embedding[field])
                    if not file_path.is_absolute():
                        file_path = config_dir / file_path
                    if not file_path.exists():
                        results.append(
                            ValidationResult(
                                level="error",
                                message=f"Embedding SSL file not found: {embedding[field]}",
                                section="code_analysis",
                                key=f"embedding.{field}",
                                suggestion=f"Ensure file exists at {file_path}",
                            )
                        )

        database = code_analysis.get("database", {})
        if database:
            driver = database.get("driver", {})
            if driver and isinstance(driver, dict):
                driver_type = driver.get("type")
                if driver_type not in ("sqlite", "sqlite_proxy"):
                    driver_type = None
                driver_config = driver.get("config", {})
                if driver_type and driver_config and isinstance(driver_config, dict):
                    db_path = driver_config.get("path")
                    if db_path and isinstance(db_path, str):
                        file_path = Path(db_path)
                        if not file_path.is_absolute():
                            file_path = config_dir / file_path
                        if file_path.parent.exists() and not file_path.parent.is_dir():
                            results.append(
                                ValidationResult(
                                    level="error",
                                    message=f"Database path parent is not a directory: {db_path}",
                                    section="code_analysis",
                                    key="database.driver.config.path",
                                    suggestion=f"Ensure parent directory exists and is a directory: {file_path.parent}",
                                )
                            )
                        elif not file_path.parent.exists():
                            results.append(
                                ValidationResult(
                                    level="warning",
                                    message=f"Database path parent directory does not exist: {file_path.parent}",
                                    section="code_analysis",
                                    key="database.driver.config.path",
                                    suggestion=f"Parent directory will be created automatically: {file_path.parent}",
                                )
                            )
