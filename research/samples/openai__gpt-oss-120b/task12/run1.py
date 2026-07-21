"""
file_compressor.py

A small utility for creating and handling ZIP, GZIP, and TAR archives.

Features
--------
- Compress a single file into a ZIP, GZIP, or TAR archive.
- Compress an entire directory (recursively) into a ZIP or TAR archive.
- Decompress archives while protecting against path traversal attacks.
- List the contents of supported archives.

The module uses only the Python standard library and follows security best
practices such as safe extraction of archive members. All public functions are
type‑annotated and contain comprehensive docstrings.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
import gzip
import shutil
from pathlib import Path
from typing import Iterable, List, Union, Literal, Optional, Tuple

# Public API
__all__ = [
    "ArchiveFormat",
    "ArchiveError",
    "compress_file",
    "compress_directory",
    "decompress_archive",
    "list_archive_contents",
]

ArchiveFormat = Literal["zip", "tar", "gztar", "gzip"]


class ArchiveError(Exception):
    """Base class for all archive‑related errors raised by this module."""


def _ensure_path(path: Union[str, Path]) -> Path:
    """Convert *path* to a :class:`~pathlib.Path` and ensure it exists."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ArchiveError(f"Path does not exist: {p}")
    return p


def _safe_extract_tar(tar: tarfile.TarFile, destination: Path) -> None:
    """
    Extract *tar* safely into *destination*.

    The function checks each member's name to prevent absolute paths or path
    traversal (``..``) that could escape *destination*.
    """
    for member in tar.getmembers():
        member_path = destination / member.name
        try:
            member_path.resolve().relative_to(destination.resolve())
        except ValueError as exc:
            raise ArchiveError(f"Tar archive member '{member.name}' is unsafe.") from exc
    tar.extractall(path=destination)


def _safe_extract_zip(zipf: zipfile.ZipFile, destination: Path) -> None:
    """
    Extract *zipf* safely into *destination*.

    The function checks each entry's name to prevent absolute paths or path
    traversal (``..``) that could escape *destination*.
    """
    for member in zipf.infolist():
        member_path = destination / member.filename
        try:
            member_path.resolve().relative_to(destination.resolve())
        except ValueError as exc:
            raise ArchiveError(f"Zip archive member '{member.filename}' is unsafe.") from exc
    zipf.extractall(path=destination)


def compress_file(
    source: Union[str, Path],
    destination: Union[str, Path],
    fmt: ArchiveFormat = "zip",
    *,
    compresslevel: int = 9,
) -> Path:
    """
    Compress a single *source* file into an archive of type *fmt*.

    Parameters
    ----------
    source: path‑like
        The file to compress.
    destination: path‑like
        Desired archive file path. If the suffix does not match *fmt*, it will be
        adjusted automatically.
    fmt: {"zip", "tar", "gztar", "gzip"}
        Archive format. ``"gztar"`` produces a ``.tar.gz`` archive.
    compresslevel: int, optional
        Compression level (0–9). Ignored for ``zip`` where the default is used.

    Returns
    -------
    pathlib.Path
        The path to the created archive.

    Raises
    ------
    ArchiveError
        If *source* is not a regular file or any I/O error occurs.
    """
    src_path = _ensure_path(source)
    if not src_path.is_file():
        raise ArchiveError(f"Source must be a file: {src_path}")

    dest_path = Path(destination).expanduser().resolve()
    # Adjust suffix based on format
    suffix_map: dict[ArchiveFormat, str] = {
        "zip": ".zip",
        "tar": ".tar",
        "gztar": ".tar.gz",
        "gzip": ".gz",
    }
    expected_suffix = suffix_map[fmt]
    if dest_path.suffix != expected_suffix:
        dest_path = dest_path.with_suffix(expected_suffix)

    try:
        if fmt == "zip":
            with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(src_path, arcname=src_path.name)
        elif fmt == "tar":
            with tarfile.open(dest_path, "w") as tf:
                tf.add(src_path, arcname=src_path.name)
        elif fmt == "gztar":
            with tarfile.open(dest_path, "w:gz", compresslevel=compresslevel) as tf:
                tf.add(src_path, arcname=src_path.name)
        elif fmt == "gzip":
            # GZIP works on a single file; we create a .gz that contains the raw data.
            with open(src_path, "rb") as f_in, gzip.open(dest_path, "wb", compresslevel=compresslevel) as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            raise ArchiveError(f"Unsupported format: {fmt}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Failed to compress file: {exc}") from exc

    return dest_path


