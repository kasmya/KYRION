"""
File compression utility supporting ZIP, GZIP, and TAR formats.

This module provides functions to compress files and directories, decompress archives,
and list archive contents. It supports ZIP, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, and GZIP
(single file) formats. Security best practices are followed to prevent path traversal
and archive extraction vulnerabilities.

Example usage:
    >>> from compression_util import compress_files, decompress, list_archive
    >>> compress_files(["file1.txt", "file2.txt"], "archive.zip")
    >>> decompress("archive.zip", "output_dir")
    >>> print(list_archive("archive.zip"))
"""

import os
import sys
import zipfile
import tarfile
import gzip
import shutil
from pathlib import Path
from typing import List, Union, Optional, Tuple, BinaryIO


class CompressionError(Exception):
    """Base exception for compression-related errors."""
    pass


class DecompressionError(Exception):
    """Base exception for decompression-related errors."""
    pass


class ArchiveFormatError(ValueError):
    """Raised when an unsupported or unrecognized archive format is encountered."""
    pass


def _normalize_path(path: Union[str, Path]) -> Path:
    """Convert a path to an absolute Path object, resolving symlinks."""
    return Path(path).expanduser().resolve()


def _validate_files_exist(files: List[Union[str, Path]]) -> List[Path]:
    """Ensure all provided files exist and are readable. Returns list of resolved Paths."""
    resolved = []
    for f in files:
        p = _normalize_path(f)
        if not p.is_file():
            raise CompressionError(f"File not found or not a regular file: {p}")
        resolved.append(p)
    return resolved


def _validate_directory(directory: Union[str, Path]) -> Path:
    """Ensure the provided directory exists and is readable."""
    p = _normalize_path(directory)
    if not p.is_dir():
        raise CompressionError(f"Directory not found or not a directory: {p}")
    return p


def _infer_format(archive_path: Union[str, Path], explicit_format: Optional[str] = None) -> str:
    """
    Determine archive format from extension or explicit format argument.

    Supported formats: zip, tar, tar.gz, tgz, tar.bz2, tbz2, tar.xz, txz, gz.
    """
    if explicit_format:
        fmt = explicit_format.lower()
        if fmt in {"zip", "tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz", "gz"}:
            return fmt
        raise ArchiveFormatError(f"Unsupported format: {explicit_format}")

    path = Path(archive_path)
    suffixes = path.suffixes
    if path.suffix == ".zip":
        return "zip"
    if path.suffix == ".gz" and len(suffixes) == 1:
        return "gz"
    if path.suffix in {".tar", ".tgz", ".tbz2", ".txz"}:
        return path.suffix[1:]  # remove leading dot
    if len(suffixes) >= 2:
        combined = "".join(suffixes[-2:])
        if combined in {".tar.gz", ".tar.bz2", ".tar.xz"}:
            return combined[1:]
    raise ArchiveFormatError(f"Cannot infer archive format from filename: {archive_path}")


def _safe_extract_zip(zip_file: zipfile.ZipFile, destination: Path) -> None:
    """
    Safely extract a ZIP archive, preventing path traversal and absolute paths.

    Args:
        zip_file: Open ZipFile object in read mode.
        destination: Destination directory (must exist).

    Raises:
        DecompressionError: If any member attempts to escape the destination.
    """
    destination = destination.resolve()
    for member in zip_file.infolist():
        # Skip directories (they will be created by extracting files)
        if member.is_dir():
            continue
        # Resolve target path
        target_path = (destination / member.filename).resolve()
        # Ensure target is within destination
        try:
            target_path.relative_to(destination)
        except ValueError:
            raise DecompressionError(f"Path traversal attempt detected in ZIP member: {member.filename}")
    # If all members are safe, extract
    zip_file.extractall(destination)


def _safe_extract_tar(tar_file: tarfile.TarFile, destination: Path) -> None:
    """
    Safely extract a TAR archive, preventing path traversal and absolute paths.

    Args:
        tar_file: Open TarFile object in read mode.
        destination: Destination directory (must exist).

    Raises:
        DecompressionError: If any member attempts to escape the destination.
    """
    destination = destination.resolve()
    for member in tar_file.getmembers():
        # Skip non-regular files (symlinks, devices, etc.) for safety
        if not member.isfile():
            continue
        target_path = (destination / member.name).resolve()
        try:
            target_path.relative_to(destination)
        except ValueError:
            raise DecompressionError(f"Path traversal attempt detected in TAR member: {member.name}")
    # Extract only regular files (safe)
    tar_file.extractall(destination, members=[m for m in tar_file.getmembers() if m.isfile()])


