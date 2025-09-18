"""App repository service implementation."""

import os
from typing import Dict, Any, Optional, List

from app_manager.services.interfaces import (
    AppRepositoryInterface, AppInfo, FileSystemInterface, 
    CommandExecutorInterface
)
from app_manager.app_manager.utils.apps_scan import (
    bench_paths as _bench_dirs,
    guess_app_dir_name_from_repo as _guess_app_dir_name_from_repo
)


class FrappeAppRepository(AppRepositoryInterface):
    """App repository service for Frappe apps."""
    
    def __init__(self, file_system: FileSystemInterface):
        self.file_system = file_system
    
    def get_app_info(self, repo_url: str) -> AppInfo:
        """Get information about an app from its repository URL."""
        try:
            paths = _bench_dirs()
            app_dir_name = _guess_app_dir_name_from_repo(repo_url)
            app_path = os.path.join(paths["apps_dir"], app_dir_name) if app_dir_name else None
            exists = app_path and self.file_system.is_dir(app_path)
            
            return AppInfo(
                name=app_dir_name or "unknown",
                path=app_path or "",
                exists=bool(exists)
            )
        except Exception:
            return AppInfo(
                name="unknown",
                path="",
                exists=False
            )
    
    def check_app_exists(self, app_name: str) -> bool:
        """Check if an app exists in the apps directory."""
        try:
            paths = _bench_dirs()
            app_path = os.path.join(paths["apps_dir"], app_name)
            return self.file_system.is_dir(app_path)
        except Exception:
            return False
    
    def refresh_apps_list(self) -> None:
        """Refresh the apps list in sites/apps.txt."""
        try:
            paths = _bench_dirs()
            apps_dir = paths["apps_dir"]
            sites_dir = paths["sites_dir"]
            apps_txt_path = os.path.join(sites_dir, "apps.txt")

            if not self.file_system.is_dir(apps_dir):
                return

            # Read existing apps from apps.txt
            existing_apps = set()
            if self.file_system.exists(apps_txt_path):
                content = self.file_system.read_file(apps_txt_path)
                existing_apps = {line.strip() for line in content.splitlines() if line.strip()}

            # Find new apps in apps directory
            new_apps = []
            for item in self.file_system.list_dir(apps_dir):
                item_path = os.path.join(apps_dir, item)
                if (self.file_system.is_dir(item_path) and 
                    not item.startswith('.') and 
                    item not in existing_apps):
                    new_apps.append(item)

            # Add new apps to apps.txt if any
            if new_apps:
                new_apps.sort()
                content = "\n".join(new_apps) + "\n"
                self.file_system.append_file(apps_txt_path, content)
        except Exception as e:
            import frappe
            frappe.log_error(frappe.get_traceback(), "App Manager: failed to refresh sites/apps.txt")
