import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

import frappe
from frappe.utils import get_site_name, get_bench_path


def _get_site_name_safe() -> str:
	try:
		return get_site_name(frappe.local.request.host)
	except Exception:
		return getattr(frappe.local, "site", None) or frappe.local.site


def _bench_paths() -> Dict[str, str]:
	bench_root = get_bench_path()
	return {
		"bench_root": bench_root,
		"apps_dir": os.path.join(bench_root, "apps"),
		"sites_dir": os.path.join(bench_root, "sites"),
	}


def _load_apps_from_apps_txt(sites_dir: str) -> Optional[List[str]]:
	"""Load allowlisted app names from bench-level sites/apps.txt if present.

	Returns None if file doesn't exist (meaning no restriction should be applied).
	"""
	apps_txt_path = os.path.join(sites_dir, 'apps.txt')
	if not os.path.exists(apps_txt_path):
		return None
	try:
		with open(apps_txt_path, 'r', encoding='utf-8') as handle:
			allowed: List[str] = []
			for line in handle.readlines():
				line = line.strip()
				if not line or line.startswith('#'):
					continue
				allowed.append(line)
			return allowed
	except Exception:
		# On any parsing error, behave as if no restriction
		return None


def get_apps_from_directory(apps_dir: str) -> List[str]:
	"""Return app directories filtered by sites/apps.txt if present.

	- If sites/apps.txt exists, only include directories listed there
	- Otherwise, include all directories under apps_dir (current behavior)
	"""
	apps: List[str] = []
	if not os.path.exists(apps_dir):
		return apps

	paths = _bench_paths()
	allowed_apps = _load_apps_from_apps_txt(paths["sites_dir"])  # None means no restriction

	for item in os.listdir(apps_dir):
		item_path = os.path.join(apps_dir, item)
		if not os.path.isdir(item_path) or item.startswith('.'):
			continue
		if allowed_apps is not None and item not in allowed_apps:
			continue
		apps.append(item)

	return apps


def load_apps_json(apps_json_path: str) -> Dict[str, Any]:
	if os.path.exists(apps_json_path):
		with open(apps_json_path, 'r', encoding='utf-8') as f:
			return json.load(f)
	return {}


def get_git_remote_url(app_path: str) -> Optional[str]:
	for remote_name in ['origin', 'upstream']:
		try:
			result = subprocess.run(
				['git', 'remote', 'get-url', remote_name],
				cwd=app_path,
				capture_output=True,
				text=True,
				check=True
			)
			return result.stdout.strip()
		except subprocess.CalledProcessError:
			continue
	return None


def parse_hooks_file(hooks_path: str) -> Dict[str, Any]:
	app_info: Dict[str, Any] = {}
	if not os.path.exists(hooks_path):
		return app_info
	with open(hooks_path, 'r', encoding='utf-8') as f:
		content = f.read()

	def _m(pattern: str) -> Optional[str]:
		m = re.search(pattern, content, re.MULTILINE)
		return m.group(1) if m else None

	name = _m(r'^app_name\s*=\s*["\']([^"\']+)["\']')
	if name:
		app_info['app_name'] = name
	title = _m(r'^app_title\s*=\s*["\']([^"\']+)["\']')
	if title:
		app_info['app_title'] = title
	desc = _m(r'^app_description\s*=\s*["\']([^"\']+)["\']')
	if desc:
		app_info['app_description'] = desc
	icon = _m(r'^app_icon\s*=\s*["\']([^"\']+)["\']')
	icon_url = _m(r'^app_icon_url\s*=\s*["\']([^"\']+)["\']')
	if icon_url:
		app_info['app_icon'] = icon_url
	elif icon:
		app_info['app_icon'] = icon

	deps_match = re.search(r'^required_apps\s*=\s*\[(.*?)\]', content, re.MULTILINE | re.DOTALL)
	deps: List[str] = []
	if deps_match:
		for dep in re.findall(r'["\']([^"\']+)["\']', deps_match.group(1)):
			deps.append(dep)
	app_info['required_apps'] = deps
	return app_info


def get_installed_apps_for_site(site_name: str, project_root: str) -> List[str]:
	installed_apps: List[str] = []

	# Primary: use bench CLI output for the site
	try:
		# Example output lines:
		# frappe           15.x.x-develop (64ab641) develop
		# enhanced_sidebar 0.0.1                    develop
		# app_manager      0.0.1                    develop
		result = subprocess.run(
			['bench', '--site', site_name, 'list-apps'],
			cwd=project_root or None,
			capture_output=True,
			text=True,
			check=True,
		)
		lines = (result.stdout or '').splitlines()
		for line in lines:
			line = line.strip()
			if not line:
				continue
			# app name is the first whitespace-separated token
			app_name = line.split()[0]
			if app_name and app_name not in installed_apps:
				installed_apps.append(app_name)
	except Exception as e:
		print(f"Error running bench list-apps for site '{site_name}': {e}")

	# Fallback 1: DB query
	if not installed_apps:
		try:
			installed_apps_docs = frappe.get_all('Installed Application', fields=['app_name'])
			installed_apps = [d.app_name for d in installed_apps_docs if d.app_name]
		except Exception as e:
			print(f"Error reading Installed Applications: {e}")

	return installed_apps


