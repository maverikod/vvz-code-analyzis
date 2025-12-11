"""
BM25 Configuration Module

This module provides configuration settings and constants for BM25 search functionality.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class BM25Config:
    """
    Configuration for BM25 search service.
    
    Attributes:
        k1: BM25 k1 parameter for term frequency saturation (default: 1.2)
        b: BM25 b parameter for length normalization (default: 0.75)
        min_token_length: Minimum token length for indexing (default: 2)
        max_token_length: Maximum token length for indexing (default: 50)
        redis_key_prefix: Redis key prefix for BM25 index storage (default: "bm25:")
        enable_persistence: Whether to persist BM25 index to Redis (default: True)
        enable_stemming: Whether to enable stemming for tokens (default: True)
        enable_stopwords: Whether to remove stopwords (default: True)
        language: Language for tokenization (default: "en")
    """
    
    # BM25 algorithm parameters
    k1: float = 1.2
    b: float = 0.75
    
    # Tokenization settings
    min_token_length: int = 2
    max_token_length: int = 50
    
    # Redis integration
    redis_key_prefix: str = "bm25:"
    enable_persistence: bool = True
    
    # NLP settings
    enable_stemming: bool = True
    enable_stopwords: bool = True
    language: str = "en"
    
    # Performance settings
    batch_size: int = 100
    max_documents: int = 100000
    
    def validate(self) -> None:
        """
        Validate configuration parameters.
        
        Raises:
            ValueError: If any parameter is invalid
        """
        if self.k1 < 0 or self.k1 > 3.0:
            raise ValueError("k1 must be between 0.0 and 3.0")
        
        if self.b < 0 or self.b > 1.0:
            raise ValueError("b must be between 0.0 and 1.0")
        
        if self.min_token_length < 1:
            raise ValueError("min_token_length must be >= 1")
        
        if self.max_token_length < self.min_token_length:
            raise ValueError("max_token_length must be >= min_token_length")
        
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        
        if self.max_documents < 1:
            raise ValueError("max_documents must be >= 1")


def load_bm25_config_from_env() -> BM25Config:
    """
    Load BM25 configuration from environment variables.
    
    Returns:
        BM25Config instance with values from environment
    """
    config = BM25Config()
    
    # Load from environment variables
    if os.getenv("BM25_K1"):
        config.k1 = float(os.getenv("BM25_K1"))
    
    if os.getenv("BM25_B"):
        config.b = float(os.getenv("BM25_B"))
    
    if os.getenv("BM25_MIN_TOKEN_LENGTH"):
        config.min_token_length = int(os.getenv("BM25_MIN_TOKEN_LENGTH"))
    
    if os.getenv("BM25_MAX_TOKEN_LENGTH"):
        config.max_token_length = int(os.getenv("BM25_MAX_TOKEN_LENGTH"))
    
    if os.getenv("BM25_REDIS_KEY_PREFIX"):
        config.redis_key_prefix = os.getenv("BM25_REDIS_KEY_PREFIX")
    
    if os.getenv("BM25_ENABLE_PERSISTENCE"):
        config.enable_persistence = os.getenv("BM25_ENABLE_PERSISTENCE").lower() == "true"
    
    if os.getenv("BM25_ENABLE_STEMMING"):
        config.enable_stemming = os.getenv("BM25_ENABLE_STEMMING").lower() == "true"
    
    if os.getenv("BM25_ENABLE_STOPWORDS"):
        config.enable_stopwords = os.getenv("BM25_ENABLE_STOPWORDS").lower() == "true"
    
    if os.getenv("BM25_LANGUAGE"):
        config.language = os.getenv("BM25_LANGUAGE")
    
    if os.getenv("BM25_BATCH_SIZE"):
        config.batch_size = int(os.getenv("BM25_BATCH_SIZE"))
    
    if os.getenv("BM25_MAX_DOCUMENTS"):
        config.max_documents = int(os.getenv("BM25_MAX_DOCUMENTS"))
    
    # Validate configuration
    config.validate()
    
    return config


def get_default_bm25_config() -> Dict[str, Any]:
    """
    Get default BM25 configuration as dictionary.
    
    Returns:
        Dictionary with default BM25 configuration
    """
    config = BM25Config()
    return {
        "k1": config.k1,
        "b": config.b,
        "min_token_length": config.min_token_length,
        "max_token_length": config.max_token_length,
        "redis_key_prefix": config.redis_key_prefix,
        "enable_persistence": config.enable_persistence,
        "enable_stemming": config.enable_stemming,
        "enable_stopwords": config.enable_stopwords,
        "language": config.language,
        "batch_size": config.batch_size,
        "max_documents": config.max_documents
    }
