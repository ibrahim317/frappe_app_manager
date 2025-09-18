"""Service container for dependency injection."""

from app_manager.services.interfaces import (
    CommandExecutorInterface, FileSystemInterface, PackageManagerInterface,
    NotificationInterface, AppRepositoryInterface, AppManagerInterface
)
from app_manager.services.command_executor import FrappeCommandExecutor
from app_manager.services.file_system import OSFileSystem
from app_manager.services.package_manager import PipPackageManager
from app_manager.services.notification_service import FrappeNotificationService
from app_manager.services.app_repository import FrappeAppRepository
from app_manager.services.app_manager_service import FrappeAppManager


class ServiceContainer:
    """Service container for dependency injection."""
    
    def __init__(self):
        self._services = {}
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize all services with their dependencies."""
        # Core services (no dependencies)
        self._services[CommandExecutorInterface] = FrappeCommandExecutor()
        self._services[FileSystemInterface] = OSFileSystem()
        self._services[NotificationInterface] = FrappeNotificationService()
        
        # Services with dependencies
        self._services[PackageManagerInterface] = PipPackageManager(
            self._services[CommandExecutorInterface]
        )
        
        self._services[AppRepositoryInterface] = FrappeAppRepository(
            self._services[FileSystemInterface]
        )
        
        self._services[AppManagerInterface] = FrappeAppManager(
            self._services[CommandExecutorInterface],
            self._services[FileSystemInterface],
            self._services[PackageManagerInterface],
            self._services[NotificationInterface],
            self._services[AppRepositoryInterface]
        )
    
    def get(self, service_type):
        """Get a service instance by type."""
        return self._services.get(service_type)
    
    def get_command_executor(self) -> CommandExecutorInterface:
        """Get the command executor service."""
        return self._services[CommandExecutorInterface]
    
    def get_file_system(self) -> FileSystemInterface:
        """Get the file system service."""
        return self._services[FileSystemInterface]
    
    def get_package_manager(self) -> PackageManagerInterface:
        """Get the package manager service."""
        return self._services[PackageManagerInterface]
    
    def get_notification_service(self) -> NotificationInterface:
        """Get the notification service."""
        return self._services[NotificationInterface]
    
    def get_app_repository(self) -> AppRepositoryInterface:
        """Get the app repository service."""
        return self._services[AppRepositoryInterface]
    
    def get_app_manager(self) -> AppManagerInterface:
        """Get the app manager service."""
        return self._services[AppManagerInterface]


# Global service container instance
_service_container = None


def get_service_container() -> ServiceContainer:
    """Get the global service container instance."""
    global _service_container
    if _service_container is None:
        _service_container = ServiceContainer()
    return _service_container