def create_custom_app_dependency(dep_name: str) -> Dict[str, str]:
	return {
		"dependency_name": dep_name,
		"dependency_version": "",
		"dependency_type": "required",
	}


# Public wrappers for reuse outside this module
def get_current_site() -> str:
	return _get_site_name_safe()


def bench_paths() -> Dict[str, str]:
	return _bench_paths()


def guess_app_dir_name_from_repo(repo_url: str) -> Optional[str]:
	name = repo_url.rstrip("/")
	name = name.split(":")[-1]
	name = name.split("/")[-1]
	if name.endswith(".git"):
		name = name[:-4]
	return name or None


def get_app_version_from_init(app_path: str, app_name: str) -> str:
	"""Get the version from the app's __init__.py file."""
	init_path = os.path.join(app_path, app_name, '__init__.py')
	if not os.path.exists(init_path):
		return '0.0.1'
	
	try:
		with open(init_path, 'r') as f:
			content = f.read()
			# Look for __version__ = "version" pattern
			import re
			match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
			if match:
				return match.group(1)
	except Exception:
		pass
	
	return '0.0.1'


def upsert_custom_app_from_dir(app_name: str) -> Dict[str, Any]:
	"""Upsert a single `Frappe Custom App` document based on an app in bench.

	- Reads metadata from `<apps>/<app_name>/<app_name>/hooks.py`
	- Determines version from `<apps>/<app_name>/<app_name>/__init__.py` (__version__)
	- Falls back to site or global `apps.json` if version not found in __init__.py
	- Determines status based on installation for current site
	- Respects `force`: if False and doc exists, it will skip

	Returns a dict with keys: action (created|updated|skipped), app_name, doc (optional)
	"""
	site_name = _get_site_name_safe()
	paths = _bench_paths()
	project_root = paths['bench_root']
	apps_dir = paths['apps_dir']
	sites_dir = paths['sites_dir']

	if app_name == 'frappe':
		return {"action": "skipped", "reason": "core_app", "app_name": app_name}

	app_path = os.path.join(apps_dir, app_name)
	hooks_path = os.path.join(app_path, app_name, 'hooks.py')
	info = parse_hooks_file(hooks_path)
	if not info.get('app_name'):
		return {"action": "skipped", "reason": "no_hooks", "app_name": app_name}

	# Version and repo
	# First try to get version from __init__.py
	version = get_app_version_from_init(app_path, app_name)
	repo_url = get_git_remote_url(app_path) or ''
	
	# Fallback to apps.json if needed (for backward compatibility)
	site_apps_json_path = os.path.join(sites_dir, site_name, 'apps.json')
	global_apps_json_path = os.path.join(sites_dir, 'apps.json')
	apps_json = load_apps_json(site_apps_json_path) or load_apps_json(global_apps_json_path)
	resolved_app_name = info.get('app_name', app_name)
	if resolved_app_name in apps_json and version == '0.0.1':
		# Only use apps.json version if we couldn't find version in __init__.py
		version = apps_json[resolved_app_name].get('version', version)

	# Installed status
	installed_apps = get_installed_apps_for_site(site_name, project_root)
	is_installed = app_name in installed_apps

	# Upsert
	existing = frappe.db.exists('Frappe Custom App', { 'app_name': resolved_app_name })

	if existing:
		doc = frappe.get_doc('Frappe Custom App', str(existing))
		action = 'updated'
	else:
		doc = frappe.new_doc('Frappe Custom App')
		action = 'created'

	doc.set('app_name', resolved_app_name)
	doc.set('description', info.get('app_description', ''))
	doc.set('icon', info.get('app_icon', ''))
	doc.set('version', version)
	doc.set('repo_url', repo_url)
	doc.set('status', 'Installed' if is_installed else 'Available')

	# Dependencies
	doc.set('dependencies', [])
	for dep in info.get('required_apps', []) or []:
		if dep != 'frappe':
			doc.append('dependencies', create_custom_app_dependency(dep))

	doc.save()
	frappe.db.commit()

	return {"action": action, "app_name": resolved_app_name, "doc": doc.name}


def scan_and_sync_custom_apps() -> Dict[str, Any]:
	"""Scan bench apps and upsert Frappe Custom App docs with status and deps."""
	paths = _bench_paths()
	apps_dir = paths['apps_dir']

	all_apps = get_apps_from_directory(apps_dir)
	results: Dict[str, Any] = {"updated": [], "created": []}

	for app_name in all_apps:
		res = upsert_custom_app_from_dir(app_name)
		if not res:
			continue
		action = res.get('action')
		if action == 'updated' and res.get('doc'):
			results['updated'].append(res['doc'])
		elif action == 'created':
			results['created'].append(res.get('app_name'))

	return results


