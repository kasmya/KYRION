"""
File Compression Utility Module

This module provides functionality for compressing and decompressing files
and directories using ZIP, GZIP, and TAR formats. It supports creating
archives, extracting them, and listing their contents with proper error
handling and security considerations.
"""

import os
import tarfile
import zipfile
import gzip
import shutil
import tempfile
from typing import List, Optional, Union
from pathlib import Path


def _sanitize_path(base_path: str, member_path: str) -> str:
    """
    Sanitize archive member paths to prevent path traversal attacks.
    
    Args:
        base_path: The base extraction directory.
        member_path: The path of the member within the archive.
        
    Returns:
        A safe, resolved path within the base directory.
        
    Raises:
        ValueError: If the member path attempts to escape the base directory.
    """
    base = Path(base_path).resolve()
    target = (base / member_path).resolve()
    
    # Ensure the target is within the base directory
    if not str(target).startswith(str(base) + os.sep) and str(target) != str(base):
        raise ValueError(f"Path traversal detected: {member_path}")
    
    return str(target)


def _validate_archive_path(archive_path: str) -> None:
    """
    Validate that the archive path is safe for operations.
    
    Args:
        archive_path: Path to the archive file.
        
    Raises:
        ValueError: If the path contains suspicious patterns.
        FileNotFoundError: If the path does not exist for read operations.
    """
    if '..' in Path(archive_path).parts:
        raise ValueError("Archive path contains unsafe traversal patterns")


def compress_file(
    source_path: str,
    archive_path: str,
    format: str = 'zip',
    compression_level: int = 6
) -> None:
    """
    Compress a single file into an archive.
    
    Args:
        source_path: Path to the file to compress.
        archive_path: Path where the archive will be created.
        format: Archive format ('zip', 'gzip', or 'tar').
        compression_level: Compression level (1-9, only applicable for gzip).
        
    Raises:
        FileNotFoundError: If the source file does not exist.
        ValueError: If an unsupported format is specified or path traversal detected.
        OSError: If there are permission issues or disk errors.
    """
    _validate_archive_path(archive_path)
    source = Path(source_path).resolve()
    
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    
    if format not in ('zip', 'gzip', 'tar'):
        raise ValueError(f"Unsupported format: {format}. Use 'zip', 'gzip', or 'tar'.")
    
    try:
        if format == 'zip':
            with zipfile.ZipFile(
                archive_path, 'w',
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=compression_level
            ) as zf:
                zf.write(source, source.name)
        
        elif format == 'gzip':
            with open(source, 'rb') as f_in:
                with gzip.open(archive_path, 'wb', compresslevel=compression_level) as f_out:
                    shutil.copyfileobj(f_in, f_out)
        
        elif format == 'tar':
            with tarfile.open(archive_path, 'w') as tf:
                tf.add(source, source.name)
    
    except (OSError, IOError) as e:
        raise OSError(f"Failed to compress file: {e}")


def compress_directory(
    source_dir: str,
    archive_path: str,
    format: str = 'zip',
    compression_level: Optional[int] = 9
) -> None:
    """
    Compress a directory into an archive.
    
    Args:
        source_dir: Path to the directory to compress.
        archive_path: Path where the compressed archive will be created.
        format: Archive format ('zip' or 'tar').
        compression_level: Compression level for ZIP format.
        
    Returns:
        None
        
    Raises:
        FileNotFoundError: If the source directory does not exist.
        NotADirectoryError: If the source path is not a directory.
        ValueError: If an unsupported format is specified or path traversal detected.
        OSError: If there are issues with file operations.
    """
    _validate_archive_path(archive_path)
    source = Path(source_dir).resolve()
    
    if not source.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    if not source.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")
    
    if format not in ('zip', 'tar'):
        raise ValueError(f"Unsupported format for directory: {format}. Use 'zip' or 'tar'.")
    
    try:
        if format == 'zip':
            with zipfile.ZipFile(
                archive_path, 'w',
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=compression_level
            ) as zf:
                for root, dirs, files in os.walk(source):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(source)
                        zf.write(file_path, arcname)
        
        elif format == 'tar':
            with tarfile.open(archive_path, 'w') as tar:
                tar.add(source, source.name)
    
    except (OSError, IOError) as e:
        raise OSError(f"Failed to compress directory: {e}")


