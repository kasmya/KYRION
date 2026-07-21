"""
File Compression Utility

A comprehensive utility for compressing and decompressing files and directories
using ZIP, GZIP, and TAR formats. Supports listing archive contents and provides
secure extraction with path traversal protection.

Supported formats:
- ZIP (.zip)
- GZIP (.gz) - single file compression only
- TAR (.tar, .tar.gz/.tgz, .tar.bz2/.tbz2, .tar.xz/.txz)

Security features:
- Path traversal protection during extraction
- Safe temporary file handling
- Input validation and sanitization
- Secure default permissions
"""

import os
import sys
import gzip
import shutil
import zipfile
import tarfile
import tempfile
from pathlib import Path
from typing import List, Optional, Union, Literal, Tuple
from contextlib import contextmanager


# Type aliases
ArchiveType = Literal['zip', 'gz', 'gzip', 'tar', 'tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar.xz', 'txz']
PathLike = Union[str, Path]


class CompressionError(Exception):
    """Base exception for compression-related errors."""
    pass


class ArchiveNotFoundError(CompressionError, FileNotFoundError):
    """Raised when archive file is not found."""
    pass


class InvalidArchiveTypeError(CompressionError, ValueError):
    """Raised when archive type is not supported or invalid."""
    pass


class ExtractionError(CompressionError):
    """Raised when extraction fails due to security or corruption issues."""
    pass


