"""
file_compressor.py

A small utility for creating and handling archive files. Supports ZIP, GZIP, and TAR
formats with functions to compress a single file, compress an entire directory,
decompress an archive, and list the contents of an archive.

Security considerations:
- Extraction routines guard against path traversal attacks.
- Only files with safe relative paths are written to the filesystem.
- Overwrites are prevented unless explicitly allowed.

All functions raise :class:`ArchiveError` on failure.
"""

from __future__ import annotations

import enum
import gzip
import io
import os
import pathlib
import shutil
import tarfile
import typing
import zipfile

from typing import Iterable, List, Optional, Union

__all__ = [
    "ArchiveFormat",
    "ArchiveError",
    "compress_file",
    "compress_directory",
    "decompress_archive",
    "list_archive_contents",
]

PathLike = Union[str, os.PathLike]


class ArchiveFormat(enum.Enum):
    """Supported archive formats."""

    ZIP = "zip"
    GZIP = "gzip"
    TAR = "tar"


class ArchiveError(RuntimeError):
    """Base exception for all archive‑related errors."""


def _resolve_path(path: PathLike) -> pathlib.Path:
    """Resolve a path to an absolute :class:`pathlib.Path`."""
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists():
        raise ArchiveError(f"Path does not exist: {p}")
    return p


