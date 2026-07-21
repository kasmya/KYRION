"""
File Compression Utility

Supports compression and decompression of files and directories using ZIP, GZIP, and TAR formats.
Provides functionality to compress files, compress directories, decompress archives, and list archive contents.

Security considerations:
- Path traversal protection during extraction
- Safe temporary file handling
- Input validation and sanitization
- No shell command execution

Example usage:
    from compression_util import compress_files, compress_directory, decompress, list_archive_contents
    
    compress_files(['file1.txt', 'file2.txt'], 'archive.zip')
    compress_directory('my_folder', 'archive.tar.gz')
    decompress('archive.zip', 'output_dir')
    contents = list_archive_contents('archive.tar')
"""

import os
import sys
import gzip
import shutil
import zipfile
import tarfile
import tempfile
from pathlib import Path
from typing import List, Union, Optional, BinaryIO
from contextlib import contextmanager


# Type aliases
PathLike = Union[str, Path]
ArchiveFormat = str


class CompressionError(Exception):
    """Base exception for compression-related errors."""
    pass


class InvalidArchiveError(CompressionError):
    """Raised when an archive is invalid or corrupted."""
    pass


class PathTraversalError(CompressionError):
    """Raised when a path traversal attempt is detected."""
    pass


class UnsupportedFormatError(CompressionError):
    """Raised when an unsupported archive format is requested."""
    pass


def _normalize_path(path: PathLike) -> Path:
    """Convert path to absolute Path object and resolve symlinks."""
    return Path(path).expanduser().resolve()


def _validate_paths_within_base(paths: List[Path], base: Path) -> None:
    """Ensure all paths are within the base directory to prevent path traversal."""
    base_resolved = base.resolve()
    for path in paths:
        try:
            path.resolve().relative_to(base_resolved)
        except ValueError:
            raise PathTraversalError(
                f"Path '{path}' attempts to traverse outside base directory '{base}'"
            )


def _get_archive_format(archive_path: PathLike) -> ArchiveFormat:
    """Determine archive format from file extension."""
    path = Path(archive_path)
    suffixes = path.suffixes
    
    if '.tar.gz' in ''.join(suffixes[-2:]) or '.tgz' in ''.join(suffixes[-2:]):
        return 'tar.gz'
    elif '.tar.bz2' in ''.join(suffixes[-2:]) or '.tbz2' in ''.join(suffixes[-2:]):
        return 'tar.bz2'
    elif '.tar.xz' in ''.join(suffixes[-2:]) or '.txz' in ''.join(suffixes[-2:]):
        return 'tar.xz'
    elif suffixes and suffixes[-1] in ('.zip', '.gz', '.tar', '.bz2', '.xz'):
        return suffixes[-1][1:]  # Remove leading dot
    else:
        raise UnsupportedFormatError(f"Cannot determine format for '{archive_path}'")


@contextmanager
def _safe_temp_file(suffix: str = '', prefix: str = 'tmp', dir: Optional[PathLike] = None) -> BinaryIO:
    """Create a temporary file safely with automatic cleanup."""
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb', suffix=suffix, prefix=prefix, dir=dir, delete=False
    )
    try:
        yield temp_file
    finally:
        temp_file.close()
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass


