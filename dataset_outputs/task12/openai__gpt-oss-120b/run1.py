#!/usr/bin/env python3
"""
File compression utility supporting ZIP, GZIP, and TAR formats.

Features:
- Compress single files or directories.
- Decompress archives.
- List archive contents.
- Security‑aware extraction (prevents path traversal).
- Full type hints and comprehensive error handling.
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
import tarfile
import zipfile
from enum import Enum, auto
from pathlib import Path
from typing import Iterable, List, Sequence


class ArchiveFormat(Enum):
    """Supported archive formats."""

    ZIP = auto()
    GZIP = auto()
    TAR = auto()

    @classmethod
    def from_path(cls, path: Path) -> "ArchiveFormat":
        """Detect format from file suffix."""
        suffix = path.suffix.lower()
        if suffix == ".zip":
            return cls.ZIP
        if suffix in (".gz", ".gzip"):
            # Distinguish between plain .gz (single file) and .tar.gz (tar archive)
            if path.name.lower().endswith(".tar.gz"):
                return cls.TAR
            return cls.GZIP
        if suffix in (".tar", ".tgz", ".tbz", ".tbz2", ".txz"):
            return cls.TAR
        raise ValueError(f"Cannot determine archive format from suffix: {suffix}")


def _ensure_parent_dir(path: Path) -> None:
    """Create parent directories for the given path if they do not exist."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PermissionError(f"Cannot create directory {path.parent!s}: {exc}") from exc


def compress(
    source: Path,
    destination: Path,
    fmt: ArchiveFormat,
    *,  # keyword‑only arguments
    compresslevel: int = 9,
) -> None:
    """
    Compress `source` (file or directory) to `destination` using the given format.

    Args:
        source: Path to a file or directory to compress.
        destination: Output archive file.
        fmt: Desired archive format.
        compresslevel: Compression level (0–9). Higher is slower but smaller.

    Raises:
        FileNotFoundError: If `source` does not exist.
        ValueError: If an unsupported combination is requested (e.g., gzip + directory).
        PermissionError: If writing to `destination` fails.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist: {source}")

    _ensure_parent_dir(destination)

    if fmt is ArchiveFormat.ZIP:
        _compress_zip(source, destination, compresslevel)
    elif fmt is ArchiveFormat.GZIP:
        if source.is_dir():
            raise ValueError("GZIP format only supports single files, not directories.")
        _compress_gzip(source, destination, compresslevel)
    elif fmt is ArchiveFormat.TAR:
        _compress_tar(source, destination, compresslevel)
    else:
        raise ValueError(f"Unsupported archive format: {fmt}")


def _compress_zip(source: Path, dest: Path, compresslevel: int) -> None:
    """Create a ZIP archive."""
    mode = "w"
    try:
        with zipfile.ZipFile(dest, mode, compression=zipfile.ZIP_DEFLATED, compresslevel=compresslevel) as zf:
            if source.is_file():
                zf.write(source, arcname=source.name)
            else:
                for root, _, files in os.walk(source):
                    root_path = Path(root)
                    for file in files:
                        file_path = root_path / file
                        arcname = file_path.relative_to(source.parent)
                        zf.write(file_path, arcname=str(arcname))
    except OSError as exc:
        raise PermissionError(f"Failed to write ZIP archive {dest!s}: {exc}") from exc


def _compress_gzip(source: Path, dest: Path, compresslevel: int) -> None:
    """Compress a single file using GZIP."""
    try:
        with source.open("rb") as f_in, gzip.open(dest, "wb", compresslevel=compresslevel) as f_out:
            shutil.copyfileobj(f_in, f_out)
    except OSError as exc:
        raise PermissionError(f"Failed to write GZIP file {dest!s}: {exc}") from exc


def _compress_tar(source: Path, dest: Path, compresslevel: int) -> None:
    """Create a TAR (optionally gzipped) archive."""
    mode = "w:gz" if dest.suffixes[-2:] == [".tar", ".gz"] or dest.suffix == ".tgz" else "w"
    try:
        with tarfile.open(dest, mode, compresslevel=compresslevel) as tf:
            if source.is_file():
                tf.add(source, arcname=source.name)
            else:
                tf.add(source, arcname=source.name)
    except OSError as exc:
        raise PermissionError(f"Failed to write TAR archive {dest!s}: {exc}") from exc


def decompress(archive: Path, destination: Path) -> None:
    """
    Decompress `archive` into `destination` safely.

    Args:
        archive: Path to the archive file.
        destination: Directory where contents will be extracted.

    Raises:
        FileNotFoundError: If the archive does not exist.
        ValueError: If the archive format is unknown.
        PermissionError: If extraction fails due to filesystem permissions.
    """
    if not archive.is_file():
        raise FileNotFoundError(f"Archive not found: {archive}")

    fmt = ArchiveFormat.from_path(archive)
    _ensure_parent_dir(destination)
    destination.mkdir(parents=True, exist_ok=True)

    if fmt is ArchiveFormat.ZIP:
        _decompress_zip(archive, destination)
    elif fmt is ArchiveFormat.GZIP:
        _decompress_gzip(archive, destination)
    elif fmt is ArchiveFormat.TAR:
        _decompress_tar(archive, destination)
    else:
        raise ValueError(f"Unsupported archive format: {fmt}")


def _decompress_zip(archive: Path, dest: Path) -> None:
    """Extract ZIP archive safely."""
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            for info in zf.infolist():
                _validate_zip_path(info.filename)
                zf.extract(info, path=dest)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid ZIP file: {archive}") from exc
    except OSError as exc:
        raise PermissionError(f"Failed to extract ZIP archive {archive}: {exc}") from exc


def _validate_zip_path(name: str) -> None:
    """Prevent ZipSlip attacks."""
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"Unsafe path detected in zip entry: {name}")


def _decompress_gzip(archive: Path, dest: Path) -> None:
    """Decompress a GZIP file (produces a single output file)."""
    output_file = dest / archive.stem
    try:
        with gzip.open(archive, "rb") as f_in, output_file.open("wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    except OSError as exc:
        raise PermissionError(f"Failed to extract GZIP file {archive}: {exc}") from exc


def _decompress_tar(archive: Path, dest: Path) -> None:
    """Extract TAR (or TAR.GZ) archive safely."""
    try:
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getmembers():
                _validate_tar_path(member)
                tf.extract(member, path=dest)
    except tarfile.TarError as exc:
        raise ValueError(f"Invalid TAR archive: {archive}") from exc
    except OSError as exc:
        raise PermissionError(f"Failed to extract TAR archive {archive}: {exc}") from exc


def _validate_tar_path(member: tarfile.TarInfo) -> None: