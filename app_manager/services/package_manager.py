"""Package management service implementation."""

import os
from typing import List

from app_manager.services.interfaces import PackageManagerInterface, CommandResult, CommandExecutorInterface


class PipPackageManager(PackageManagerInterface):
    """Package manager using pip for Python package installation."""
    
    def __init__(self, command_executor: CommandExecutorInterface):
        self.command_executor = command_executor
    
    def _get_virtual_env_pip(self) -> str:
        """Get the path to pip in the virtual environment."""
        from frappe.utils import get_bench_path
        bench_path = get_bench_path()
        return os.path.join(bench_path, "env", "bin", "pip")
    
    def install_package(self, app_path: str) -> CommandResult:
        """Install an app as a Python package."""
        cmd = [
            self._get_virtual_env_pip(), 
            "install", 
            "--force-reinstall", 
            app_path, 
            "--no-cache-dir"
        ]
        return self.command_executor.execute(cmd)
    