def compress_directory(
    source_dir: Union[str, Path],
    destination: Union[str, Path],
    fmt: Literal["zip", "tar", "gztar"] = "zip",
    *,
    compresslevel: int = 9,
) -> Path:
    """
    Recursively compress *source_dir* into an archive.

    Parameters
    ----------
    source_dir: path‑like
        Directory to compress.
    destination: path‑like
        Desired archive file path. The suffix is adjusted to match *fmt*.
    fmt: {"zip", "tar", "gztar"}
        Archive format.
    compresslevel: int, optional
        Compression level for ``tar``/``gztar``. Ignored for ``zip``.

    Returns
    -------
    pathlib.Path
        Path to the created archive.

    Raises
    ------
    ArchiveError
        If *source_dir* is not a directory or any I/O error occurs.
    """
    src_path = _ensure_path(source_dir)
    if not src_path.is_dir():
        raise ArchiveError(f"Source must be a directory: {src_path}")

    dest_path = Path(destination).expanduser().resolve()
    suffix_map = {"zip": ".zip", "tar": ".tar", "gztar": ".tar.gz"}
    expected_suffix = suffix_map[fmt]
    if dest_path.suffix != expected_suffix:
        dest_path = dest_path.with_suffix(expected_suffix)

    try:
        if fmt == "zip":
            with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file_path in src_path.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(src_path)
                        zf.write(file_path, arcname=str(arcname))
        elif fmt == "tar":
            with tarfile.open(dest_path, "w") as tf:
                tf.add(src_path, arcname=src_path.name)
        elif fmt == "gztar":
            with tarfile.open(dest_path, "w:gz", compresslevel=compresslevel) as tf:
                tf.add(src_path, arcname=src_path.name)
        else:
            raise ArchiveError(f"Unsupported format: {fmt}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Failed to compress directory: {exc}") from exc

    return dest_path


def decompress_archive(
    archive_path: Union[str, Path],
    destination: Union[str, Path],
    *,
    members: Optional[Iterable[str]] = None,
) -> List[Path]:
    """
    Decompress *archive_path* into *destination* safely.

    Parameters
    ----------
    archive_path: path‑like
        Path to the archive file.
    destination: path‑like
        Directory where the archive will be extracted. It is created if missing.
    members: iterable of str, optional
        Specific members to extract. If omitted, the whole archive is extracted.

    Returns
    -------
    list[pathlib.Path]
        List of extracted file paths.

    Raises
    ------
    ArchiveError
        If the archive format is unsupported, the archive is corrupted,
        or a security check fails.
    """
    arch_path = _ensure_path(archive_path)
    dest_path = Path(destination).expanduser().resolve()
    dest_path.mkdir(parents=True, exist_ok=True)

    extracted: List[Path] = []

    try:
        if zipfile.is_zipfile(arch_path):
            with zipfile.ZipFile(arch_path, "r") as zf:
                if members is None:
                    _safe_extract_zip(zf, dest_path)
                    extracted = [dest_path / info.filename for info in zf.infolist()]
                else:
                    for member in members:
                        if member not in zf.namelist():
                            raise ArchiveError(f"Member '{member}' not found in zip archive.")
                        # Safety check for the single member
                        member_path = dest_path / member
                        member_path.resolve().relative_to(dest_path.resolve())
                        zf.extract(member, path=dest_path)
                        extracted.append(member_path)
        elif tarfile.is_tarfile(arch_path):
            with tarfile.open(arch_path, "r:*") as tf:
                if members is None:
                    _safe_extract_tar(tf, dest_path)
                    extracted = [dest_path / member.name for member in tf.getmembers()]
                else:
                    # Ensure members exist and are safe
                    for name in members:
                        try:
                            member = tf.getmember(name)
                        except KeyError as exc:
                            raise ArchiveError(f"Member '{name}' not found in tar archive.") from exc
                        member_path = dest_path / member.name
                        member_path.resolve().relative_to(dest_path.resolve())
                    tf.extractall(path=dest_path, members=[tf.getmember(m) for m in members])
                    extracted = [dest_path / m for m in members]
        elif arch_path.suffix == ".gz":
            # Assume a single‑file gzip
            out_file = dest_path / arch_path.with_suffix("").name
            with gzip.open(arch_path, "rb") as f_in, open(out_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            extracted = [out_file]
        else:
            raise ArchiveError(f"Unsupported archive format: {arch_path}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        raise ArchiveError(f"Failed to decompress archive: {exc}") from exc

    return extracted


def list_archive_contents(
    archive_path: Union[str, Path],
) -> List[Tuple[str, int, str]]:
    """
    Return a list of entries in *archive_path*.

    Each entry is a tuple ``(name, size, type)`` where *type* is ``'file'``,
    ``'dir'`` or ``'symlink'``.

    Parameters
    ----------
    archive_path: path‑like
        Path to the archive file.

    Returns
    -------
    list[tuple[str, int, str]]
        Archive members sorted alphabetically.

    Raises
    ------
    ArchiveError
        If the archive cannot be opened or is of an unsupported type.
    """
    arch_path = _ensure_path(archive_path)

    try:
        if zipfile.is_zipfile(arch_path):
            with zipfile.ZipFile(arch_path, "r") as zf:
                entries = [
                    (
                        info.filename,
                        info.file_size,
                        "dir" if info.is_dir() else "file",
                    )
                    for info in zf.infolist()
                ]
        elif tarfile.is_tarfile(arch_path):
            with tarfile.open(arch_path, "r:*") as tf:
                entries = [
                    (
                        member.name,
                        member.size,
                        "dir"
                        if member.isdir()
                        else "symlink"
                        if member.issym()
                        else "file",
                    )
                    for member in tf.getmembers()
                ]
        elif arch_path.suffix == ".gz":
            # GZIP contains a single compressed file; size is unknown without decompression.
            entries = [(arch_path.with_suffix("").name, 0, "file")]
        else:
            raise ArchiveError(f"Unsupported archive format: {arch_path}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        raise ArchiveError(f"Failed to list archive contents: {exc}") from exc

    return sorted(entries, key=lambda x: x[0])