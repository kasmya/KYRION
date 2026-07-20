#!/usr/bin/env python3
"""
File compression utility supporting ZIP, GZIP, and TAR formats.

Features
--------
- Compress a single file.
- Compress a directory (ZIP, TAR).
- Decompress an archive.
- List archive contents.

Security
--------
- Safe extraction for TAR and ZIP archives (prevents path traversal).
- Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Iterable, List, Tuple


class ArchiveFormat(Enum):
    """Supported archive formats."""
    ZIP = auto()
    GZIP = auto()
    TAR = auto()

    @staticmethod
    def from_path(path: Path) -> "ArchiveFormat":
        """Detect format from file extension."""
        ext = path.suffix.lower()
        if ext == ".zip":
            return ArchiveFormat.ZIP
        if ext == ".gz":
            return ArchiveFormat.GZIP
        if ext in {".tar", ".tgz", ".tar.gz"}:
            return ArchiveFormat.TAR
        raise ValueError(f"Unable to determine archive format for: {path}")


def _safe_path(base: Path, target: Path) -> Path:
    """
    Ensure that ``target`` is within ``base`` to avoid path traversal attacks.
    Returns the resolved path if safe, otherwise raises ValueError.
    """
    resolved = (base / target).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Attempted Path Traversal in archive: {target}")
    return resolved


def _safe_extract_tar(tar: tarfile.TarFile, path: Path) -> None:
    """Safely extract a tar archive to ``path``."""
    for member in tar.getmembers():
        member_path = Path(member.name)
        safe_path = _safe_path(path, member_path)
        if member.isdir():
            safe_path.mkdir(parents=True, exist_ok=True)
        else:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            tar.extract(member, path=path)


def _safe_extract_zip(zipf: zipfile.ZipFile, path: Path) -> None:
    """Safely extract a zip archive to ``path``."""
    for member in zipf.infolist():
        member_path = Path(member.filename)
        safe_path = _safe_path(path, member_path)
        if member.is_dir():
            safe_path.mkdir(parents=True, exist_ok=True)
        else:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with zipf.open(member, "r") as src, safe_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)


@dataclass
class ArchiveUtility:
    """Utility class offering static methods for compression tasks."""

    @staticmethod
    def compress_file(
        src: Path,
        dst: Path,
        fmt: ArchiveFormat,
    ) -> None:
        """
        Compress a single file.

        Parameters
        ----------
        src: Path
            Path to the source file.
        dst: Path
            Destination archive file.
        fmt: ArchiveFormat
            Desired archive format.

        Raises
        ------
        FileNotFoundError
            If ``src`` does not exist or is not a file.
        ValueError
            If the format is unsupported for single-file compression.
        """
        if not src.is_file():
            raise FileNotFoundError(f"Source file not found: {src}")

        try:
            if fmt == ArchiveFormat.ZIP:
                with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(src, arcname=src.name)
            elif fmt == ArchiveFormat.GZIP:
                with src.open("rb") as f_in, gzip.open(dst, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            elif fmt == ArchiveFormat.TAR:
                with tarfile.open(dst, "w") as tf:
                    tf.add(src, arcname=src.name)
            else:
                raise ValueError(f"Unsupported format: {fmt}")
        except OSError as exc:
            raise IOError(f"Failed to compress file: {exc}") from exc

    @staticmethod
    def compress_directory(
        src_dir: Path,
        dst: Path,
        fmt: ArchiveFormat,
    ) -> None:
        """
        Compress an entire directory.

        Parameters
        ----------
        src_dir: Path
            Directory to compress.
        dst: Path
            Destination archive file.
        fmt: ArchiveFormat
            Desired archive format (ZIP or TAR).

        Raises
        ------
        FileNotFoundError
            If ``src_dir`` does not exist or is not a directory.
        ValueError
            If the format does not support directory compression.
        """
        if not src_dir.is_dir():
            raise FileNotFoundError(f"Source directory not found: {src_dir}")

        try:
            if fmt == ArchiveFormat.ZIP:
                with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for file_path in src_dir.rglob("*"):
                        arcname = file_path.relative_to(src_dir)
                        zf.write(file_path, arcname=str(arcname))
            elif fmt == ArchiveFormat.TAR:
                with tarfile.open(dst, "w") as tf:
                    tf.add(src_dir, arcname=".")
            elif fmt == ArchiveFormat.GZIP:
                raise ValueError("GZIP format does not support directory compression.")
            else:
                raise ValueError(f"Unsupported format: {fmt}")
        except OSError as exc:
            raise IOError(f"Failed to compress directory: {exc}") from exc

    @staticmethod
    def decompress(
        archive: Path,
        out_dir: Path,
    ) -> None:
        """
        Decompress an archive into ``out_dir``.

        Parameters
        ----------
        archive: Path
            Archive file to decompress.
        out_dir: Path
            Destination directory.

        Raises
        ------
        FileNotFoundError
            If ``archive`` does not exist.
        ValueError
            If the archive type is unknown or unsupported.
        """
        if not archive.is_file():
            raise FileNotFoundError(f"Archive not found: {archive}")

        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            if zipfile.is_zipfile(archive):
                with zipfile.ZipFile(archive, "r") as zf:
                    _safe_extract_zip(zf, out_dir)
            elif tarfile.is_tarfile(archive):
                with tarfile.open(archive, "r:*") as tf:
                    _safe_extract_tar(tf, out_dir)
            elif archive.suffix.lower() == ".gz":
                # GZIP contains a single file; derive name from archive
                out_file = out_dir / archive.stem
                with gzip.open(archive, "rb") as f_in, out_file.open("wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            else:
                raise ValueError(f"Unsupported archive format: {archive}")
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            raise IOError(f"Failed