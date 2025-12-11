"""
Configuration validator module.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, validator
import os
from pathlib import Path
import json

class Config(BaseModel):
    """Configuration model."""

    # Redis settings
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: Optional[str] = None

    # FAISS settings
    faiss_index_path: str = Field(default="data/faiss_index")
    vector_dimension: int = Field(default=1536)

    # Service settings
    service_host: str = Field(default="0.0.0.0")
    service_port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # Logging settings
    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    @validator("faiss_index_path")
    def validate_faiss_index_path(cls, v: str) -> str:
        """Validate FAISS index path.

        Args:
            v: Path value

        Returns:
            Validated path

        Raises:
            ValueError: If path is invalid
        """
        path = Path(v)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        return str(path)

    @validator("vector_dimension")
    def validate_vector_dimension(cls, v: int) -> int:
        """Validate vector dimension.

        Args:
            v: Dimension value

        Returns:
            Validated dimension

        Raises:
            ValueError: If dimension is invalid
        """
        if v <= 0:
            raise ValueError("Vector dimension must be positive")
        return v

    @validator("service_port")
    def validate_service_port(cls, v: int) -> int:
        """Validate service port.

        Args:
            v: Port value

        Returns:
            Validated port

        Raises:
            ValueError: If port is invalid
        """
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

class ConfigValidator:
    """Configuration validator."""

    @staticmethod
    def validate(config: Dict[str, Any]) -> Config:
        """Validate configuration.

        Args:
            config: Configuration dictionary

        Returns:
            Validated configuration

        Raises:
            ValueError: If configuration is invalid
        """
        return Config(**config)

    @staticmethod
    def validate_file(path: str) -> Config:
        """Validate configuration file.

        Args:
            path: Configuration file path

        Returns:
            Validated configuration

        Raises:
            ValueError: If configuration is invalid
        """
        if not os.path.exists(path):
            raise ValueError(f"Configuration file not found: {path}")

        with open(path) as f:
            config = json.load(f)

        return ConfigValidator.validate(config)
