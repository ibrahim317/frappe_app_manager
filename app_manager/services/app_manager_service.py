"""Main app management service implementation."""

import os
from typing import Dict, Any, Optional

import frappe
from frappe.utils import cstr

from app_manager.services.interfaces import (
    AppManagerInterface, CommandResult, CommandExecutorInterface,
    FileSystemInterface, PackageManagerInterface, NotificationInterface,
    AppRepositoryInterface
)
from app_manager.app_manager.utils.apps_scan import (
    get_current_site as _current_site,
    bench_paths as _bench_dirs,
    guess_app_dir_name_from_repo as _guess_app_dir_name_from_repo,
    upsert_custom_app_from_dir as _upsert_custom_app_from_dir
)


class FrappeAppManager(AppManagerInterface):
    """Main app management service for Frappe applications."""
    
    def __init__(
        self,
        command_executor: CommandExecutorInterface,
        file_system: FileSystemInterface,
        package_manager: PackageManagerInterface,
        notification_service: NotificationInterface,
        app_repository: AppRepositoryInterface
    ):
        self.command_executor = command_executor
        self.file_system = file_system
        self.package_manager = package_manager
        self.notification_service = notification_service
        self.app_repository = app_repository
    
    def _construct_authenticated_url(self, repo_url: str, username: str, pat: str) -> str:
        """Construct authenticated URL for private repositories."""
        if repo_url.startswith('https://github.com/'):
            return repo_url.replace('https://github.com/', f'https://{username}:{pat}@github.com/')
        elif repo_url.startswith('git@github.com:'):
            # Convert SSH to HTTPS with credentials
            repo_path = repo_url.replace('git@github.com:', '')
            return f'https://{username}:{pat}@github.com/{repo_path}'
        else:
            # For other formats, return as-is (might need additional handling)
            return repo_url
    
    def _update_custom_app_status(self, app_name: str, status: str) -> None:
        """Update the status field of matching Frappe Custom App and commit."""
        try:
            name = frappe.db.get_value("Frappe Custom App", {"app_name": app_name}, "name")
            if not name:
                return
            doc = frappe.get_doc("Frappe Custom App", cstr(name))
            doc.set("status", status)
            doc.save()
            frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"App Manager: failed to update status for {app_name} -> {status}"
            )
    
    def _delete_custom_app_doc(self, app_name: str) -> None:
        """Delete the matching Frappe Custom App document and commit."""
        try:
            name = frappe.db.get_value("Frappe Custom App", {"app_name": app_name}, "name")
            if not name:
                return
            frappe.delete_doc("Frappe Custom App", cstr(name), force=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"App Manager: failed to delete Frappe Custom App doc for {app_name}"
            )
    
    def _ensure_app_is_installed_as_package(self, app_name: str) -> bool:
        """Ensure the app is installed as a Python package before attempting site installation."""
        paths = _bench_dirs()
        app_path = os.path.join(paths["apps_dir"], app_name)
        
        if not self.file_system.is_dir(app_path):
            return False
        
        # Check if the app has a setup.py or pyproject.toml
        setup_py_path = os.path.join(app_path, "setup.py")
        pyproject_toml_path = os.path.join(app_path, "pyproject.toml")
        
        if self.file_system.exists(setup_py_path) or self.file_system.exists(pyproject_toml_path):
            # Check if app is installed as a proper package (not development mode)
            try:
                import pkg_resources
                dist = pkg_resources.get_distribution(app_name)
                # Check if it's properly installed (not in development mode)
                if dist and dist.location:
                    # If location points to the actual app directory, it's in development mode (.pth file)
                    # If location points to site-packages, it's properly installed
                    if not dist.location.endswith(app_path):
                        return True
            except (pkg_resources.DistributionNotFound, ImportError):
                pass
            
            # App is not installed as a proper package, install it
            install_result = self.package_manager.install_package(app_path)
            return install_result.ok
        
        return True  # App doesn't need package installation
    
    def fetch_app(self, repo_url: str, overwrite: bool = False, 
                 is_private: bool = False, username: str = "", 
                 pat: str = "") -> Dict[str, Any]:
        """Fetch an app from a repository."""
        if not repo_url:
            raise frappe.ValidationError("repo_url is required")

        # Construct authenticated URL if private repo
        authenticated_repo_url = repo_url
        if is_private and username and pat:
            authenticated_repo_url = self._construct_authenticated_url(repo_url, username, pat)

        # Extract app name for user feedback
        try:
            app_dir_name = _guess_app_dir_name_from_repo(repo_url)
        except Exception:
            app_dir_name = "app"

        # Start background job
        job = frappe.enqueue(
            "app_manager.services.app_manager_service._get_app_background",
            queue="long",
            timeout=3600,  # 1 hour timeout
            repo_url=authenticated_repo_url,
            overwrite=overwrite,
            app_name=app_dir_name,
            user=frappe.session.user
        )

        return {
            "ok": True,
            "message": f"Started fetching {app_dir_name} in background",
            "job_id": job.id if job else None
        }
    
    def install_app(self, app_name: str) -> CommandResult:
        """Install an app on the current site."""
        if not app_name:
            raise frappe.ValidationError("app_name is required")

        # Ensure the app is installed as a Python package first
        if not self._ensure_app_is_installed_as_package(app_name):
            return CommandResult(
                ok=False,
                stdout="",
                stderr=f"Failed to install {app_name} as Python package. Please check the app structure and try again."
            )

        site = _current_site()
        cmd = ["bench", "--site", site, "install-app", app_name]
        # Refresh apps list so import path includes newly fetched apps
        self.app_repository.refresh_apps_list()
        result = self.command_executor.execute(cmd)
        
        if result.ok:
            self._update_custom_app_status(app_name, "Installed")
        
        return result
    
    def uninstall_app(self, app_name: str) -> CommandResult:
        """Uninstall an app from the current site."""
        if not app_name:
            raise frappe.ValidationError("app_name is required")

        site = _current_site()
        cmd = ["bench", "--site", site, "uninstall-app", app_name, "--yes"]
        result = self.command_executor.execute(cmd)
        
        if result.ok:
            self._update_custom_app_status(app_name, "Available")
        
        return result
    
    def remove_app(self, app_name: str) -> CommandResult:
        """Remove an app from bench."""
        if not app_name:
            raise frappe.ValidationError("app_name is required")

        cmd = ["bench", "remove-app", app_name]
        result = self.command_executor.execute(cmd)
        
        if result.ok:
            # Remove the document from DB when app is removed from bench
            self._delete_custom_app_doc(app_name)
        
        return result