def compress_files(
    files: List[Union[str, Path]],
    archive_path: Union[str, Path],
    format: Optional[str] = None,
    compression_level: int = 6,
) -> None:
    """
    Compress multiple files into a single archive.

    Args:
        files: List of file paths to compress. Each must be a regular file.
        archive_path: Output archive path. Extension determines format if `format` is None.
        format: Explicit archive format (zip, tar, tar.gz, tgz, tar.bz2, tbz2, tar.xz, txz, gz).
                If None, inferred from `archive_path` extension.
        compression_level: Compression level (0-9) for formats that support it (gzip, bz2, xz, zip).
                           Default is 6.

    Raises:
        CompressionError: If any file is missing, format unsupported, or compression fails.
        ArchiveFormatError: If format cannot be determined or is unsupported.

    Security:
        - Validates that all input files exist and are regular files.
        - Does not follow symlinks (uses resolved absolute paths).
        - Archives store relative paths only (no absolute paths).
    """
    if not files:
        raise CompressionError("No files provided for compression")

    resolved_files = _validate_files_exist(files)
    archive_path = _normalize_path(archive_path)
    fmt = _infer_format(archive_path, format)

    # Ensure parent directory exists
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if fmt == "zip":
            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level
            ) as zf:
                for file_path in resolved_files:
                    # Store with relative name (basename) to avoid path traversal in archive
                    arcname = file_path.name
                    zf.write(file_path, arcname=arcname)

        elif fmt in {"tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz"}:
            mode_map = {
                "tar": "w",
                "tar.gz": "w:gz",
                "tgz": "w:gz",
                "tar.bz2": "w:bz2",
                "tbz2": "w:bz2",
                "tar.xz": "w:xz",
                "txz": "w:xz",
            }
            mode = mode_map[fmt]
            with tarfile.open(archive_path, mode) as tf:
                for file_path in resolved_files:
                    arcname = file_path.name
                    tf.add(file_path, arcname=arcname)

        elif fmt == "gz":
            if len(resolved_files) != 1:
                raise CompressionError("GZIP format only supports compressing a single file")
            file_path = resolved_files[0]
            with open(file_path, "rb") as f_in:
                with gzip.open(archive_path, "wb", compresslevel=compression_level) as f_out:
                    shutil.copyfileobj(f_in, f_out)

        else:
            raise ArchiveFormatError(f"Unsupported format: {fmt}")

    except (OSError, zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile) as e:
        raise CompressionError(f"Compression failed: {e}") from e


def compress_directory(
    directory: Union[str, Path],
    archive_path: Union[str, Path],
    format: Optional[str] = None,
    compression_level: int = 6,
) -> None:
    """
    Compress an entire directory recursively into an archive.

    Args:
        directory: Path to the directory to compress.
        archive_path: Output archive path. Extension determines format if `format` is None.
        format: Explicit archive format (zip, tar, tar.gz, tgz, tar.bz2, tbz2, tar.xz, txz).
                GZIP (gz) is not supported for directories.
        compression_level: Compression level (0-9) for formats that support it.

    Raises:
        CompressionError: If directory missing, format unsupported, or compression fails.
        ArchiveFormatError: If format is gz or cannot be determined.

    Security:
        - Validates directory exists and is readable.
        - Archives store relative paths from the directory root.
        - Does not follow symlinks outside the directory (uses tarfile/zipfile default behavior).
    """
    dir_path = _validate_directory(directory)
    archive_path = _normalize_path(archive_path)
    fmt = _infer_format(archive_path, format)

    if fmt == "gz":
        raise ArchiveFormatError("GZIP format does not support directory compression")

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if fmt == "zip":
            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level
            ) as zf:
                for root, _, files in os.walk(dir_path):
                    for file in files:
                        file_path = Path(root) / file
                        # Compute relative path from the directory root
                        arcname = file_path.relative_to(dir_path)
                        zf.write(file_path, arcname=arcname.as_posix())

        elif fmt in {"tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz"}:
            mode_map = {
                "tar": "w",
                "tar.gz": "w:gz",
                "tgz": "w:gz",
                "tar.bz2": "w:bz2",
                "tbz2": "w:bz2",
                "tar.xz": "w:xz",
                "txz": "w:xz",
            }
            mode = mode_map[fmt]
            with tarfile.open(archive_path, mode) as tf:
                tf.add(dir_path, arcname=dir_path.name)

        else:
            raise ArchiveFormatError(f"Unsupported format: {fmt}")

    except (OSError, zipfile.BadZipFile, tarfile.TarError) as e:
        raise CompressionError(f"Directory compression failed: {e}") from e


def decompress(
    archive_path: Union[str, Path],
    destination: Union[str, Path],
    format: Optional[str] = None,
) -> None:
    """
    Decompress an archive to a destination directory.

    Args:
        archive_path: Path to the archive file.
        destination: Directory where contents will be extracted. Created if it doesn't exist.
        format: Explicit archive format (zip, tar, tar.gz, tgz, tar.bz2, tbz2, tar.xz, txz, gz).
                If None, inferred from `archive_path` extension.

    Raises:
        DecompressionError: If archive is corrupt, format unsupported, or extraction fails.
        ArchiveFormatError: If format cannot be determined or is unsupported.

    Security:
        - Prevents path traversal (absolute paths, '..' components).
        - Does not extract symlinks, device files, or other special files.
        - Validates that all extracted paths remain within the destination directory.
    """
    archive_path = _normalize_path(archive_path)
    if not archive_path.is_file():
        raise DecompressionError(f"Archive not found: {archive_path}")

    destination = _normalize_path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    fmt = _infer_format(archive_path, format)

    try:
        if fmt == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                _safe_extract_zip(zf, destination)

        elif fmt in {"tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz"}:
            mode_map = {
                "tar": "r",
                "tar.gz": "r:gz",
                "tgz": "r:gz",
                "tar.bz2": "r:bz2",
                "tbz2