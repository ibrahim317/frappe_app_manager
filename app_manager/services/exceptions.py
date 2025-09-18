"""Custom exceptions for App Manager services."""


class AppManagerException(Exception):
    """Base exception for App Manager operations."""
    pass


class AppNotFoundError(AppManagerException):
    """Raised when an app is not found."""
    pass


class AppInstallationError(AppManagerException):
    """Raised when app installation fails."""
    pass


class AppUninstallationError(AppManagerException):
    """Raised when app uninstallation fails."""
    pass


class AppRemovalError(AppManagerException):
    """Raised when app removal fails."""
    pass


class InvalidRepositoryURLError(AppManagerException):
    """Raised when repository URL is invalid."""
    pass


class PackageInstallationError(AppManagerException):
    """Raised when package installation fails."""
    pass


class CommandExecutionError(AppManagerException):
    """Raised when command execution fails."""
    pass


class FileSystemError(AppManagerException):
    """Raised when file system operations fail."""
    pass
