"""
File Compression Utility Module

Provides functionality to compress and decompress files and directories
using ZIP, GZIP, and TAR formats. Supports listing archive contents.
All operations are performed with security best practices in mind,
including path traversal prevention and safe file handling.
"""

import os
import tarfile
import gzip
import zipfile
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Union, Literal

ArchiveFormat = Literal["zip", "gzip", "tar"]


def _sanitize_member_path(member_name: str, target_dir: str) -> str:
    """
    Validate and sanitize an archive member path to prevent path traversal attacks.

    Args:
        member_name: The original path of the member inside the archive.
        target_dir: The directory where extraction is taking place.

    Returns:
        The sanitized absolute path for extraction.

    Raises:
        ValueError: If the member path attempts to escape the target directory.
    """
    target_dir_real = os.path.realpath(target_dir)
    member_path = os.path.realpath(os.path.join(target_dir_real, member_name))
    if not member_path.startswith(target_dir_real + os.sep) and member_path != target_dir_real:
        raise ValueError(f"Path traversal detected: '{member_name}' escapes target directory.")
    return member_path


def compress_files(
    source_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    format: ArchiveFormat = "zip",
    compression_level: Optional[int] = None,
) -> None:
    """
    Compress multiple files into a single archive.

    Args:
        source_paths: List of file paths to include in the archive.
        output_path: Path where the output archive will be created.
        format: Archive format ('zip', 'gzip', 'tar').
        compression_level: Compression level (0-9 for gzip/zip, ignored for tar).
                           Defaults to default compression for each format.

    Raises:
        FileNotFoundError: If any source file does not exist.
        ValueError: If an unsupported format is specified or compression level is invalid.
        OSError: For filesystem-related errors during compression.
    """
    source_paths = [Path(p).resolve() for p in source_paths]
    output_path = Path(output_path).resolve()

    # Validate all source files exist and are files
    for src in source_paths:
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")
        if not src.is_file():
            raise ValueError(f"Source path is not a file: {src}")

    if format == "zip":
        compress_kwargs = {}
        if compression_level is not None:
            if not 0 <= compression_level <= 9:
                raise ValueError("Compression level must be between 0 and 9 for ZIP format.")
            compress_kwargs["compresslevel"] = compression_level
        else:
            compress_kwargs["compresslevel"] = zipfile.ZIP_DEFLATED

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, **compress_kwargs) as zf:
            for src in source_paths:
                zf.write(src, arcname=src.name)

    elif format == "gzip":
        if len(source_paths) != 1:
            raise ValueError("GZIP format supports compressing only a single file.")
        src = source_paths[0]
        compress_kwargs = {}
        if compression_level is not None:
            if not 0 <= compression_level <= 9:
                raise ValueError("Compression level must be between 0 and 9 for GZIP format.")
            compress_kwargs["compresslevel"] = compression_level

        with open(src, 'rb') as f_in:
            with gzip.open(output_path, 'wb', **compress_kwargs) as f_out:
                shutil.copyfileobj(f_in, f_out)

    elif format == "tar":
        with tarfile.open(output_path, 'w') as tf:
            for src in source_paths:
                tf.add(src, arcname=src.name)

    else:
        raise ValueError(f"Unsupported compression format: {format}")


def compress_directory(
    source_dir: Union[str, Path],
    output_path: Union[str, Path],
    format: ArchiveFormat = "zip",
    compression_level: Optional[int] = None,
) -> None:
    """
    Compress an entire directory recursively into an archive.

    Args:
        source_dir: Path to the directory to compress.
        output_path: Path where the output archive will be created.
        format: Archive format ('zip', 'gzip', 'tar').
        compression_level: Compression level (0-9 for zip, ignored for tar/gzip).

    Raises:
        FileNotFoundError: If the source directory does not exist.
        NotADirectoryError: If source_dir is not a directory.
        ValueError: If format is unsupported or compression level is invalid.
        OSError: For filesystem-related errors during compression.
    """
    source_dir = Path(source_dir).resolve()
    output_path = Path(output_path).resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

    if format == "zip":
        compress_kwargs = {}
        if compression_level is not None:
            if not 0 <= compression_level <= 9:
                raise ValueError("Compression level must be between 0 and 9 for ZIP format.")
            compress_kwargs["compresslevel"] = compression_level
        else:
            compress_kwargs["compresslevel"] = zipfile.ZIP_DEFLATED

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, **compress_kwargs) as zf:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(source_dir)
                    zf.write(file_path, arcname=str(arcname))

    elif format == "gzip":
        # GZIP only compresses a single file, so create a tar.gz (compressed tar)
        with tarfile.open(output_path, 'w:gz', compresslevel=compression_level or 9) as tf:
            tf.add(source_dir, arcname=source_dir.name)

    elif format == "tar":
        with tarfile.open(output_path, 'w') as tf:
            tf.add(source_dir, arcname=source_dir.name)

    else:
        raise ValueError(f"Unsupported compression format: {format}")