def decompress(
    archive_path: str,
    output_dir: str,
    format: Optional[str] = None
) -> None:
    """
    Decompress an archive to a target directory.
    
    Args:
        archive_path: Path to the compressed archive.
        output_dir: Directory where contents will be extracted.
        format: Archive format ('zip', 'gzip', 'tar'). If None, inferred from extension.
        
    Returns:
        None
        
    Raises:
        FileNotFoundError: If the archive file does not exist.
        ValueError: If the format cannot be determined or path traversal detected.
        OSError: If there are issues during extraction.
    """
    _validate_archive_path(archive_path)
    archive = Path(archive_path).resolve()
    
    if not archive.is_file():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")
    
    # Create output directory if it doesn't exist
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    
    # Determine format if not specified
    if format is None:
        suffix = archive.suffix.lower()
        if suffix == '.zip':
            format = 'zip'
        elif suffix == '.gz':
            format = 'gzip'
        elif suffix in ('.tar', '.tgz', '.tar.gz'):
            format = 'tar'
        else:
            raise ValueError(f"Cannot determine archive format from extension: {suffix}")
    
    if format not in ('zip', 'gzip', 'tar'):
        raise ValueError(f"Unsupported format: {format}")
    
    try:
        if format == 'zip':
            with zipfile.ZipFile(archive, 'r') as zf:
                # Security check: verify all members are safe
                for member in zf.namelist():
                    _sanitize_path(str(output), member)
                zf.extractall(output)
        
        elif format == 'gzip':
            # Gzip only contains a single file
            output_file = output / archive.stem
            with gzip.open(archive, 'rb') as f_in:
                with open(output_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        
        elif format == 'tar':
            with tarfile.open(archive, 'r') as tar:
                # Security check for all members
                for member in tar.getmembers():
                    if not member.isfile() and not member.isdir():
                        continue
                    _sanitize_path(output_dir, member.name)
                tar.extractall(output)
    
    except (OSError, IOError, tarfile.TarError, zipfile.BadZipFile) as e:
        raise OSError(f"Failed to decompress archive: {e}")


def list_contents(archive_path: str, format: Optional[str] = None) -> List[str]:
    """
    List the contents of an archive file.
    
    Args:
        archive_path: Path to the archive file.
        format: Optional format hint ('zip', 'gzip', 'tar'). If None, inferred.
        
    Returns:
        List of file/folder names contained in the archive.
        
    Raises:
        FileNotFoundError: If the archive file does not exist.
        ValueError: If the format cannot be determined or path traversal detected.
        OSError: If there are issues reading the archive.
    """
    _validate_archive_path(archive_path)
    archive = Path(archive_path).resolve()
    
    if not archive.is_file():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")
    
    # Determine format if not specified
    if format is None:
        suffix = archive.suffix.lower()
        if suffix == '.zip':
            format = 'zip'
        elif suffix == '.gz':
            format = 'gzip'
        elif suffix in ('.tar', '.tgz', '.tar.gz'):
            format = 'tar'
        else:
            raise ValueError(f"Cannot determine archive format from extension: {suffix}")
    
    if format not in ('zip', 'gzip', 'tar'):
        raise ValueError(f"Unsupported format: {format}")
    
    contents: List[str] = []
    
    try:
        if format == 'zip':
            with zipfile.ZipFile(archive, 'r') as zf:
                contents = zf.namelist()
        
        elif format == 'gzip':
            # Gzip archives contain a single file with the archive name minus .gz
            contents = [archive.stem]
        
        elif format == 'tar':
            with tarfile.open(archive, 'r') as tar:
                contents = [member.name for member in tar.getmembers()]
    
    except (OSError, IOError, tarfile.TarError, zipfile.BadZipFile) as e:
        raise OSError(f"Failed to list archive contents: {e}")
    
    return contents


# For convenience, provide a unified function
def compress(
    source: str,
    archive_path: str,
    format: str = 'zip',
    compression_level: int = 9
) -> None:
    """
    Compress a file or directory into an archive.
    
    Args:
        source: Path to the file or directory to compress.
        archive_path: Path where the compressed archive will be created.
        format: Archive format ('zip', 'gzip', 'tar').
        compression_level: Compression level (1-9) for applicable formats.
        
    Returns:
        None
        
    Raises:
        FileNotFoundError: If the source does not exist.
        ValueError: If the format is invalid or path traversal detected.
        OSError: If there are issues with file operations.
    """
    source_path = Path(source).resolve()
    
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source}")
    
    if source_path.is_file():
        compress_file(str(source_path), archive_path, format, compression_level)
    elif source_path.is_dir():
        if format == 'gzip':
            raise ValueError("Cannot compress a directory using gzip. Use tar or zip.")
        compress_directory(str(source_path), archive_path, format, compression_level)
    else:
        raise ValueError(f"Source is neither a file nor a directory: {source}")