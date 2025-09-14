import frappe
from app_manager.app_manager.utils.apps_scan import scan_and_sync_custom_apps

def after_install():
    populate_app_manager_data()
    frappe.db.commit()

def populate_app_manager_data():
    """Populate the Frappe Custom App doctype with data from all custom apps."""
    print("🔍 Scanning custom apps for App Manager...")
    scan_and_sync_custom_apps()
    print(f"\n✅ Successfully populated Frappe Custom App data!")
