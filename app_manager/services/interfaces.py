"""Interfaces and abstract base classes for App Manager services."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of a command execution."""
    ok: bool
    stdout: str
    stderr: str


@dataclass
class AppInfo:
    """Information about an app."""
    name: str
    path: str
    exists: bool
    version: Optional[str] = None
    repo_url: Optional[str] = None


class CommandExecutorInterface(ABC):
    """Interface for executing shell commands."""
    
    @abstractmethod
    def execute(self, cmd: List[str]) -> CommandResult:
        """Execute a shell command and return the result."""
        pass


class FileSystemInterface(ABC):
    """Interface for file system operations."""
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a path exists."""
        pass
    
    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """Check if a path is a directory."""
        pass
    
    @abstractmethod
    def list_dir(self, path: str) -> List[str]:
        """List directory contents."""
        pass
    
    @abstractmethod
    def read_file(self, path: str, encoding: str = 'utf-8') -> str:
        """Read file contents."""
        pass
    
    @abstractmethod
    def write_file(self, path: str, content: str, encoding: str = 'utf-8') -> None:
        """Write content to a file."""
        pass
    
    @abstractmethod
    def append_file(self, path: str, content: str, encoding: str = 'utf-8') -> None:
        """Append content to a file."""
        pass
    
    @abstractmethod
    def remove_tree(self, path: str) -> None:
        """Remove a directory tree."""
        pass


class AppRepositoryInterface(ABC):
    """Interface for app repository operations."""
    
    @abstractmethod
    def get_app_info(self, repo_url: str) -> AppInfo:
        """Get information about an app from its repository URL."""
        pass
    
    @abstractmethod
    def check_app_exists(self, app_name: str) -> bool:
        """Check if an app exists in the apps directory."""
        pass
    
    @abstractmethod
    def refresh_apps_list(self) -> None:
        """Refresh the apps list in sites/apps.txt."""
        pass


class PackageManagerInterface(ABC):
    """Interface for package management operations."""
    
    @abstractmethod
    def install_package(self, app_path: str) -> CommandResult:
        """Install an app as a Python package."""
        pass
    
class NotificationInterface(ABC):
    """Interface for sending notifications."""
    
    @abstractmethod
    def send_progress_update(self, status: str, message: str, app_name: str, 
                           user: str, **kwargs) -> None:
        """Send a progress update notification."""
        pass


class AppManagerInterface(ABC):
    """Interface for app management operations."""
    
    @abstractmethod
    def fetch_app(self, repo_url: str, overwrite: bool = False, 
                 is_private: bool = False, username: str = "", 
                 pat: str = "") -> Dict[str, Any]:
        """Fetch an app from a repository."""
        pass
    
    @abstractmethod
    def install_app(self, app_name: str) -> CommandResult:
        """Install an app on the current site."""
        pass
    
    @abstractmethod
    def uninstall_app(self, app_name: str) -> CommandResult:
        """Uninstall an app from the current site."""
        pass
    
    @abstractmethod
    def remove_app(self, app_name: str) -> CommandResult:
        """Remove an app from bench."""
        pass