def _ensure_parent_dir(path: pathlib.Path) -> None:
    """Create parent directories for *path* if they do not exist."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchiveError(f"Unable to create directory {path.parent}: {exc}") from exc


def compress_file(
    source: PathLike,
    dest: PathLike,
    fmt: ArchiveFormat = ArchiveFormat.ZIP,
    *,
    compresslevel: int = 9,
) -> None:
    """
    Compress a single file.

    Args:
        source: Path to the file to compress.
        dest: Destination archive file path.
        fmt: Archive format to use.
        compresslevel: Compression level (1‑9) where applicable.

    Raises:
        ArchiveError: If the operation fails.
    """
    src_path = _resolve_path(source)
    if not src_path.is_file():
        raise ArchiveError(f"Source must be a file: {src_path}")

    dest_path = pathlib.Path(dest).expanduser().resolve()
    _ensure_parent_dir(dest_path)

    try:
        if fmt is ArchiveFormat.ZIP:
            with zipfile.ZipFile(
                dest_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=compresslevel
            ) as zf:
                zf.write(src_path, arcname=src_path.name)
        elif fmt is ArchiveFormat.GZIP:
            with src_path.open("rb") as f_in, gzip.open(
                dest_path, "wb", compresslevel=compresslevel
            ) as f_out:
                shutil.copyfileobj(f_in, f_out)
        elif fmt is ArchiveFormat.TAR:
            with tarfile.open(dest_path, "w:gz", compresslevel=compresslevel) as tf:
                tf.add(src_path, arcname=src_path.name)
        else:
            raise ArchiveError(f"Unsupported format: {fmt}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        raise ArchiveError(f"Failed to compress file: {exc}") from exc


def compress_directory(
    source_dir: PathLike,
    dest: PathLike,
    fmt: ArchiveFormat = ArchiveFormat.ZIP,
    *,
    compresslevel: int = 9,
) -> None:
    """
    Compress an entire directory (recursively).

    Args:
        source_dir: Directory to compress.
        dest: Destination archive file path.
        fmt: Archive format to use.
        compresslevel: Compression level where applicable.

    Raises:
        ArchiveError: If the operation fails or if the format does not support directories.
    """
    src_path = _resolve_path(source_dir)
    if not src_path.is_dir():
        raise ArchiveError(f"Source must be a directory: {src_path}")

    dest_path = pathlib.Path(dest).expanduser().resolve()
    _ensure_parent_dir(dest_path)

    try:
        if fmt is ArchiveFormat.ZIP:
            with zipfile.ZipFile(
                dest_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=compresslevel
            ) as zf:
                for root, _, files in os.walk(src_path):
                    for file in files:
                        file_path = pathlib.Path(root) / file
                        arcname = file_path.relative_to(src_path.parent)
                        zf.write(file_path, arcname=str(arcname))
        elif fmt is ArchiveFormat.TAR:
            mode = f"w:gz" if compresslevel > 0 else "w"
            with tarfile.open(dest_path, mode, compresslevel=compresslevel) as tf:
                tf.add(src_path, arcname=src_path.name)
        elif fmt is ArchiveFormat.GZIP:
            raise ArchiveError("GZIP format does not support directory compression.")
        else:
            raise ArchiveError(f"Unsupported format: {fmt}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Failed to compress directory: {exc}") from exc


def _is_path_within_directory(base: pathlib.Path, target: pathlib.Path) -> bool:
    """Return ``True`` if *target* resides inside *base* (prevents path traversal)."""
    try:
        base = base.resolve()
        target = target.resolve()
        return str(target).startswith(str(base) + os.sep)
    except RuntimeError:
        return False


def decompress_archive(
    archive_path: PathLike,
    dest_dir: PathLike,
    *,
    fmt: Optional[ArchiveFormat] = None,
    overwrite: bool = False,
) -> None:
    """
    Decompress an archive into *dest_dir*.

    Args:
        archive_path: Path to the archive file.
        dest_dir: Directory where files will be extracted.
        fmt: Optional explicit format; if omitted, format is inferred from extension.
        overwrite: Allow overwriting existing files.

    Raises:
        ArchiveError: If extraction fails or unsafe paths are detected.
    """
    archive = _resolve_path(archive_path)
    dest = pathlib.Path(dest_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # Infer format if not provided
    if fmt is None:
        ext = archive.suffix.lower()
        if ext == ".zip":
            fmt = ArchiveFormat.ZIP
        elif ext in (".gz", ".tgz"):
            # Could be gzip (single file) or tar.gz; guess based on name
            if archive.name.endswith(".tar.gz") or archive.name.endswith(".tgz"):
                fmt = ArchiveFormat.TAR
            else:
                fmt = ArchiveFormat.GZIP
        elif ext == ".tar":
            fmt = ArchiveFormat.TAR
        else:
            raise ArchiveError(f"Unable to infer archive format from extension: {ext}")

    try:
        if fmt is ArchiveFormat.ZIP:
            with zipfile.ZipFile(archive, "r") as zf:
                for info in zf.infolist():
                    extracted_path = dest / info.filename
                    if not _is_path_within_directory(dest, extracted_path):
                        raise ArchiveError(f"Unsafe path detected in zip: {info.filename}")
                    if extracted_path.exists() and not overwrite:
                        raise ArchiveError(f"File exists and overwrite=False: {extracted_path}")
                    _ensure_parent_dir(extracted_path)
                    with zf.open(info, "r") as source, extracted_path.open("wb") as target:
                        shutil.copyfileobj(source, target)
        elif fmt is ArchiveFormat.GZIP:
            # GZIP usually contains a single file
            with gzip.open(archive, "rb") as gz:
                # Derive output name from archive name (strip .gz)
                out_name = archive.stem
                extracted_path = dest / out_name
                if extracted_path.exists() and not overwrite:
                    raise ArchiveError(f"File exists and overwrite=False: {extracted_path}")
                _ensure_parent_dir(extracted_path)
                with extracted_path.open("wb") as out_f:
                    shutil.copyfileobj(gz, out_f)
        elif fmt is ArchiveFormat.TAR:
            with tarfile.open(archive, "r:*") as tf:
                for member in tf.getmembers():
                    member_path = dest / member.name
                    if not _is_path_within_directory(dest, member_path):
                        raise ArchiveError(f"Unsafe path detected in tar: {member.name}")
                    if member_path.exists() and not overwrite:
                        raise ArchiveError(f"File exists and overwrite=False: {member_path}")
                    tf.extract(member, path=dest, set_attrs=False)
        else:
            raise ArchiveError(f"Unsupported format: {fmt}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        raise ArchiveError(f"Failed to decompress archive: {exc}") from exc


def list_archive_contents(
    archive_path: PathLike,
    *,
    fmt: Optional[ArchiveFormat] = None,
) -> List[str]:
    """
    Return a list of file names contained in the archive.

    Args:
        archive_path: Path to the archive file.
        fmt: Optional explicit format; inferred from extension if omitted.

    Returns:
        A list of relative file paths stored in the archive.

    Raises:
        ArchiveError: If reading the archive fails.
    """
    archive = _resolve_path(archive_path)

    if fmt is None:
        ext = archive.suffix.lower()
        if ext == ".zip":
            fmt = ArchiveFormat.ZIP
        elif ext in (".gz", ".tgz"):
            if archive.name.endswith(".tar.gz") or archive.name.endswith(".tgz"):
                fmt = ArchiveFormat.TAR
            else:
                fmt = ArchiveFormat.GZIP
        elif ext == ".tar":
            fmt = ArchiveFormat.TAR
        else:
            raise ArchiveError(f"Cannot infer archive format from extension: {ext}")

    try:
        if fmt is ArchiveFormat.ZIP:
            with zipfile.ZipFile(archive, "r") as zf:
                return zf.namelist()
        elif fmt is ArchiveFormat.GZIP:
            # GZIP usually wraps a single file; return its inferred name
            return [archive.stem]
        elif fmt is ArchiveFormat.TAR:
            with tarfile.open(archive, "r:*") as tf:
                return tf.getnames()
        else:
            raise ArchiveError(f"Unsupported format: {fmt}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        raise ArchiveError(f"Failed to list archive contents: {exc}") from exc