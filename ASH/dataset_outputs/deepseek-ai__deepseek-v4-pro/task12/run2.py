"""
File-compression utility supporting ZIP, GZIP, and TAR archives.

Provides functions to compress files and directories into ZIP, GZIP, or TAR
archives, decompress them, and list their contents. Designed with security
best practices: path traversal prevention, input validation, and safe file
handling.
"""

import os
import tarfile
import zipfile
import gzip
import shutil
import tempfile
from typing import List, Optional, Union
from pathlib import Path


def _validate_path(base_dir: Path, member_path: Path) -> Path:
    """
    Validate that a member path does not escape a base directory.

    Args:
        base_dir: The intended base directory.
        member_path: A relative or absolute path to validate.

    Returns:
        The resolved absolute path of the member if it is safe.

    Raises:
        ValueError: If the member_path attempts to traverse outside base_dir.
    """
    # Resolve to absolute paths to avoid symlink/relative trickery
    resolved_base = base_dir.resolve()
    resolved_member = (resolved_base / member_path).resolve()

    # Ensure the resolved member is inside the base directory
    if not str(resolved_member).startswith(str(resolved_base) + os.sep) and resolved_member != resolved_base:
        raise ValueError(f"Path traversal detected: {member_path}")
    return resolved_member


def compress_file_zip(source: str, archive_path: str, arcname: Optional[str] = None) -> None:
    """
    Compress a single file into a ZIP archive.

    Args:
        source: Path to the file to compress.
        target: Path to the output ZIP file.
        arcname: Alternative name for the file inside the archive. Uses
                 the source basename if None.

    Raises:
        FileNotFoundError: If source does not exist.
        IsADirectoryError: If source is a directory.
        OSError: On filesystem errors during compression.
    """
    source_path = Path(source).resolve()
    target_path = Path(target).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    if source_path.is_dir():
        raise IsADirectoryError(f"Source is a directory, not a file: {source}")

    if arcname is None:
        arcname = source_path.name

    try:
        with zipfile.ZipFile(target_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(source_path, arcname=arcname)
    except (OSError, zipfile.BadZipFile) as e:
        raise OSError(f"Failed to create ZIP archive {target}: {e}")


def compress_directory_zip(source: str, target: str) -> None:
    """
    Compress a directory recursively into a ZIP archive.

    Args:
        source: Path to the directory to compress.
        target: Path to the output ZIP file.

    Raises:
        FileNotFoundError: If source does not exist.
        NotADirectoryError: If source is not a directory.
        OSError: If filesystem errors occur.
    """
    source_path = Path(source).resolve()
    target_path = Path(target).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source directory not found: {source}")
    if not source_path.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {source}")

    try:
        with zipfile.ZipFile(target_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source_path):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(source_path)
                    zf.write(file_path, arcname=str(arcname))
    except (zipfile.BadZipFile, OSError) as e:
        raise OSError(f"Failed to create ZIP archive from directory {source}: {e}")


def compress_file_gzip(source: str, target: str) -> None:
    """
    Compress a single file using GZIP.

    Args:
        source: Path to the file to compress.
        target: Path to the output .gz file.

    Raises:
        FileNotFoundError: If source does not exist.
        IsADirectoryError: If source is a directory.
        OSError: On write errors.
    """
    source_path = Path(source).resolve()
    target_path = Path(target).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    if source_path.is_dir():
        raise IsADirectoryError(f"Source is a directory, not a file: {source}")

    try:
        with open(source_path, 'rb') as f_in:
            with gzip.open(target_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    except OSError as e:
        raise OSError(f"Failed to create GZIP file {target}: {e}")


def compress_directory_tar(source: str, target: str) -> None:
    """
    Compress a directory into a TAR archive (uncompressed).

    Args:
        source: Path to the directory.
        target: Path to the output .tar file.

    Raises:
        FileNotFoundError: If source does not exist.
        NotADirectoryError: If source is not a directory.
        OSError: On write errors.
    """
    source_path = Path(source).resolve()
    target_path = Path(target).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source directory not found: {source}")
    if not source_path.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {source}")

    try:
        with tarfile.open(target_path, 'w') as tar:
            tar.add(source_path, arcname=source_path.name)
    except tarfile.TarError as e:
        raise OSError(f"Failed to create TAR archive {target}: {e}")


def decompress_zip(source: str, target_dir: str) -> None:
    """
    Decompress a ZIP archive into a target directory.

    Args:
        source: Path to the ZIP archive.
        target_dir: Directory to extract files into.

    Raises:
        FileNotFoundError: If source archive does not exist.
        OSError: On extraction errors.
        ValueError: If path traversal is detected in archive members.
    """
    source_path = Path(source).resolve()
    target_path = Path(target_dir).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"ZIP archive not found: {source}")

    # Create target directory if it doesn't exist
    target_path.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(source_path, 'r') as zf:
            for member in zf.infolist():
                # Validate against path traversal
                member_path = Path(member.filename)
                # Remove leading slashes / absolute paths
                if member_path.is_absolute():
                    member_path = member_path.relative_to('/')
                safe_path = _validate_path_exists(target_path, member_path)

                zf.extract(member, path=str(target_path))
    except (zipfile.BadZipFile, OSError) as e:
        raise OSError(f"Failed to decompress ZIP {source}: {e}")


def decompress_gzip(source: str, target: Optional[str] = None) -> None:
    """
    Decompress a GZIP file.

    Args:
        source: Path to the .gz file.
        target: Path for the decompressed output. If None, derives from source
                by stripping .gz extension.

    Raises:
        FileNotFoundError: If source does not exist.
        OSError: On read/write errors.
    """
    source_path = Path(source).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"GZIP file not found: {source}")

    if target is None:
        if source_path.suffix != '.gz':
            raise ValueError("Source does not have .gz extension and no target specified.")
        target_path = source_path.with_suffix('')
    else:
        target_path = Path(target).resolve()

    try:
        with gzip.open(source_path, 'rb') as f_in:
            with open(target_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    except OSError as e:
        raise OSError(f"Failed to decompress GZIP {source}: {e}")


def decompress_tar(source: str, target_dir: str) -> None:
    """
    Decompress a TAR archive into a target directory.

    Args:
        source: Path to the .tar file.
        target_dir: Directory to extract files into.

    Raises:
        FileNotFoundError: If source archive does not exist.
        OSError: On extraction errors.
        ValueError: If path traversal is detected in archive members.
    """
    source_path = Path(source).resolve()
    target_path = Path(target_dir).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"TAR archive not found: {source}")

    target_path.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(source_path, 'r') as tar:
            # Security: check each member before extracting
            for member in tar.getmembers():
                # Prevent absolute paths and path traversal
                if member.islnk() or member.issym():
                    raise ValueError(f"Symlinks/hardlinks not allowed: {member.name}")
                member_path = Path(member.name)
                if member_path.is_absolute():
                    member_path = member_path.relative_to('/')
                _validate_path_exists(target_path, member_path)

            # Extract with filter (Python 3.12+ has filter parameter, but for compatibility we use manual check)
            tar.extractall(path=str(target_path))
    except tarfile.TarError as e:
        raise OSError(f"Failed to decompress TAR {source}: {e}")


def list_archive_contents(archive_path: str) -> List[str]:
    """
    List the contents of a ZIP, GZIP, or TAR archive.

    Args:
        archive_path: Path to the archive file.

    Returns:
        A list of member names (for TAR/ZIP) or the single file name for GZIP.

    Raises:
        FileNotFoundError: If archive does not exist.
        ValueError: If the archive format is not recognised.
        OSError: On read errors.
    """
    path = Path(archive_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    suffix = path.suffix.lower()
    try:
        if suffix == '.zip':
            with zipfile.ZipFile(path, 'r') as zf:
                return zf.namelist()
        elif suffix == '.gz':
            # GZIP only contains one file; return the original filename
            with gzip.open(path, 'rb') as f:
                # Gzip files store original filename
                return [f.name if f.name else path.stem]
        elif suffix in ('.tar',):
            with tarfile.open(path, 'r') as tar:
                return [member.name for member in tar.getmembers()]
        else:
            raise ValueError(f"Unsupported archive format: {suffix}")
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        raise OSError(f"Failed to list contents of {archive_path}: {e}")