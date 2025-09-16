import os
from typing import Any, Dict, List, Optional

import frappe
from frappe.utils import execute_in_shell, cstr
from app_manager.app_manager.utils.apps_scan import (
	scan_and_sync_custom_apps,
	get_current_site as _current_site,
	bench_paths as _bench_dirs,
	guess_app_dir_name_from_repo as _guess_app_dir_name_from_repo,
	upsert_custom_app_from_dir as _upsert_custom_app_from_dir,
)


def _run(cmd: list[str]) -> dict:
	# Use execute_in_shell with joined command string for proper escaping
	# Returns structured response
	err, out = execute_in_shell(cmd, check_exit_code=False)
	return {
		"ok": bool(not err),
		"stdout": (out or b"").decode(errors="replace"),
		"stderr": (err or b"").decode(errors="replace"),
	}



def _refresh_apps_txt() -> None:
    """Add new apps from apps directory to sites/apps.txt.

    Only adds apps that are not already present in apps.txt to avoid duplicates.
    This ensures Python can import newly fetched apps in production where
    auto-reload isn't active.
    """
    try:
        paths = _bench_dirs()
        apps_dir = paths["apps_dir"]
        sites_dir = paths["sites_dir"]
        apps_txt_path = os.path.join(sites_dir, "apps.txt")

        if not os.path.isdir(apps_dir):
            return

        # Read existing apps from apps.txt
        existing_apps = set()
        if os.path.exists(apps_txt_path):
            with open(apps_txt_path, 'r', encoding='utf-8') as f:
                existing_apps = {line.strip() for line in f if line.strip()}

        # Find new apps in apps directory
        new_apps = []
        for item in os.listdir(apps_dir):
            item_path = os.path.join(apps_dir, item)
            if (os.path.isdir(item_path) and 
                not item.startswith('.') and 
                item not in existing_apps):
                new_apps.append(item)

        # Add new apps to apps.txt if any
        if new_apps:
            new_apps.sort()
            with open(apps_txt_path, 'a', encoding='utf-8') as f:
                f.write("\n".join(new_apps) + "\n")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "App Manager: failed to refresh sites/apps.txt")


def _get_virtual_env_pip() -> str:
	"""Get the path to pip in the virtual environment."""
	from frappe.utils import get_bench_path
	bench_path = get_bench_path()
	return os.path.join(bench_path, "env", "bin", "pip")



def _update_custom_app_status(app_name: str, status: str) -> None:
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


def _delete_custom_app_doc(app_name: str) -> None:
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


@frappe.whitelist()
def check_app_exists(repo_url: str) -> dict:
	"""Check if an app already exists in the apps directory.

	Extracts app name from repo URL and checks if directory exists.
	"""
	if not repo_url:
		raise frappe.ValidationError("repo_url is required")

	try:
		paths = _bench_dirs()
		app_dir_name = _guess_app_dir_name_from_repo(repo_url)
		app_path = os.path.join(paths["apps_dir"], app_dir_name) if app_dir_name else None
		exists = app_path and os.path.isdir(app_path)
		return {
			"exists": exists,
			"app_name": app_dir_name,
			"app_path": app_path
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "App Manager: check_app_exists failed")
		return {"exists": False, "error": str(e)}


@frappe.whitelist()
def get_app(repo_url: str, overwrite: bool = False) -> dict:
	"""Fetch an app into bench using its repository URL.

	Runs: bench get-app <repo_url> [--overwrite] in background job
	"""
	if not repo_url:
		raise frappe.ValidationError("repo_url is required")

	# Extract app name for user feedback
	try:
		paths = _bench_dirs()
		app_dir_name = _guess_app_dir_name_from_repo(repo_url)
	except Exception:
		app_dir_name = "app"

	# Start background job
	job = frappe.enqueue(
		"app_manager.api.apps._get_app_background",
		queue="long",
		timeout=3600,  # 1 hour timeout
		repo_url=repo_url,
		overwrite=overwrite,
		app_name=app_dir_name,
		user=frappe.session.user
	)

	return {
		"ok": True,
		"message": f"Started fetching {app_dir_name} in background",
		"job_id": job.id if job else None
	}


