"""
Configuration generator for code-analysis-server.

Generates configuration files compatible with mcp-proxy-adapter format.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from pathlib import Path
from typing import Optional


class CodeAnalysisConfigGenerator:
    """Generate configuration for code-analysis-server."""

    def generate(
        self,
        protocol: str = "mtls",
        out_path: str = "config.json",
        # Server parameters
        server_host: Optional[str] = None,
        server_port: Optional[int] = None,
        server_cert_file: Optional[str] = None,
        server_key_file: Optional[str] = None,
        server_ca_cert_file: Optional[str] = None,
        server_log_dir: Optional[str] = None,
        # Registration parameters
        registration_host: Optional[str] = None,
        registration_port: Optional[int] = None,
        registration_protocol: Optional[str] = None,
        registration_cert_file: Optional[str] = None,
        registration_key_file: Optional[str] = None,
        registration_ca_cert_file: Optional[str] = None,
        registration_server_id: Optional[str] = None,
        registration_server_name: Optional[str] = None,
        instance_uuid: Optional[str] = None,
        # Queue manager parameters
        queue_enabled: bool = True,
        queue_in_memory: bool = True,
        queue_max_concurrent: int = 5,
        queue_retention_seconds: int = 21600,
    ) -> str:
        """
        Generate configuration file for code-analysis-server.

        Args:
            protocol: Server protocol (http, https, mtls) - default: mtls
            out_path: Output file path - default: config.json
            server_host: Server host - default: 127.0.0.1
            server_port: Server port - default: 15000
            server_cert_file: Server certificate file path
            server_key_file: Server key file path
            server_ca_cert_file: Server CA certificate file path
            server_log_dir: Log directory path - default: ./logs
            registration_host: Registration proxy host - default: localhost
            registration_port: Registration proxy port - default: 3005
            registration_protocol: Registration protocol - default: mtls
            registration_cert_file: Registration certificate file path
            registration_key_file: Registration key file path
            registration_ca_cert_file: Registration CA certificate file path
            registration_server_id: Server ID for registration - default: code-analysis-server
            registration_server_name: Server name - default: Code Analysis Server
            instance_uuid: Server instance UUID (UUID4, auto-generated if not provided)
            queue_enabled: Enable queue manager - default: True
            queue_in_memory: Use in-memory queue - default: True
            queue_max_concurrent: Maximum concurrent jobs - default: 5
            queue_retention_seconds: Completed job retention in seconds - default: 21600

        Returns:
            Path to generated configuration file
        """
        import os
        import socket
        import subprocess

        # Get host IP address in smart-assistant Docker network
        # Priority: Environment variable > Docker network gateway > Host IP
        docker_host_ip = os.getenv("DOCKER_HOST_IP") or os.getenv(
            "SMART_ASSISTANT_HOST_IP"
        )

        if not docker_host_ip:
            # Try to get gateway IP from smart-assistant network
            # Gateway IP is the host IP address in Docker network
            try:
                result = subprocess.run(
                    ["docker", "network", "inspect", "smart-assistant"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    import json

                    network_info = json.loads(result.stdout)
                    if network_info and len(network_info) > 0:
                        ipam = network_info[0].get("IPAM", {})
                        configs = ipam.get("Config", [])
                        if configs and len(configs) > 0:
                            gateway = configs[0].get("Gateway")
                            if gateway:
                                docker_host_ip = gateway
            except Exception:
                pass

        if not docker_host_ip:
            # Fallback: try to get host IP address
            try:
                # Get hostname
                hostname = socket.gethostname()
                # Get IP address
                docker_host_ip = socket.gethostbyname(hostname)
            except Exception:
                # Fallback: try to get from hostname -I
                try:
                    result = subprocess.run(
                        ["hostname", "-I"], capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        docker_host_ip = result.stdout.strip().split()[0]
                except Exception:
                    pass

        # Default to 0.0.0.0 if we can't determine host IP
        # This allows server to listen on all interfaces
        server_host_val = server_host or "0.0.0.0"
        server_port_val = server_port or 15000
        server_servername = "code-analysis-server"
        # Use host IP in Docker network for advertised_host so proxy in container can reach it
        # If docker_host_ip is not available, use servername as fallback
        if server_host_val != "0.0.0.0":
            server_advertised_host = server_host_val
        else:
            server_advertised_host = docker_host_ip or server_servername

        # Create SSL config if needed
        server_ssl = None
        if protocol in ("https", "mtls"):
            if protocol == "mtls" and not server_ca_cert_file:
                raise ValueError(
                    "CA certificate is required for mTLS protocol. "
                    "Provide server_ca_cert_file parameter."
                )

            server_ssl = {
                "cert": server_cert_file
                or "mtls_certificates/mtls_certificates/server/code-analysis-server.crt",
                "key": server_key_file
                or "mtls_certificates/mtls_certificates/server/code-analysis-server.key",
                "ca": server_ca_cert_file
                or "mtls_certificates/mtls_certificates/ca/ca.crt",
                "crl": None,
                "dnscheck": False,
                "check_hostname": False,
            }

        server_config = {
            "host": server_host_val,
            "port": server_port_val,
            "protocol": protocol,
            "servername": server_servername,
            "advertised_host": (
                server_advertised_host if server_advertised_host else server_servername
            ),
            "debug": False,
            "log_level": "INFO",
            "ssl": server_ssl,
            "log_dir": server_log_dir or "./logs",
        }

        # Client configuration (disabled)
        client_config = {
            "enabled": False,
            "protocol": protocol,
            "ssl": None,
        }

        # Registration configuration
        # Use host IP in smart-assistant network for registration
        # Proxy in container needs to reach the server
        reg_host = registration_host or docker_host_ip or "localhost"
        reg_port = registration_port or 3005
        reg_protocol = registration_protocol or "mtls"

        # Generate instance_uuid if not provided
        if instance_uuid is None:
            instance_uuid = str(uuid.uuid4())
        else:
            # Validate provided UUID
            try:
                uuid_obj = uuid.UUID(instance_uuid)
                if uuid_obj.version != 4:
                    raise ValueError(
                        f"instance_uuid must be UUID4, got UUID version {uuid_obj.version}"
                    )
            except ValueError as e:
                raise ValueError(f"Invalid instance_uuid format: {str(e)}")

        # Determine URL scheme based on protocol
        scheme = "https" if reg_protocol in ("https", "mtls") else "http"

        # Create full URLs for registration and heartbeat
        register_url = f"{scheme}://{reg_host}:{reg_port}/register"
        unregister_url = f"{scheme}://{reg_host}:{reg_port}/unregister"
        heartbeat_url = f"{scheme}://{reg_host}:{reg_port}/proxy/heartbeat"

        # Create SSL config for registration if needed
        registration_ssl = None
        if reg_protocol in ("https", "mtls"):
            registration_ssl = {
                "cert": registration_cert_file
                or "mtls_certificates/mtls_certificates/client/code-analysis.crt",
                "key": registration_key_file
                or "mtls_certificates/mtls_certificates/client/code-analysis.key",
                "ca": registration_ca_cert_file
                or "mtls_certificates/mtls_certificates/ca/ca.crt",
                "crl": None,
                "dnscheck": False,
                "check_hostname": False,
            }

        registration_config = {
            "enabled": True,
            "protocol": reg_protocol,
            "register_url": register_url,
            "unregister_url": unregister_url,
            "heartbeat_interval": 30,
            "server_id": registration_server_id or "code-analysis-server",
            "server_name": registration_server_name or "Code Analysis Server",
            "instance_uuid": instance_uuid,
            "auto_on_startup": True,
            "auto_on_shutdown": True,
            "ssl": registration_ssl,
            "heartbeat": {
                "url": heartbeat_url,
                "interval": 30,
            },
        }

        # Server validation (disabled by default)
        server_validation_config = {
            "enabled": False,
            "protocol": protocol,
            "timeout": 10,
            "use_token": False,
            "use_roles": False,
            "tokens": {},
            "roles": {},
            "auth_header": "X-API-Key",
            "roles_header": "X-Roles",
            "health_path": "/health",
            "check_hostname": False,
            "ssl": server_ssl,
        }

        # Auth configuration
        auth_config = {
            "use_token": False,
            "use_roles": False,
            "tokens": {},
            "roles": {},
        }

        # Queue manager configuration
        queue_manager_config = {
            "enabled": queue_enabled,
            "in_memory": queue_in_memory,
            "registry_path": None,
            "shutdown_timeout": 30.0,
            "max_concurrent_jobs": queue_max_concurrent,
            "max_queue_size": None,
            "per_job_type_limits": None,
            "completed_job_retention_seconds": queue_retention_seconds,
        }

        # Transport configuration
        transport_config = {
            "type": "https" if protocol in ("https", "mtls") else "http",
            "verify_client": protocol == "mtls",
            "chk_hostname": False,
        }

        # Code analysis configuration
        code_analysis_config = {
            "host": server_host_val,
            "port": server_port_val,
            "log": f"{server_log_dir or './logs'}/code_analysis.log",
            "db_path": "data/code_analysis.db",
            "dirs": [],
            "chunker": {
                "enabled": True,
                "url": "localhost",
                "port": 8009,
                "protocol": protocol,
                "cert_file": server_cert_file
                or "mtls_certificates/mtls_certificates/client/code-analysis.crt",
                "key_file": server_key_file
                or "mtls_certificates/mtls_certificates/client/code-analysis.key",
                "ca_cert_file": server_ca_cert_file
                or "mtls_certificates/mtls_certificates/ca/ca.crt",
                "crl_file": None,
                "retry_attempts": 3,
                "retry_delay": 5.0,
                "timeout": 60.0,
            },
            "embedding": {
                "enabled": True,
                "host": "localhost",
                "port": 8001,
                "protocol": protocol,
                "cert_file": server_cert_file
                or "mtls_certificates/mtls_certificates/client/code-analysis.crt",
                "key_file": server_key_file
                or "mtls_certificates/mtls_certificates/client/code-analysis.key",
                "ca_cert_file": server_ca_cert_file
                or "mtls_certificates/mtls_certificates/ca/ca.crt",
                "crl_file": None,
                "retry_attempts": 3,
                "retry_delay": 5.0,
                "timeout": 60.0,
            },
            "faiss_index_path": "data/faiss_index.bin",
            "vector_dim": 384,
            "min_chunk_length": 30,
            "vectorization_retry_attempts": 3,
            "vectorization_retry_delay": 10.0,
            "worker": {
                "enabled": True,
                "poll_interval": 30,
                "batch_size": 10,
                "retry_attempts": 3,
                "retry_delay": 10.0,
                "watch_dirs": [],
                "dynamic_watch_file": "data/dynamic_watch_dirs.json",
                "log_path": "logs/vectorization_worker.log",
                "circuit_breaker": {
                    "failure_threshold": 5,
                    "recovery_timeout": 60.0,
                    "success_threshold": 2,
                    "initial_backoff": 5.0,
                    "max_backoff": 300.0,
                    "backoff_multiplier": 2.0,
                },
                "batch_processor": {
                    "max_empty_iterations": 3,
                    "empty_delay": 5.0,
                },
            },
        }

        # Complete configuration
        config = {
            "server": server_config,
            "client": client_config,
            "registration": registration_config,
            "server_validation": server_validation_config,
            "auth": auth_config,
            "queue_manager": queue_manager_config,
            "transport": transport_config,
            "code_analysis": code_analysis_config,
        }

        # Save configuration
        out_path_obj = Path(out_path)
        out_path_obj.parent.mkdir(parents=True, exist_ok=True)
        import json

        with open(out_path_obj, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Validate generated configuration
        from .config_validator import CodeAnalysisConfigValidator

        validator = CodeAnalysisConfigValidator(str(out_path_obj))
        validator.load_config()
        validation_results = validator.validate_config()
        summary = validator.get_validation_summary()

        if not summary["is_valid"]:
            errors = [
                r.message for r in validation_results if r.level == "error"
            ]
            raise ValueError(
                f"Generated configuration is invalid: {'; '.join(errors)}"
            )

        return str(out_path_obj.resolve())
