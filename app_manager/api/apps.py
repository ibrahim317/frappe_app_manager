"""Refactored App Manager API using SOLID principles."""

import os
from typing import Any, Dict, List, Optional

import frappe
from frappe.utils import cstr

from app_manager.app_manager.utils.apps_scan import (
    scan_and_sync_custom_apps
)
from app_manager.services.service_container import get_service_container
from app_manager.services.exceptions import (
    AppManagerException
)


@frappe.whitelist()
def check_app_exists(repo_url: str, is_private: bool = False, username: str = "", pat: str = "") -> dict:
	"""Check if an app already exists in the apps directory.

	Extracts app name from repo URL and checks if directory exists.
	"""
	if not repo_url:
		raise frappe.ValidationError("repo_url is required")

	try:
		services = get_service_container()
		app_info = services.get_app_repository().get_app_info(repo_url)
		return {
			"exists": app_info.exists,
			"app_name": app_info.name,
			"app_path": app_info.path
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "App Manager: check_app_exists failed")
		return {"exists": False, "error": str(e)}


@frappe.whitelist()
def get_app(repo_url: str, overwrite: bool = False, is_private: bool = False, username: str = "", pat: str = "") -> dict:
	"""Fetch an app into bench using its repository URL.

	Runs: bench get-app <repo_url> [--overwrite] in background job
	"""
	if not repo_url:
		raise frappe.ValidationError("repo_url is required")

	try:
		services = get_service_container()
		result = services.get_app_manager().fetch_app(
			repo_url=repo_url,
			overwrite=overwrite,
			is_private=is_private,
			username=username,
			pat=pat
		)
		return result
	except AppManagerException as e:
		frappe.log_error(frappe.get_traceback(), f"App Manager: get_app failed - {str(e)}")
		return {"ok": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "App Manager: get_app unexpected error")
		return {"ok": False, "error": "Unexpected error occurred"}

@frappe.whitelist()
def reload_apps() -> dict:
	"""Rescan bench apps and sync Frappe Custom App records."""
	res = scan_and_sync_custom_apps()
	return {"ok": True, **res}


@frappe.whitelist()
def install_app(app_name: str) -> dict:
	"""Install an already available app onto the current site.

	Runs: bench --site <site> install-app <app_name>
	"""
	if not app_name:
		raise frappe.ValidationError("app_name is required")

	try:
		services = get_service_container()
		result = services.get_app_manager().install_app(app_name)
		return {
			"ok": result.ok,
			"stdout": result.stdout,
			"stderr": result.stderr
		}
	except AppManagerException as e:
		frappe.log_error(frappe.get_traceback(), f"App Manager: install_app failed - {str(e)}")
		return {"ok": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "App Manager: install_app unexpected error")
		return {"ok": False, "error": "Unexpected error occurred"}


@frappe.whitelist()
def delete_app_directory(app_name: str) -> dict:
	"""Delete an app directory from bench (useful for manual cleanup)."""
	if not app_name:
		raise frappe.ValidationError("app_name is required")
	
	try:
		services = get_service_container()
		file_system = services.get_file_system()
		
		from app_manager.app_manager.utils.apps_scan import bench_paths as _bench_dirs
		paths = _bench_dirs()
		app_path = os.path.join(paths["apps_dir"], app_name)
		
		if not file_system.is_dir(app_path):
			return {
				"ok": False,
				"stderr": f"App directory not found: {app_path}"
			}
		
		# Remove the app directory
		file_system.remove_tree(app_path)
		return {
			"ok": True,
			"stdout": f"Successfully removed {app_name} directory from bench"
		}
	except Exception as e:
		return {
			"ok": False,
			"stderr": f"Failed to remove {app_name}: {str(e)}"
		}


@frappe.whitelist()
def uninstall_app(app_name: str) -> dict:
	"""Uninstall an app from the current site.

	Runs: bench --site <site> uninstall-app <app_name>
	"""
	if not app_name:
		raise frappe.ValidationError("app_name is required")

	try:
		services = get_service_container()
		result = services.get_app_manager().uninstall_app(app_name)
		return {
			"ok": result.ok,
			"stdout": result.stdout,
			"stderr": result.stderr
		}
	except AppManagerException as e:
		frappe.log_error(frappe.get_traceback(), f"App Manager: uninstall_app failed - {str(e)}")
		return {"ok": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "App Manager: uninstall_app unexpected error")
		return {"ok": False, "error": "Unexpected error occurred"}


@frappe.whitelist()
def remove_app(app_name: str) -> dict:
	"""Remove an app from bench (deletes app from sites/apps.json and bench config).

	Runs: bench remove-app <app_name>
	"""
	if not app_name:
		raise frappe.ValidationError("app_name is required")

	try:
		services = get_service_container()
		result = services.get_app_manager().remove_app(app_name)
		return {
			"ok": result.ok,
			"stdout": result.stdout,
			"stderr": result.stderr
		}
	except AppManagerException as e:
		frappe.log_error(frappe.get_traceback(), f"App Manager: remove_app failed - {str(e)}")
		return {"ok": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "App Manager: remove_app unexpected error")
		return {"ok": False, "error": "Unexpected error occurred"}