def _get_app_background(repo_url: str, overwrite: bool, app_name: str, user: str):
	"""Background job to fetch app and send websocket updates."""
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
		cmd = ["bench", "get-app", repo_url]
		if overwrite:
			cmd.append("--overwrite")

		result = _run(cmd)

		if result.get("ok"):
			# Ensure apps list reflects newly fetched app for import path resolution
			_refresh_apps_txt()
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
					
					install_cmd = [_get_virtual_env_pip(), "install", app_path]
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


@frappe.whitelist()
def reload_apps() -> dict:
	"""Rescan bench apps and sync Frappe Custom App records."""
	res = scan_and_sync_custom_apps()
	return {"ok": True, **res}


def _ensure_app_is_installed_as_package(app_name: str) -> bool:
	"""Ensure the app is installed as a Python package before attempting site installation."""
	paths = _bench_dirs()
	app_path = os.path.join(paths["apps_dir"], app_name)
	
	if not os.path.isdir(app_path):
		return False
	
	# Check if the app has a setup.py or pyproject.toml
	setup_py_path = os.path.join(app_path, "setup.py")
	pyproject_toml_path = os.path.join(app_path, "pyproject.toml")
	
	if os.path.exists(setup_py_path) or os.path.exists(pyproject_toml_path):
		# Try to import the app to check if it's installed
		try:
			__import__(app_name)
			return True
		except ImportError:
			# App is not installed as a package, install it
			install_cmd = [_get_virtual_env_pip(), "install", "-e", app_path]
			install_result = _run(install_cmd)
			return install_result.get("ok", False)
	
	return True  # App doesn't need package installation


@frappe.whitelist()
def install_app(app_name: str) -> dict:
	"""Install an already available app onto the current site.

	Runs: bench --site <site> install-app <app_name>
	"""
	if not app_name:
		raise frappe.ValidationError("app_name is required")

	# Ensure the app is installed as a Python package first
	if not _ensure_app_is_installed_as_package(app_name):
		return {
			"ok": False,
			"stderr": f"Failed to install {app_name} as Python package. Please check the app structure and try again."
		}

	site = _current_site()
	cmd = ["bench", "--site", site, "install-app", app_name]
	# Refresh apps list so import path includes newly fetched apps
	_refresh_apps_txt()
	res = _run(cmd)
	if res.get("ok"):
		_update_custom_app_status(app_name, "Installed")
	return res




@frappe.whitelist()
def delete_app_directory(app_name: str) -> dict:
	"""Delete an app directory from bench (useful for manual cleanup)."""
	if not app_name:
		raise frappe.ValidationError("app_name is required")
	
	paths = _bench_dirs()
	app_path = os.path.join(paths["apps_dir"], app_name)
	
	if not os.path.isdir(app_path):
		return {
			"ok": False,
			"stderr": f"App directory not found: {app_path}"
		}
	
	# Remove the app directory
	import shutil
	try:
		shutil.rmtree(app_path)
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

	site = _current_site()
	cmd = ["bench", "--site", site, "uninstall-app", app_name, "--yes"]
	res = _run(cmd)
	if res.get("ok"):
		_update_custom_app_status(app_name, "Available")
	return res


@frappe.whitelist()
def remove_app(app_name: str) -> dict:
	"""Remove an app from bench (deletes app from sites/apps.json and bench config).

	Runs: bench remove-app <app_name>
	"""
	if not app_name:
		raise frappe.ValidationError("app_name is required")

	cmd = ["bench", "remove-app", app_name]
	res = _run(cmd)
	if res.get("ok"):
		# Remove the document from DB when app is removed from bench
		_delete_custom_app_doc(app_name)
	return res