class CompressionUtility:
    """
    Utility class for file compression and decompression operations.
    
    Provides methods for compressing files/directories, decompressing archives,
    and listing archive contents with support for ZIP, GZIP, and TAR formats.
    """
    
    # Supported archive types and their extensions
    ARCHIVE_TYPES = {
        'zip': ['.zip'],
        'gz': ['.gz'],
        'gzip': ['.gz'],
        'tar': ['.tar'],
        'tar.gz': ['.tar.gz', '.tgz'],
        'tgz': ['.tar.gz', '.tgz'],
        'tar.bz2': ['.tar.bz2', '.tbz2'],
        'tbz2': ['.tar.bz2', '.tbz2'],
        'tar.xz': ['.tar.xz', '.txz'],
        'txz': ['.tar.xz', '.txz'],
    }
    
    # Compression modes for tarfile
    TAR_MODES = {
        'tar': 'w',
        'tar.gz': 'w:gz',
        'tgz': 'w:gz',
        'tar.bz2': 'w:bz2',
        'tbz2': 'w:bz2',
        'tar.xz': 'w:xz',
        'txz': 'w:xz',
    }
    
    # Read modes for tarfile
    TAR_READ_MODES = {
        'tar': 'r',
        'tar.gz': 'r:gz',
        'tgz': 'r:gz',
        'tar.bz2': 'r:bz2',
        'tbz2': 'r:bz2',
        'tar.xz': 'r:xz',
        'txz': 'r:xz',
    }

    @staticmethod
    def _normalize_path(path: PathLike) -> Path:
        """Normalize and resolve a path to absolute form."""
        return Path(path).expanduser().resolve()

    @staticmethod
    def _validate_archive_type(archive_type: Optional[str], archive_path: PathLike) -> str:
        """
        Validate and normalize archive type.
        
        Args:
            archive_type: Explicit archive type or None for auto-detection
            archive_path: Path to archive file for extension-based detection
            
        Returns:
            Normalized archive type string
            
        Raises:
            InvalidArchiveTypeError: If archive type is unsupported or cannot be determined
        """
        if archive_type:
            archive_type = archive_type.lower()
            if archive_type not in CompressionUtility.ARCHIVE_TYPES:
                raise InvalidArchiveTypeError(f"Unsupported archive type: {archive_type}")
            return archive_type
        
        # Auto-detect from file extension
        path = Path(archive_path)
        suffixes = ''.join(path.suffixes).lower()
        
        for atype, extensions in CompressionUtility.ARCHIVE_TYPES.items():
            if any(suffixes.endswith(ext) for ext in extensions):
                return atype
        
        raise InvalidArchiveTypeError(
            f"Cannot determine archive type from extension: {path}. "
            f"Please specify archive_type explicitly."
        )

    @staticmethod
    def _safe_extract_path(extract_dir: Path, member_path: str) -> Path:
        """
        Resolve extraction path with traversal protection.
        
        Args:
            extract_dir: Base extraction directory
            member_path: Archive member path
            
        Returns:
            Safe absolute path within extract_dir
            
        Raises:
            ExtractionError: If path traversal is detected
        """
        # Normalize paths
        extract_dir = extract_dir.resolve()
        member_path = os.path.normpath(member_path)
        
        # Resolve target path
        target_path = (extract_dir / member_path).resolve()
        
        # Ensure target is within extract_dir
        try:
            target_path.relative_to(extract_dir)
        except ValueError:
            raise ExtractionError(f"Path traversal attempt detected: {member_path}")
        
        return target_path

    @classmethod
    def compress_files(
        cls,
        archive_path: PathLike,
        file_paths: List[PathLike],
        archive_type: Optional[ArchiveType] = None,
        compression_level: int = 9,
        preserve_paths: bool = True
    ) -> None:
        """
        Compress a list of files into an archive.
        
        Args:
            archive_path: Output archive path
            file_paths: List of files to compress
            archive_type: Archive format (auto-detected from extension if None)
            compression_level: Compression level (0-9, default 9)
            preserve_paths: Whether to preserve directory structure in archive
            
        Raises:
            InvalidArchiveTypeError: If archive type is unsupported
            FileNotFoundError: If any input file doesn't exist
            CompressionError: If compression fails
        """
        archive_path = cls._normalize_path(archive_path)
        archive_type = cls._validate_archive_type(archive_type, archive_path)
        
        # Validate input files
        resolved_files = []
        for f in file_paths:
            f_path = cls._normalize_path(f)
            if not f_path.is_file():
                raise FileNotFoundError(f"Input file not found: {f_path}")
            resolved_files.append(f_path)
        
        # Ensure output directory exists
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if archive_type == 'zip':
                cls._compress_files_zip(archive_path, resolved_files, compression_level, preserve_paths)
            elif archive_type in ('gz', 'gzip'):
                cls._compress_files_gzip(archive_path, resolved_files, compression_level)
            else:  # tar variants
                cls._compress_files_tar(archive_path, resolved_files, archive_type, preserve_paths)
        except Exception as e:
            # Clean up partial archive on failure
            if archive_path.exists():
                archive_path.unlink(missing_ok=True)
            raise CompressionError(f"Compression failed: {e}") from e

    @classmethod
    def _compress_files_zip(
        cls,
        archive_path: Path,
        file_paths: List[Path],
        compression_level: int,
        preserve_paths: bool
    ) -> None:
        """Compress files to ZIP archive."""
        with zipfile.ZipFile(
            archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=compression_level
        ) as zf:
            for file_path in file_paths:
                if preserve_paths:
                    # Use relative path from current directory
                    arcname = file_path.relative_to(Path.cwd())
                else:
                    arcname = file_path.name
                zf.write(file_path, arcname)

    @classmethod
    def _compress_files_gzip(
        cls,
        archive_path: Path,
        file_paths: List[Path],
        compression_level: int
    ) -> None:
        """Compress files to GZIP (only supports single file)."""
        if len(file_paths) > 1:
            raise CompressionError("GZIP format only supports single file compression. Use TAR.GZ for multiple files.")
        
        file_path = file_paths[0]
        with open(file_path, 'rb') as f_in:
            with gzip.open(archive_path, 'wb', compresslevel=compression_level) as f_out:
                shutil.copyfileobj(f_in, f_out)

    @classmethod
    def _compress_files_tar(
        cls,
        archive_path: Path,
        file_paths: List[Path],
        archive_type: str,
        preserve_paths: bool
    ) -> None:
        """Compress files to TAR archive."""
        mode = cls.TAR_MODES[archive_type]
        with tarfile.open(archive_path, mode) as tf:
            for file_path in file_paths:
                if preserve_paths:
                    arcname = file_path.relative_to(Path.cwd())
                else:
                    arcname = file_path.name
                tf.add(file_path, arcname=arcname)

    @classmethod
    def compress_directory(
        cls,
        archive_path: PathLike,
        dir_path: PathLike,
        archive_type: Optional[ArchiveType] = None,
        compression_level: int = 9,
        include_root: bool = True
    ) -> None:
        """
        Compress an entire directory into an archive.
        
        Args:
            archive_path: Output archive path
            dir_path: Directory to compress
            archive_type: Archive format (auto-detected from extension if None)
            compression_level: Compression level (0-9, default 9)
            include_root: Whether to include directory name in archive
            
        Raises:
            InvalidArchiveTypeError: If archive type is unsupported
            FileNotFoundError: If directory doesn't exist
            CompressionError: If compression fails
        """
        archive_path = cls._normalize_path(archive_path)
        dir_path = cls._normalize_path(dir_path)
        archive_type = cls._validate_archive_type(archive_type, archive_path)
        
        if not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")
        
        # GZIP doesn't support directories directly
        if archive_type in ('gz', 'gzip'):
            raise CompressionError("GZIP format does not support directory compression. Use TAR.GZ instead.")
        
        # Ensure output directory exists
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if archive_type == 'zip':
                cls._compress_directory_zip(archive_path, dir_path, compression_level, include_root)
            else:  # tar variants
                cls._compress_directory_tar(archive_path, dir_path, archive_type, include_root)
        except Exception as e:
            if archive_path.exists():
                archive_path.unlink(missing_ok=True)
            raise CompressionError(f"Directory compression failed: {e}") from e

    @classmethod
    def _compress_directory_zip(
        cls,
        archive_path: Path,
        dir_path: Path,
        compression_level: int,
        include_root: bool
    ) -> None:
        """Compress directory to ZIP archive."""
        with zipfile.ZipFile(
            archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=compression_level
        ) as zf:
            root_dir = dir_path.parent if include_root else dir_path
            base_name = dir_path.name if include_root else ''
            
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(root_dir)
                    if base_name:
                        arcname = Path(base_name) / rel_path
                    else:
                        arcname = rel_path
                    zf.write(file_path, arcname)

    @classmethod
    def _compress_directory_tar(
        cls,
        archive_path: Path,
        dir_path: Path,
        archive_type: str,
        include_root: bool
    ) -> None:
        """Compress directory to TAR archive."""
        mode = cls.TAR_MODES[archive_type]
        with tarfile.open(archive_path, mode) as tf:
            if include_root:
                tf.add(dir_path, arcname=dir_path.name)
            else:
                for item in dir_path.iterdir():
                    tf.add(item, arcname=item.name)

    @classmethod
    def decompress(
        cls,
        archive_path: PathLike,
        extract_path: PathLike,
        archive_type: Optional[ArchiveType] = None,
        overwrite: bool = False
    ) -> None:
        """
        Decompress an archive to a directory.
        
        Args:
            archive_path: Path to archive file
            extract_path: Destination directory
            archive_type: Archive format (auto-detected from extension if None)
            overwrite: Whether to overwrite existing files
            
        Raises:
            ArchiveNotFoundError: If archive doesn't exist
            InvalidArchiveTypeError: If archive type is unsupported
            ExtractionError: If extraction fails or path traversal detected