def _get_app_background(repo_url: str, overwrite: bool, app_name: str, user: str):
    """Background job to fetch app and send websocket updates."""
    from frappe.utils import execute_in_shell
    
    def _run(cmd):
        err, out = execute_in_shell(cmd, check_exit_code=False)
        return {
            "ok": bool(not err),
            "stdout": (out or b"").decode(errors="replace"),
            "stderr": (err or b"").decode(errors="replace"),
        }
    
    def _get_virtual_env_pip():
        """Get the path to pip in the virtual environment."""
        from frappe.utils import get_bench_path
        bench_path = get_bench_path()
        return os.path.join(bench_path, "env", "bin", "pip")
    
    try:
        # Send start notification
        frappe.publish_realtime(
            "app_manager_progress",
            {
                "status": "started",
                "message": f"Starting to fetch {app_name}...",
                "app_name": app_name
            },
            user=user
        )

        # Run the actual command
        cmd = ["bench", "get-app", repo_url, "--resolve-deps"]
        if overwrite:
            cmd.append("--overwrite")

        result = _run(cmd)

        if result.get("ok"):
            # Ensure apps list reflects newly fetched app for import path resolution
            from app_manager.services.service_container import get_service_container
            services = get_service_container()
            services.get_app_repository().refresh_apps_list()
            
            # Install the app as a Python package
            paths = _bench_dirs()
            app_dir_name = _guess_app_dir_name_from_repo(repo_url)
            app_path = os.path.join(paths["apps_dir"], app_dir_name) if app_dir_name else None
            
            if app_path and os.path.isdir(app_path) and app_dir_name:
                # Check if the app has a setup.py or pyproject.toml
                setup_py_path = os.path.join(app_path, "setup.py")
                pyproject_toml_path = os.path.join(app_path, "pyproject.toml")
                
                if os.path.exists(setup_py_path) or os.path.exists(pyproject_toml_path):
                    # Install the app as a Python package
                    frappe.publish_realtime(
                        "app_manager_progress",
                        {
                            "status": "installing_package",
                            "message": f"Installing {app_name} as Python package...",
                            "app_name": app_name
                        },
                        user=user
                    )
                    
                    install_cmd = [_get_virtual_env_pip(), "install", "--force-reinstall", app_path, "--no-cache-dir"]
                    install_result = _run(install_cmd)
                    
                    if not install_result.get("ok"):
                        frappe.log_error(
                            f"Failed to install {app_name} as Python package: {install_result.get('stderr', '')}",
                            "App Manager: pip install failed"
                        )
                        frappe.publish_realtime(
                            "app_manager_progress",
                            {
                                "status": "package_install_failed",
                                "message": f"Failed to install {app_name} as Python package",
                                "app_name": app_name,
                                "error": install_result.get("stderr", "Unknown error")
                            },
                            user=user
                        )
                    else:
                        frappe.publish_realtime(
                            "app_manager_progress",
                            {
                                "status": "package_installed",
                                "message": f"Successfully installed {app_name} as Python package",
                                "app_name": app_name
                            },
                            user=user
                        )

            # Send success notification
            frappe.publish_realtime(
                "app_manager_progress",
                {
                    "status": "success",
                    "message": f"Successfully fetched {app_name}",
                    "app_name": app_name,
                    "output": result.get("stdout", "")
                },
                user=user
            )

            # Attempt to auto-create/update Frappe Custom App doc
            try:
                # If the app directory exists, delegate to shared single-app upsert
                if app_path and os.path.isdir(app_path) and app_dir_name:
                    res = _upsert_custom_app_from_dir(app_dir_name)
                    if res.get("action") in ("created", "updated"):
                        frappe.publish_realtime(
                            "app_manager_progress",
                            {
                                "status": "doc_updated",
                                "message": f"Updated {app_name} in app list",
                                "app_name": app_name
                            },
                            user=user
                        )
            except Exception as e:
                frappe.log_error(frappe.get_traceback(), "App Manager: get_app doc creation failed")
        else:
            # Even if bench get-app failed, the app might still be installed
            # Let's check if we can still proceed with package installation
            paths = _bench_dirs()
            app_dir_name = _guess_app_dir_name_from_repo(repo_url)
            app_path = os.path.join(paths["apps_dir"], app_dir_name) if app_dir_name else None
            
            if app_path and os.path.isdir(app_path) and app_dir_name:
                # Proceed with package installation even if bench get-app had issues
                setup_py_path = os.path.join(app_path, "setup.py")
                pyproject_toml_path = os.path.join(app_path, "pyproject.toml")
                
                if os.path.exists(setup_py_path) or os.path.exists(pyproject_toml_path):
                    # Check if app needs to be installed as a proper package
                    # Install the app as a Python package
                    frappe.publish_realtime(
                        "app_manager_progress",
                        {
                            "status": "installing_package",
                            "message": f"Installing {app_name} as Python package...",
                            "app_name": app_name
                        },
                        user=user
                    )
                    
                    install_cmd = [_get_virtual_env_pip(), "install", "--force-reinstall", app_path, "--no-cache-dir"]
                    install_result = _run(install_cmd)
                    
                    if not install_result.get("ok"):
                        frappe.log_error(
                            f"Failed to install {app_name} as Python package: {install_result.get('stderr', '')}",
                            "App Manager: pip install failed"
                        )
                        frappe.publish_realtime(
                            "app_manager_progress",
                            {
                                "status": "package_install_failed",
                                "message": f"Failed to install {app_name} as Python package",
                                "app_name": app_name,
                                "error": install_result.get("stderr", "Unknown error")
                            },
                            user=user
                        )
                    else:
                        frappe.publish_realtime(
                            "app_manager_progress",
                            {
                                "status": "package_installed",
                                "message": f"Successfully installed {app_name} as Python package",
                                "app_name": app_name
                            },
                            user=user
                        )
            
            # Send error notification
            frappe.publish_realtime(
                "app_manager_progress",
                {
                    "status": "error",
                    "message": f"Failed to fetch {app_name}",
                    "app_name": app_name,
                    "error": result.get("stderr", "Unknown error")
                },
                user=user
            )

    except Exception as e:
        # Send error notification for unexpected errors
        frappe.publish_realtime(
            "app_manager_progress",
            {
                "status": "error",
                "message": f"Unexpected error while fetching {app_name}",
                "app_name": app_name,
                "error": str(e)
            },
            user=user
        )
        frappe.log_error(frappe.get_traceback(), f"App Manager: get_app background job failed for {app_name}")
