"""Notification service implementation."""

import frappe
from typing import Any

from app_manager.services.interfaces import NotificationInterface


class FrappeNotificationService(NotificationInterface):
    """Notification service using Frappe's realtime messaging."""
    
    def send_progress_update(self, status: str, message: str, app_name: str, 
                           user: str, **kwargs) -> None:
        """Send a progress update notification."""
        data = {
            "status": status,
            "message": message,
            "app_name": app_name,
            **kwargs
        }
        
        frappe.publish_realtime(
            "app_manager_progress",
            data,
            user=user
        )
