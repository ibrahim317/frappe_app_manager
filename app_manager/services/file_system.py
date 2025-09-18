"""File system operations service implementation."""

import os
import shutil
from typing import List

from app_manager.services.interfaces import FileSystemInterface


class OSFileSystem(FileSystemInterface):
    """File system operations using Python's os module."""
    
    def exists(self, path: str) -> bool:
        """Check if a path exists."""
        return os.path.exists(path)
    
    def is_dir(self, path: str) -> bool:
        """Check if a path is a directory."""
        return os.path.isdir(path)
    
    def list_dir(self, path: str) -> List[str]:
        """List directory contents."""
        if not self.exists(path):
            return []
        return os.listdir(path)
    
    def read_file(self, path: str, encoding: str = 'utf-8') -> str:
        """Read file contents."""
        with open(path, 'r', encoding=encoding) as f:
            return f.read()
    
    def write_file(self, path: str, content: str, encoding: str = 'utf-8') -> None:
        """Write content to a file."""
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
    
    def append_file(self, path: str, content: str, encoding: str = 'utf-8') -> None:
        """Append content to a file."""
        with open(path, 'a', encoding=encoding) as f:
            f.write(content)
    
    def remove_tree(self, path: str) -> None:
        """Remove a directory tree."""
        shutil.rmtree(path)
