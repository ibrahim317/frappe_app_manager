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
				paths = _bench_dirs()
				app_dir_name = _guess_app_dir_name_from_repo(repo_url)
				app_path = os.path.join(paths["apps_dir"], app_dir_name) if app_dir_name else None

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


@frappe.whitelist()
def install_app(app_name: str) -> dict:
	"""Install an already available app onto the current site.

	Runs: bench --site <site> install-app <app_name>
	"""
	if not app_name:
		raise frappe.ValidationError("app_name is required")

	site = _current_site()
	cmd = ["bench", "--site", site, "install-app", app_name]
	res = _run(cmd)
	if res.get("ok"):
		_update_custom_app_status(app_name, "Installed")
	return res


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
