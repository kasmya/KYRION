#!/usr/bin/env python3
"""
File compression utility supporting ZIP, GZIP, and TAR formats.

Features:
- Compress single files or entire directories.
- Decompress archives safely.
- List archive contents.

Usage (as a script):
    python compress_util.py compress -f zip -o archive.zip /path/to/input
    python compress_util.py decompress -d output_dir archive.zip
    python compress_util.py list archive.tar.gz
"""

import argparse
import gzip
import os
import shutil
import sys
import tarfile
import zipfile
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Union


class ArchiveFormat(Enum):
    """Supported archive formats."""
    ZIP = auto()
    GZIP = auto()   # single file compression
    TAR = auto()    # uncompressed tar
    TAR_GZ = auto() # compressed tar (tar.gz)


def _detect_format_from_extension(file_path: Path) -> Optional[ArchiveFormat]:
    """Detect archive format based on file extension."""
    ext = file_path.suffix.lower()
    if ext == ".zip":
        return ArchiveFormat.ZIP
    if ext == ".gz" and file_path.suffixes[-2:] == [".tar", ".gz"]:
        return ArchiveFormat.TAR_GZ
    if ext == ".tar":
        return ArchiveFormat.TAR
    if ext == ".gz":
        return ArchiveFormat.GZIP
    return None


def compress(
    src: Union[str, Path],
    dest: Union[str, Path],
    fmt: ArchiveFormat,
) -> None:
    """
    Compress a file or directory.

    Args:
        src: Path to source file or directory.
        dest: Destination archive path.
        fmt: Desired archive format.

    Raises:
        FileNotFoundError: If source does not exist.
        ValueError: If format is incompatible with source type.
        OSError: For I/O related errors.
    """
    src_path = Path(src).resolve()
    dest_path = Path(dest).resolve()

    if not src_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {src_path}")

    try:
        if fmt == ArchiveFormat.GZIP:
            if not src_path.is_file():
                raise ValueError("GZIP format only supports single file compression.")
            with src_path.open("rb") as f_in, gzip.open(dest_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        elif fmt == ArchiveFormat.ZIP:
            with zipfile.ZipFile(dest_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                if src_path.is_file():
                    zf.write(src_path, arcname=src_path.name)
                else:
                    for file in src_path.rglob("*"):
                        if file.is_file():
                            arcname = file.relative_to(src_path.parent)
                            zf.write(file, arcname=str(arcname))

        elif fmt in (ArchiveFormat.TAR, ArchiveFormat.TAR_GZ):
            mode = "w:gz" if fmt == ArchiveFormat.TAR_GZ else "w"
            with tarfile.open(dest_path, mode=mode) as tf:
                tf.add(src_path, arcname=src_path.name, recursive=True)

        else:
            raise ValueError(f"Unsupported format: {fmt}")

    except OSError as exc:
        raise OSError(f"Error during compression: {exc}") from exc


def _is_within_directory(directory: Path, target: Path) -> bool:
    """Check that target is inside directory to prevent path traversal."""
    try:
        directory = directory.resolve()
        target = target.resolve()
        return str(target).startswith(str(directory))
    except Exception:
        return False


def _safe_extract_tar(tar: tarfile.TarFile, path: Path) -> None:
    """Extract tar safely, preventing path traversal attacks."""
    for member in tar.getmembers():
        member_path = path / member.name
        if not _is_within_directory(path, member_path):
            raise Exception(f"Attempted Path Traversal in Tar File: {member.name}")
    tar.extractall(path)


def decompress(
    archive: Union[str, Path],
    dest_dir: Union[str, Path],
) -> None:
    """
    Decompress an archive to a destination directory.

    Args:
        archive: Path to the archive file.
        dest_dir: Directory where contents will be extracted.

    Raises:
        FileNotFoundError: If archive does not exist.
        ValueError: If format is unsupported.
        OSError: For I/O errors.
    """
    archive_path = Path(archive).resolve()
    dest_path = Path(dest_dir).resolve()
    dest_path.mkdir(parents=True, exist_ok=True)

    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    fmt = _detect_format_from_extension(archive_path)
    if fmt is None:
        raise ValueError(f"Could not determine archive format for: {archive_path}")

    try:
        if fmt == ArchiveFormat.GZIP:
            # GZIP is a single file; decompress to dest_dir keeping original name
            out_name = archive_path.with_suffix("").name
            out_path = dest_path / out_name
            with gzip.open(archive_path, "rb") as f_in, out_path.open("wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        elif fmt == ArchiveFormat.ZIP:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    member_path = dest_path / member.filename
                    if not _is_within_directory(dest_path, member_path):
                        raise Exception(f"Path traversal attempt in ZIP: {member.filename}")
                zf.extractall(dest_path)

        elif fmt in (ArchiveFormat.TAR, ArchiveFormat.TAR_GZ):
            mode = "r:gz" if fmt == ArchiveFormat.TAR_GZ else "r"
            with tarfile.open(archive_path, mode) as tf:
                _safe_extract_tar(tf, dest_path)

        else:
            raise ValueError(f"Unsupported format: {fmt}")

    except OSError as exc:
        raise OSError(f"Error during decompression: {exc}") from exc


def list_contents(archive: Union[str, Path]) -> List[str]:
    """
    List the contents of an archive.

    Args:
        archive: Path to the archive file.

    Returns:
        List of file paths within the archive.

    Raises:
        FileNotFoundError: If archive does not exist.
        ValueError: If format is unsupported.
        OSError: For I/O errors.
    """
    archive_path = Path(archive).resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    fmt = _detect_format_from_extension(archive_path)
    if