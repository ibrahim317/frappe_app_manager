"""Command execution service implementation."""

from typing import List
import frappe
from frappe.utils import execute_in_shell

from app_manager.services.interfaces import CommandExecutorInterface, CommandResult


class FrappeCommandExecutor(CommandExecutorInterface):
    """Command executor using Frappe's execute_in_shell utility."""
    
    def execute(self, cmd: List[str]) -> CommandResult:
        """Execute a shell command and return the result."""
        err, out = execute_in_shell(cmd, check_exit_code=False)
        return CommandResult(
            ok=bool(not err),
            stdout=(out or b"").decode(errors="replace"),
            stderr=(err or b"").decode(errors="replace")
        )
