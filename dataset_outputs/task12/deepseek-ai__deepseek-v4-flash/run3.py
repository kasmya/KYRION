#!/usr/bin/env python3
"""
A file compression utility supporting ZIP, GZIP, and TAR formats.
Supports compression of single files and directories, decompression,
and listing archive contents with security and error handling.
"""

import os
import sys
import argparse
import zipfile
import gzip
import tarfile
import shutil
import stat
from pathlib import Path
from typing import Optional, List, Union, Literal
from enum import Enum

class Format(Enum):
    ZIP = "zip"
    GZIP = "gzip"
    TAR = "tar"

    def __str__(self):
        return self.value

class CompressionUtility:
    """Handles compression, decompression, and listing of archives."""

    def __init__(self, format: Format):
        self.format = format

    # ---------- Compression ----------
    def compress(self, input_path: Path, output_path: Optional[Path] = None) -> None:
        """
        Compress a single file or directory.

        Args:
            input_path: Path to file or directory to compress.
            output_path: Desired output archive path. If None, inferred from input and format.

        Raises:
            ValueError: If input does not exist or format inappropriate for directory.
            OSError: On file I/O errors.
        """
        if not input_path.exists():
            raise ValueError(f"Input path does not exist: {input_path}")

        if output_path is None:
            output_path = self._default_output_path(input_path)

        if input_path.is_dir():
            self._compress_directory(input_path, output_path)
        else:
            self._compress_file(input_path, output_path)

    def _compress_file(self, file_path: Path, output_path: Path) -> None:
        """Compress a single file."""
        if self.format == Format.ZIP:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(file_path, arcname=file_path.name)
        elif self.format == Format.GZIP:
            with open(file_path, 'rb') as f_in:
                with gzip.open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        elif self.format == Format.TAR:
            with tarfile.open(output_path, 'w') as tf:
                tf.add(file_path, arcname=file_path.name)
        else:
            raise ValueError(f"Unsupported format: {self.format}")

    def _compress_directory(self, dir_path: Path, output_path: Path) -> None:
        """Compress a directory. GZIP does not support directories directly."""
        if self.format == Format.GZIP:
            raise ValueError("GZIP format does not support directories. Use TAR or ZIP.")
        if self.format == Format.ZIP:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(dir_path):
                    for file in files:
                        full_path = Path(root, file)
                        arcname = full_path.relative_to(dir_path.parent)
                        zf.write(full_path, arcname=str(arcname))
        elif self.format == Format.TAR:
            with tarfile.open(output_path, 'w') as tf:
                tf.add(dir_path, arcname=dir_path.name)
        else:
            raise ValueError(f"Unsupported format: {self.format}")

    # ---------- Decompression ----------
    def decompress(self, archive_path: Path, output_dir: Optional[Path] = None) -> None:
        """
        Decompress an archive.

        Args:
            archive_path: Path to archive file.
            output_dir: Directory to extract to. If None, uses current directory.

        Raises:
            ValueError: If archive does not exist or format mismatch.
            SecurityError: If extraction would escape output directory.
        """
        if not archive_path.exists():
            raise ValueError(f"Archive does not exist: {archive_path}")

        if output_dir is None:
            output_dir = Path.cwd()
        output_dir = output_dir.resolve()

        if self.format == Format.ZIP:
            self._decompress_zip(archive_path, output_dir)
        elif self.format == Format.GZIP:
            self._decompress_gzip(archive_path, output_dir)
        elif self.format == Format.TAR:
            self._decompress_tar(archive_path, output_dir)
        else:
            raise ValueError(f"Unsupported format: {self.format}")

    def _decompress_zip(self, archive_path: Path, output_dir: Path) -> None:
        """Safely extract ZIP archive."""
        with zipfile.ZipFile(archive_path, 'r') as zf:
            for member in zf.namelist():
                # Security: prevent path traversal
                member_path = Path(member)
                target = (output_dir / member_path).resolve()
                if not str(target).startswith(str(output_dir)):
                    raise SecurityError(f"ZIP entry '{member}' would escape output directory")
                # Skip directories (handled by later extraction)
                if member.endswith('/'):
                    continue
                # Check for symlinks (zipfile may contain symlinks)
                info = zf.getinfo(member)
                if info.filename != member:   # only name, no direct symlink API in zipfile
                    pass
                # Extract the file
                zf.extract(member, path=output_dir)
            # Also extract directories (cleaner)
            zf.extractall(path=output_dir)

    def _decompress_gzip(self, archive_path: Path, output_dir: Path) -> None:
        """Decompress a .gz file to output_dir with original filename (if possible)."""
        if archive_path.suffix.lower() != '.gz':
            # Infer output name: strip .gz
            out_name = archive_path.stem
        else:
            out_name = archive_path.stem
        out_path = output_dir / out_name
        # Ensure not overwriting without warning? Simple overwrite.
        with gzip.open(archive_path, 'rb') as f_in:
            with open(out_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

    def _decompress_tar(self, archive_path: Path, output_dir: Path) -> None:
        """Safely extract tar archive with security checks."""
        with tarfile.open(archive_path, 'r') as tf:
            for member in tf.getmembers():
                # Security: path traversal
                member_path = Path(member.name)
                target = (output_dir / member_path).resolve()
                if not str(target).startswith(str(output_dir)):
                    raise SecurityError(f"Tar entry '{member.name}' would escape output directory")
                # Security: skip absolute paths or symlinks pointing outside
                if member.issym() or member.islnk():
                    # Resolve link target (if link points outside output dir, skip)
                    link_target = Path(member.linkname)
                    link_dest = (output_dir / link_target).resolve()
                    if not str(link_dest).startswith(str(output_dir)):
                        raise SecurityError(f"Symlink/link in tar points outside output")
                # Extract
                tf.extract(member, path=output_dir, set_attrs=False)

    # ---------- Listing ----------
    def list_contents(self, archive_path: Path) -> List[str]:
        """
        List contents of an archive.

        Args:
            archive_path: Path to archive.

        Returns:
            List of filenames/directories in the archive.

        Raises:
            ValueError: If archive does not exist.
        """
        if not archive_path.exists():
            raise ValueError(f"Archive does not exist: {archive_path}")

        if self.format == Format.ZIP:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                return zf.namelist()
        elif self.format == Format.TAR:
            with tarfile.open(archive_path, 'r') as tf:
                return [m.name for m in tf.getmembers()]
        elif self.format == Format.GZIP:
            # No listing support, return just the archive name
            return [archive_path.stem] if archive_path.suffix.lower() == '.gz' else [archive_path.name]
        else:
            raise ValueError(f"Unsupported format for listing: {self.format}")

    # ---------- Helpers ----------
    def _default_output_path(self, input_path: Path) -> Path:
        """Generate default output archive path based on input and format."""
        if self.format == Format.ZIP:
            return input_path.with_suffix('.zip')
        elif self.format == Format.GZIP:
            return input_path.with_suffix(input_path.suffix + '.gz')
        elif self.format == Format.TAR:
            return input_path.with_suffix('.tar')
        else:
            raise ValueError(f"Unknown format: {self.format}")

class SecurityError(Exception):
    """Raised when archive extraction would violate security constraints."""
    pass

# ---------- CLI ----------
def main():
    parser = argparse.ArgumentParser(
        description="File compression utility for ZIP, GZIP, TAR formats."
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Compress command
    comp_parser = subparsers.add_parser('compress', help='Compress file or directory')
    comp_parser.add_argument('input', type=Path, help='Path to file or directory')
    comp_parser.add_argument('-o', '--output', type=Path, default=None, help='Output archive path')
    comp_parser.add_argument('-f', '--format', type=Format, choices=list(Format), default=Format.ZIP,
                             help='Archive format (default: zip)')

    # Decompress command
    decomp_parser = subparsers.add_parser('decompress', help='Decompress archive')
    decomp_parser.add_argument('archive', type=Path, help='Path to archive file')
    decomp_parser.add_argument('-o', '--output', type=Path, default=None, help='Output directory')
    decomp_parser.add_argument('-f', '--format', type=Format, choices=list(Format), default=None,
                               help='Archive format (auto-detect if omitted)')

    # List command
    list_parser = subparsers.add_parser('list', help='List archive contents')
    list_parser.add_argument('archive', type=Path, help='Path to archive file')
    list_parser.add_argument('-f', '--format', type=Format, choices=list(Format), default=None,
                             help='Archive format (auto-detect if omitted)')

    args = parser.parse_args()

    try:
        if args.command == 'compress':
            util = CompressionUtility(args.format)
            util.compress(args.input, args.output)
            print(f"Compressed '{args.input}' -> '{util._default_output_path(args.input) if args.output is None else args.output}'")
        elif args.command == 'decompress':
            fmt = args.format or _detect_format(args.archive)
            util = CompressionUtility(fmt)
            util.decompress(args.archive, args.output)
            print(f"Decompressed '{args.archive}' to '{args.output or Path.cwd()}'")
        elif args.command == 'list':
            fmt = args.format or _detect_format(args.archive)
            util = CompressionUtility(fmt)
            contents = util.list_contents(args.archive)
            for item in contents:
                print(item)
    except (ValueError, OSError, SecurityError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def _detect_format(path: Path) -> Format:
    """Detect archive format from file extension."""
    suffix = path.suffix.lower()
    if suffix == '.zip':
        return Format.ZIP
    elif suffix == '.gz':
        return Format.GZIP
    elif suffix == '.tar':
        return Format.TAR
    elif suffix in ('.tar.gz', '.tgz'):
        return Format.TAR  # Actually gzip compressed tar, but we treat as TAR
    else:
        raise ValueError(f"Cannot detect archive format from extension: '{path}'")

if __name__ == '__main__':
    main()