def decompress(
    archive_path: Union[str, Path],
    output_dir: Union[str, Path],
    format: Optional[ArchiveFormat] = None,
) -> None:
    """
    Decompress an archive to the specified output directory.

    Args:
        archive_path: Path to the archive file.
        output_dir: Directory where the contents will be extracted.
        format: Archive format ('zip', 'gzip', 'tar'). If None, auto-detect from extension.

    Raises:
        FileNotFoundError: If the archive does not exist.
        ValueError: If format cannot be determined or is unsupported.
        OSError: For filesystem-related errors during decompression.
        RuntimeError: If a path traversal attempt is detected.
    """
    archive_path = Path(archive_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    if not archive_path.is_file():
        raise ValueError(f"Archive path is not a file: {archive_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-detect format if not provided
    if format is None:
        suffix = archive_path.suffix.lower()
        if suffix == '.zip':
            format = 'zip'
        elif suffix == '.gz':
            # Could be gzip or tar.gz
            if archive_path.suffixes[-2:] == ['.tar', '.gz']:
                format = 'tar'
            else:
                format = 'gzip'
        elif suffix in ('.tar', '.tgz', '.tbz2', '.txz'):
            format = 'tar'
        else:
            raise ValueError(f"Cannot determine archive format from extension: {archive_path.suffix}")

    if format == "zip":
        with zipfile.ZipFile(archive_path, 'r') as zf:
            for member in zf.infolist():
                # Prevent path traversal
                target_path = _sanitize_member_path(member.filename, str(output_dir))
                if member.is_dir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zf.open(member) as source, open(target_path, 'wb') as dest:
                        shutil.copyfileobj(source, dest)

    elif format == "gzip":
        # GZIP decompresses a single file, output name derived from archive name
        output_filename = archive_path.stem  # remove .gz
        output_file_path = output_dir / output_filename
        with gzip.open(archive_path, 'rb') as f_in:
            with open(output_file_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

    elif format == "tar":
        with tarfile.open(archive_path, 'r:*') as tf:
            # Validate all members before extraction
            for member in tf.getmembers():
                _sanitize_member_path(member.name, str(output_dir))

            # Extract safely
            for member in tf.getmembers():
                target_path = _sanitize_member_path(member.name, str(output_dir))
                if member.isdir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with tf.extractfile(member) as source:
                        if source is not None:
                            with open(target_path, 'wb') as dest:
                                shutil.copyfileobj(source, dest)

    else:
        raise ValueError(f"Unsupported decompression format: {format}")


def list_contents(
    archive_path: Union[str, Path],
    format: Optional[ArchiveFormat] = None,
) -> List[str]:
    """
    List the contents of an archive without extracting.

    Args:
        archive_path: Path to the archive file.
        format: Archive format ('zip', 'gzip', 'tar'). If None, auto-detect.

    Returns:
        A list of member names (paths) inside the archive.

    Raises:
        FileNotFoundError: If the archive does not exist.
        ValueError: If format cannot be determined or is unsupported.
        OSError: For filesystem-related errors during reading.
    """
    archive_path = Path(archive_path).resolve()

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    if not archive_path.is_file():
        raise ValueError(f"Archive path is not a file: {archive_path}")

    # Auto-detect format if not provided
    if format is None:
        suffix = archive_path.suffix.lower()
        if suffix == '.zip':
            format = 'zip'
        elif suffix == '.gz':
            if archive_path.suffixes[-2:] == ['.tar', '.gz']:
                format = 'tar'
            else:
                format = 'gzip'
        elif suffix in ('.tar', '.tgz', '.tbz2', '.txz'):
            format = 'tar'
        else:
            raise ValueError(f"Cannot determine archive format from extension: {archive_path.suffix}")

    contents: List[str] = []

    if format == "zip":
        with zipfile.ZipFile(archive_path, 'r') as zf:
            contents = [info.filename for info in zf.infolist()]

    elif format == "gzip":
        # GZIP contains only a single file, name is the archive name minus .gz
        contents = [archive_path.stem]

    elif format == "tar":
        with tarfile.open(archive_path, 'r:*') as tf:
            contents = [member.name for member in tf.getmembers()]

    else:
        raise ValueError(f"Unsupported format for listing: {format}")

    return contents