"""Configuration settings for agent memory operations.

Defines paths and size limits for files, directories, and total memory.
"""

import os

# Path to memory directory for storing agent files
# Can be overridden via environment variable
MEMORY_PATH = os.getenv("MEMORY_PATH", "memory_dir")

# Single file size limit (1MB)
FILE_SIZE_LIMIT = 1024 * 1024

# Single directory size limit (10MB)
DIR_SIZE_LIMIT = 1024 * 1024 * 10

# Total memory size limit (100MB)
MEMORY_SIZE_LIMIT = 1024 * 1024 * 100

