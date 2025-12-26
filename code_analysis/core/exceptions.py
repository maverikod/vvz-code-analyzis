"""
Base exception hierarchy for code analysis operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


class CodeAnalysisError(Exception):
    """Base exception for code analysis operations."""

    def __init__(self, message: str, code: str = None, details: dict = None):
        """
        Initialize exception.

        Args:
            message: Human-readable error message
            code: Optional error code for programmatic handling
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ValidationError(CodeAnalysisError):
    """Raised when validation fails."""

    def __init__(self, message: str, field: str = None, details: dict = None):
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Optional field name that failed validation
            details: Optional additional details
        """
        super().__init__(message, code="VALIDATION_ERROR", details=details)
        self.field = field


class RefactoringError(CodeAnalysisError):
    """Raised when refactoring operations fail."""

    def __init__(self, message: str, operation: str = None, details: dict = None):
        """
        Initialize refactoring error.

        Args:
            message: Error message
            operation: Optional refactoring operation name
            details: Optional additional details
        """
        super().__init__(message, code="REFACTORING_ERROR", details=details)
        self.operation = operation


class DatabaseError(CodeAnalysisError):
    """Raised when database operations fail."""

    def __init__(self, message: str, operation: str = None, details: dict = None):
        """
        Initialize database error.

        Args:
            message: Error message
            operation: Optional database operation name
            details: Optional additional details
        """
        super().__init__(message, code="DATABASE_ERROR", details=details)
        self.operation = operation


class AnalysisError(CodeAnalysisError):
    """Raised when analysis operations fail."""

    def __init__(self, message: str, analysis_type: str = None, details: dict = None):
        """
        Initialize analysis error.

        Args:
            message: Error message
            analysis_type: Optional analysis type (e.g., 'ast', 'semantic')
            details: Optional additional details
        """
        super().__init__(message, code="ANALYSIS_ERROR", details=details)
        self.analysis_type = analysis_type


class ConfigurationError(CodeAnalysisError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str, config_key: str = None, details: dict = None):
        """
        Initialize configuration error.

        Args:
            message: Error message
            config_key: Optional configuration key that is invalid
            details: Optional additional details
        """
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)
        self.config_key = config_key
