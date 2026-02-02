"""
Configuration generator for code-analysis-server.

Based on mcp-proxy-adapter SimpleConfigGenerator with code_analysis specific extensions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from typing import Any, Dict, Optional

from mcp_proxy_adapter.core.config.simple_config_generator import SimpleConfigGenerator


class CodeAnalysisConfigGenerator(SimpleConfigGenerator):
    """
    Configuration generator for code-analysis-server.

    Extends SimpleConfigGenerator from mcp-proxy-adapter with code_analysis
    specific configuration sections (database.driver, code_analysis, etc.).
    """

    def generate(
        self,
        protocol: str,
        with_proxy: bool = False,
        out_path: str = "config.json",
        # Server parameters (from SimpleConfigGenerator)
        server_host: Optional[str] = None,
        server_port: Optional[int] = None,
        server_cert_file: Optional[str] = None,
        server_key_file: Optional[str] = None,
        server_ca_cert_file: Optional[str] = None,
        server_crl_file: Optional[str] = None,
        server_debug: Optional[bool] = None,
        server_log_level: Optional[str] = None,
        server_log_dir: Optional[str] = None,
        # Registration parameters (from SimpleConfigGenerator)
        registration_host: Optional[str] = None,
        registration_port: Optional[int] = None,
        registration_protocol: Optional[str] = None,
        registration_cert_file: Optional[str] = None,
        registration_key_file: Optional[str] = None,
        registration_ca_cert_file: Optional[str] = None,
        registration_crl_file: Optional[str] = None,
        registration_server_id: Optional[str] = None,
        registration_server_name: Optional[str] = None,
        instance_uuid: Optional[str] = None,
        # Queue manager parameters (from SimpleConfigGenerator)
        queue_enabled: Optional[bool] = None,
        queue_in_memory: Optional[bool] = None,
        queue_max_concurrent: Optional[int] = None,
        queue_retention_seconds: Optional[int] = None,
        # Code analysis specific parameters
        code_analysis_db_path: Optional[str] = None,
        code_analysis_driver_type: Optional[str] = None,
        code_analysis_driver_path: Optional[str] = None,
    ) -> str:
        """
        Generate configuration file for code-analysis-server.

        Args:
            protocol: Server protocol (http, https, mtls)
            with_proxy: Enable proxy registration (default: False)
            out_path: Output file path (default: config.json)
            server_host: Server host
            server_port: Server port
            server_cert_file: Server certificate file
            server_key_file: Server key file
            server_ca_cert_file: Server CA certificate file
            server_crl_file: Server CRL file
            server_debug: Enable debug mode
            server_log_level: Log level
            server_log_dir: Log directory
            registration_host: Registration proxy host
            registration_port: Registration proxy port
            registration_protocol: Registration protocol
            registration_cert_file: Registration certificate file
            registration_key_file: Registration key file
            registration_ca_cert_file: Registration CA certificate file
            registration_crl_file: Registration CRL file
            registration_server_id: Server ID for registration
            registration_server_name: Server name
            instance_uuid: Server instance UUID
            queue_enabled: Enable queue manager
            queue_in_memory: Use in-memory queue
            queue_max_concurrent: Maximum concurrent jobs
            queue_retention_seconds: Completed job retention in seconds
            code_analysis_db_path: Database path for code_analysis section
            code_analysis_driver_type: Driver type (sqlite, sqlite_proxy, etc.)
            code_analysis_driver_path: Driver database path

        Returns:
            Path to generated configuration file
        """
        # Generate base config using SimpleConfigGenerator
        base_config_path = super().generate(
            protocol=protocol,
            with_proxy=with_proxy,
            out_path=out_path,
            server_host=server_host,
            server_port=server_port,
            server_cert_file=server_cert_file,
            server_key_file=server_key_file,
            server_ca_cert_file=server_ca_cert_file,
            server_crl_file=server_crl_file,
            server_debug=server_debug,
            server_log_level=server_log_level,
            server_log_dir=server_log_dir,
            registration_host=registration_host,
            registration_port=registration_port,
            registration_protocol=registration_protocol,
            registration_cert_file=registration_cert_file,
            registration_key_file=registration_key_file,
            registration_ca_cert_file=registration_ca_cert_file,
            registration_crl_file=registration_crl_file,
            registration_server_id=registration_server_id,
            registration_server_name=registration_server_name,
            instance_uuid=instance_uuid,
        )

        # Load generated config
        with open(base_config_path, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)

        # Add code_analysis section
        if "code_analysis" not in config:
            config["code_analysis"] = {}

        # Set database path
        db_path = code_analysis_db_path or "data/code_analysis.db"
        config["code_analysis"]["db_path"] = db_path

        # Add database.driver section if driver type is specified
        driver_type = code_analysis_driver_type or "sqlite_proxy"
        driver_path = code_analysis_driver_path or db_path

        if "database" not in config["code_analysis"]:
            config["code_analysis"]["database"] = {}

        config["code_analysis"]["database"]["driver"] = {
            "type": driver_type,
            "config": {
                "path": driver_path,
            },
        }

        # Add worker_config for sqlite_proxy
        if driver_type == "sqlite_proxy":
            config["code_analysis"]["database"]["driver"]["config"]["worker_config"] = {
                "command_timeout": 30.0,
                "poll_interval": 0.01,
            }

        # Add default code_analysis settings if not present
        if "host" not in config["code_analysis"]:
            config["code_analysis"]["host"] = server_host or "0.0.0.0"
        if "port" not in config["code_analysis"]:
            config["code_analysis"]["port"] = server_port or 15000
        if "log" not in config["code_analysis"]:
            config["code_analysis"]["log"] = "logs/code_analysis.log"
        if "faiss_index_path" not in config["code_analysis"]:
            config["code_analysis"]["faiss_index_path"] = "data/faiss_index.bin"
        if "vector_dim" not in config["code_analysis"]:
            config["code_analysis"]["vector_dim"] = 384
        if "min_chunk_length" not in config["code_analysis"]:
            config["code_analysis"]["min_chunk_length"] = 30

        # Save updated config
        with open(base_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return base_config_path