def compress_files(
    files: List[PathLike],
    archive_path: PathLike,
    format: Optional[ArchiveFormat] = None,
    compression_level: int = 6
) -> None:
    """
    Compress a list of files into an archive.
    
    Args:
        files: List of file paths to compress
        archive_path: Output archive path
        format: Archive format ('zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', 'gzip').
                If None, inferred from archive_path extension.
        compression_level: Compression level (1-9) for gzip/bz2/xz
    
    Raises:
        CompressionError: If compression fails
        InvalidArchiveError: If archive format is unsupported
        FileNotFoundError: If any input file doesn't exist
        PathTraversalError: If path traversal detected
    
    Example:
        compress_files(['data.txt', 'config.json'], 'backup.zip')
        compress_files(['large.log'], 'large.log.gz', format='gzip')
    """
    if not files:
        raise CompressionError("No files provided for compression")
    
    archive_path = _normalize_path(archive_path)
    files = [_normalize_path(f) for f in files]
    
    # Validate all files exist and are readable
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f"File not found: {f}")
        if not f.is_file():
            raise CompressionError(f"Not a regular file: {f}")
        if not os.access(f, os.R_OK):
            raise CompressionError(f"Permission denied reading: {f}")
    
    # Determine format
    if format is None:
        format = _get_archive_format(archive_path)
    
    format = format.lower()
    
    # Ensure parent directory exists
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if format == 'zip':
            _compress_zip(files, archive_path, compression_level)
        elif format == 'gzip':
            if len(files) != 1:
                raise CompressionError("GZIP format only supports single file compression")
            _compress_gzip(files[0], archive_path, compression_level)
        elif format in ('tar', 'tar.gz', 'tar.bz2', 'tar.xz'):
            _compress_tar(files, archive_path, format, compression_level)
        else:
            raise UnsupportedFormatError(f"Unsupported format: {format}")
    except Exception as e:
        # Clean up partial archive on failure
        if archive_path.exists():
            try:
                archive_path.unlink()
            except OSError:
                pass
        raise CompressionError(f"Compression failed: {e}") from e


def _compress_zip(files: List[Path], archive_path: Path, compression_level: int) -> None:
    """Compress files to ZIP archive."""
    compression = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(
        archive_path, 'w', compression=compression, compresslevel=compression_level
    ) as zf:
        for file_path in files:
            # Use relative path for archive entry
            arcname = file_path.name
            zf.write(file_path, arcname=arcname)


def _compress_gzip(file_path: Path, archive_path: Path, compression_level: int) -> None:
    """Compress single file to GZIP."""
    with open(file_path, 'rb') as f_in:
        with gzip.open(archive_path, 'wb', compresslevel=compression_level) as f_out:
            shutil.copyfileobj(f_in, f_out)


def _compress_tar(files: List[Path], archive_path: Path, format: str, compression_level: int) -> None:
    """Compress files to TAR archive (with optional compression)."""
    mode_map = {
        'tar': 'w',
        'tar.gz': 'w:gz',
        'tar.bz2': 'w:bz2',
        'tar.xz': 'w:xz'
    }
    
    if format not in mode_map:
        raise UnsupportedFormatError(f"Unsupported TAR format: {format}")
    
    mode = mode_map[format]
    with tarfile.open(archive_path, mode, compresslevel=compression_level) as tf:
        for file_path in files:
            arcname = file_path.name
            tf.add(file_path, arcname=arcname)


def compress_directory(
    directory: PathLike,
    archive_path: PathLike,
    format: Optional[ArchiveFormat] = None,
    compression_level: int = 6,
    include_root: bool = True
) -> None:
    """
    Compress an entire directory into an archive.
    
    Args:
        directory: Directory path to compress
        archive_path: Output archive path
        format: Archive format ('zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz').
                If None, inferred from archive_path extension.
        compression_level: Compression level (1-9)
        include_root: If True, include directory name in archive paths
    
    Raises:
        CompressionError: If compression fails
        InvalidArchiveError: If archive format is unsupported
        FileNotFoundError: If directory doesn't exist
        NotADirectoryError: If path is not a directory
    
    Example:
        compress_directory('project', 'project.zip')
        compress_directory('logs', 'logs.tar.gz', format='tar.gz')
    """
    directory = _normalize_path(directory)
    archive_path = _normalize_path(archive_path)
    
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    if not os.access(directory, os.R_OK):
        raise CompressionError(f"Permission denied reading directory: {directory}")
    
    # Determine format
    if format is None:
        format = _get_archive_format(archive_path)
    
    format = format.lower()
    
    # Ensure parent directory exists
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if format == 'zip':
            _compress_directory_zip(directory, archive_path, compression_level, include_root)
        elif format in ('tar', 'tar.gz', 'tar.bz2', 'tar.xz'):
            _compress_directory_tar(directory, archive_path, format, compression_level, include_root)
        else:
            raise UnsupportedFormatError(f"Unsupported format for directory: {format}")
    except Exception as e:
        # Clean up partial archive on failure
        if archive_path.exists():
            try:
                archive_path.unlink()
            except OSError:
                pass
        raise CompressionError(f"Directory compression failed: {e}") from e


