"""
hashing.py — Module 2: SHA-256 file hashing.

Provides a single public function that calculates the SHA-256 digest of a
file's content.  Used by the watcher to populate the ``hash`` field of every
synchronisation event.
"""

import hashlib
from pathlib import Path


_CHUNK_SIZE = 65_536  # 64 KiB — large enough to be efficient, small enough for RAM


def sha256_file(path: str | Path) -> str:
    """Return the lowercase hex SHA-256 digest of the file at *path*.

    Reads the file in chunks to avoid loading large files into memory at once.

    Raises:
        FileNotFoundError: if *path* does not exist.
        IsADirectoryError: if *path* is a directory.
        OSError: for other I/O errors.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
