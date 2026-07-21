"""archive_util.py
A small utility for creating and extracting archives.

Supported formats:
- ZIP (both files and directories)
- GZIP (single file compression)
- TAR (both plain tar and tar.gz)

Features:
- Compress a single file.
- Compress a directory (recursively).
- Decompress an archive to a target directory.
- List the contents of an archive.

All operations raise :class:`ArchiveError` on failure.
Security considerations:
- Extraction checks for path traversal attempts and refuses to extract such entries.
- Only paths inside the intended output directory are allowed.
"""

from __future__ import annotations

import gzip
import os
import tarfile
import zipfile
from pathlib import Path
from typing import List, Literal, Union

__all__ = [
    "ArchiveError",
    "compress_file",
    "compress_directory",
    "decompress",
    "list_contents",
]

ArchiveFormat = Literal["zip", "gzip", "tar"]


class ArchiveError(RuntimeError):
    """Base exception for all archive‑related errors."""


def _validate_path(path: Path) -> None:
    """Raise :class:`ArchiveError` if *path* does not exist or is not a file."""
    if not path.exists():
        raise ArchiveError(f"Path does not exist: {path}")
    if not path.is_file():
        raise ArchiveError(f"Path is not a file: {path}")


def _validate_dir(path: Path) -> None:
    """Raise :class:`ArchiveError` if *path* does not exist or is not a directory."""
    if not path.exists():
        raise ArchiveError(f"Directory does not exist: {path}")
    if not path.is_dir():
        raise ArchiveError(f"Path is not a directory: {path}")


def compress_file(
    source: Union[str, Path],
    destination: Union[str, Path],
    fmt: ArchiveFormat = "zip",
) -> None:
    """
    Compress a single file.

    Parameters
    ----------
    source : Path or str
        Path to the file to compress.
    destination : Path or str
        Desired archive file path (extension may be omitted).
    fmt : {"zip", "gzip", "tar"}
        Archive format.

    Raises
    ------
    ArchiveError
        If the source file cannot be read or the archive cannot be written.
    """
    src = Path(source).resolve()
    dst = Path(destination).resolve()
    _validate_path(src)

    if fmt == "gzip":
        if dst.suffix != ".gz":
            dst = dst.with_suffix(dst.suffix + ".gz")
        try:
            with src.open("rb") as f_in, gzip.open(dst, "wb") as f_out:
                f_out.writelines(f_in)
        except OSError as exc:
            raise ArchiveError(f"GZIP compression failed: {exc}") from exc

    elif fmt == "zip":
        if dst.suffix != ".zip":
            dst = dst.with_suffix(".zip")
        try:
            with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(src, arcname=src.name)
        except OSError as exc:
            raise ArchiveError(f"ZIP compression failed: {exc}") from exc

    elif fmt == "tar":
        if dst.suffix not in {".tar", ".tgz", ".tar.gz"}:
            dst = dst.with_suffix(".tar")
        try:
            mode = "w:gz" if dst.suffix in {".tgz", ".gz"} else "w"
            with tarfile.open(dst, mode) as tf:
                tf.add(src, arcname=src.name)
        except OSError as exc:
            raise ArchiveError(f"TAR compression failed: {exc}") from exc

    else:
        raise ArchiveError(f"Unsupported format: {fmt}")


def compress_directory(
    source_dir: Union[str, Path],
    destination: Union[str, Path],
    fmt: ArchiveFormat = "zip",
) -> None:
    """
    Compress an entire directory (recursively).

    Parameters
    ----------
    source_dir : Path or str
        Directory to compress.
    destination : Path or str
        Desired archive file path (extension may be omitted).
    fmt : {"zip", "tar"}
        Archive format. ``gzip`` is not applicable to directories.

    Raises
    ------
    ArchiveError
        If the source directory cannot be read or the archive cannot be written.
    """
    src_dir = Path(source_dir).resolve()
    dst = Path(destination).resolve()
    _validate_dir(src_dir)

    if fmt == "gzip":
        raise ArchiveError("GZIP format supports only single file compression, not directories.")

    if fmt == "zip":
        if dst.suffix != ".zip":
            dst = dst.with_suffix(".zip")
        try:
            with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file_path in src_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(src_dir)
                        zf.write(file_path, arcname=str(arcname))
        except OSError as exc:
            raise ArchiveError(f"ZIP compression failed: {exc}") from exc

    elif fmt == "tar":
        if dst.suffix not in {".tar", ".tgz", ".tar.gz"}:
            dst = dst.with_suffix(".tar")
        try:
            mode = "w:gz" if dst.suffix in {".tgz", ".gz"} else "w"
            with tarfile.open(dst, mode) as tf:
                tf.add(src_dir, arcname=src_dir.name)
        except OSError as exc:
            raise ArchiveError(f"TAR compression failed: {exc}") from exc

    else:
        raise ArchiveError(f"Unsupported format: {fmt}")


def _is_within_directory(directory: Path, target: Path) -> bool:
    """Return True if *target* resolves to a location inside *directory*."""
    try:
        directory = directory.resolve()
        target = target.resolve()
        return str(target).startswith(str(directory) + os.sep)
    except Exception:
        return False


def decompress(
    archive_path: Union[str, Path],
    output_dir: Union[str, Path],
) -> None:
    """
    Extract an archive to a directory.

    Parameters
    ----------
    archive_path : Path or str
        Path to the archive file.
    output_dir : Path or str
        Destination directory for extracted files.

    Raises
    ------
    ArchiveError
        If extraction fails or a security check is violated.
    """
    archive = Path(archive_path).resolve()
    out_dir = Path(output_dir).resolve()
    if not archive.is_file():
        raise ArchiveError(f"Archive not found: {archive}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # ZIP handling
    if zipfile.is_zipfile(archive):
        try:
            with zipfile.ZipFile(archive, "r") as zf:
                for member in zf.infolist():
                    member_path = out_dir / member.filename
                    if not _is_within_directory(out_dir, member_path):
                        raise ArchiveError(f"Path traversal attempt detected in ZIP entry: {member.filename}")
                zf.extractall(out_dir)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ArchiveError(f"Failed to extract ZIP archive: {exc}") from exc
        return

    # TAR handling (including gzipped tar)
    try:
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getmembers():
                member_path = out_dir / member.name
                if not _is_within_directory(out_dir, member_path):
                    raise ArchiveError(f"Path traversal attempt detected in TAR entry: {member.name}")
            tf.extractall(out_dir)
    except (tarfile.TarError, OSError) as exc:
        raise ArchiveError(f"Failed to extract TAR archive: {exc}") from exc


def list_contents(archive_path: Union[str, Path]) -> List[str]:
    """
    Return a list of file names contained in an archive.

    Parameters
    ----------
    archive_path : Path or str
        Path to the archive file.

    Returns
    -------
    List[str]
        Paths of members inside the archive, as stored (relative) names.

    Raises
    ------
    ArchiveError
        If the archive cannot be read.
    """
    archive = Path(archive_path).resolve()
    if not archive.is_file():
        raise ArchiveError(f"Archive not found: {archive}")

    if zipfile.is_zipfile(archive):
        try:
            with zipfile.ZipFile(archive, "r") as zf:
                return zf.namelist()
        except (zipfile.BadZipFile, OSError) as exc:
            raise ArchiveError(f"Failed to read ZIP archive: {exc}") from exc

    try:
        with tarfile.open(archive, "r:*") as tf:
            return [member.name for member in tf.getmembers()]
    except (tarfile.TarError, OSError) as exc:
        raise ArchiveError(f"Failed to read TAR archive: {exc}") from exc