def _compress_directory_zip(
    directory: Path, archive_path: Path, compression_level: int, include_root: bool
) -> None:
    """Compress directory to ZIP archive."""
    with zipfile.ZipFile(
        archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level
    ) as zf:
        root_path = directory.parent if include_root else directory
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(root_path)
                zf.write(file_path, arcname=str(arcname))


def _compress_directory_tar(
    directory: Path, archive_path: Path, format: str, compression_level: int, include_root: bool
) -> None:
    """Compress directory to TAR archive."""
    mode_map = {
        'tar': 'w',
        'tar.gz': 'w:gz',
        'tar.bz2': 'w:bz2',
        'tar.xz': 'w:xz'
    }
    
    mode = mode_map[format]
    with tarfile.open(archive_path, mode, compresslevel=compression_level) as tf:
        if include_root:
            tf.add(directory, arcname=directory.name)
        else:
            for item in directory.iterdir():
                tf.add(item, arcname=item.name)


def decompress(
    archive_path: PathLike,
    target_dir: PathLike,
    format: Optional[ArchiveFormat] = None,
    overwrite: bool = False
) -> None:
    """
    Decompress an archive to a target directory.
    
    Args:
        archive_path: Path to archive file
        target_dir: Target directory for extraction
        format: Archive format. If None, inferred from archive_path extension.
        overwrite: Whether to overwrite existing files
    
    Raises:
        CompressionError: If decompression fails
        InvalidArchiveError: If archive is invalid or corrupted
        FileNotFoundError: If archive doesn't exist
        PathTraversalError: If archive contains path traversal attempts
        FileExistsError: If target files exist and overwrite=False
    
    Example:
        decompress('backup.zip', 'restored')
        decompress('data.tar.gz', 'output', format='tar.gz')
    """
    archive_path = _normalize_path(archive_path)
    target_dir = _normalize_path(target_dir)
    
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    if not archive_path.is_file():
        raise CompressionError(f"Not a regular file: {archive_path}")
    if not os.access(archive_path, os.R_OK):
        raise CompressionError(f"Permission denied reading archive: {archive_path}")
    
    # Determine format
    if format is None:
        format = _get_archive_format(archive_path)
    
    format = format.lower()
    
    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        if format == 'zip':
            _decompress_zip(archive_path, target_dir, overwrite)
        elif format == 'gzip':
            _decompress_gzip(archive_path, target_dir, overwrite)
        elif format in ('tar', 'tar.gz', 'tar.bz2', 'tar.xz'):
            _decompress_tar(archive_path, target_dir, format, overwrite)
        else:
            raise UnsupportedFormatError(f"Unsupported format: {format}")
    except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile) as e:
        raise InvalidArchiveError(f"Invalid or corrupted archive: {e}") from e
    except Exception as e:
        raise CompressionError(f"Decompression failed: {e}") from e


def _decompress_zip(archive_path: Path, target_dir: Path, overwrite: bool) -> None:
    """Extract ZIP archive with path traversal protection."""
    with zipfile.ZipFile(archive_path, 'r') as zf:
        # Validate all paths before extraction
        for member in zf.namelist():
            member_path = (target_dir / member).resolve()
            try:
                member_path.relative_to(target_dir.resolve())
            except ValueError:
                raise PathTraversalError(f"Path traversal attempt in archive: {member}")
        
        # Check for existing files
        if not overwrite:
            for member in zf.namelist():
                if (target_dir / member).exists():
                    raise FileExistsError(f"File exists (use overwrite=True): {member}")
        
        # Safe extraction
        zf.extractall(target_dir)


def _decompress_gzip(archive_path: Path, target_dir: Path, overwrite: bool) -> None:
    """Extract GZIP file (single file)."""
    # Determine output filename (remove .gz extension)
    output_name = archive_path.stem  # Removes .gz
    output_path = target_dir / output_name
    
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"File exists (use overwrite=True): {output_path}")
    
    with gzip.open(archive_path, 'rb') as f_in:
        with open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)


def _decompress_tar(