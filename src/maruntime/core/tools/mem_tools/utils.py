"""Utility functions for checking file and directory sizes.

Contains functions for enforcing size limits during file system operations.
"""

import os

from maruntime.core.tools.mem_tools.settings import (
    DIR_SIZE_LIMIT,
    FILE_SIZE_LIMIT,
    MEMORY_PATH,
    MEMORY_SIZE_LIMIT,
)


def check_file_size_limit(file_path: str) -> bool:
    """Check if file size is within limit.

    Args:
        file_path: Path to file to check

    Returns:
        True if file size is within limit, False otherwise
    """
    return os.path.getsize(file_path) <= FILE_SIZE_LIMIT


def check_dir_size_limit(dir_path: str) -> bool:
    """Check if directory size is within limit.

    Args:
        dir_path: Path to directory to check

    Returns:
        True if directory size is within limit, False otherwise
    """
    total_size = 0
    for dirpath, _, filenames in os.walk(dir_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(file_path)
            except OSError:
                pass
    return total_size <= DIR_SIZE_LIMIT


def check_memory_size_limit() -> bool:
    """Check if total memory size is within limit.

    Returns:
        True if total memory size is within limit, False otherwise
    """
    if not os.path.exists(MEMORY_PATH):
        return True
    total_size = 0
    for dirpath, _, filenames in os.walk(MEMORY_PATH):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(file_path)
            except OSError:
                pass
    return total_size <= MEMORY_SIZE_LIMIT


def check_size_limits(file_or_dir_path: str) -> bool:
    """Check all applicable size limits for a given path.

    Args:
        file_or_dir_path: Path to file or directory to check

    Returns:
        True if all limits are satisfied, False otherwise
    """
    if not file_or_dir_path:
        return check_memory_size_limit()
    elif os.path.isdir(file_or_dir_path):
        return check_dir_size_limit(file_or_dir_path) and check_memory_size_limit()
    elif os.path.isfile(file_or_dir_path):
        parent_dir = os.path.dirname(file_or_dir_path)
        if parent_dir:
            return (
                check_file_size_limit(file_or_dir_path)
                and check_dir_size_limit(parent_dir)
                and check_memory_size_limit()
            )
        else:
            return check_file_size_limit(file_or_dir_path) and check_memory_size_limit()
    else:
        return False

