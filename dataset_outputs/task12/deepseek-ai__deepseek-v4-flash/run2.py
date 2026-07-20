import gzip
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import List, Optional


class CompressionUtility:
    """
    A utility class for compressing and decompressing files using ZIP, GZIP, and TAR formats.
    Supports compression of single files and directories, decompression, and listing archive contents.
    """

    SUPPORTED_FORMATS = {'zip', 'gzip', 'tar'}

    @staticmethod
    def _validate_path(path: str) -> Path:
        """Validate and resolve a file/directory path, preventing directory traversal."""
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        return resolved

    @staticmethod
    def _validate_format(fmt: str) -> None:
        """Check if format is supported."""
        if fmt.lower() not in CompressionUtility.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format '{fmt}'. Choose from {CompressionUtility.SUPPORTED_FORMATS}")

    @staticmethod
    def _safe_extract_zip(zf: zipfile.ZipFile, output_dir: Path) -> None:
        """Extract zip archive safely, preventing path traversal."""
        output_dir.mkdir(parents=True, exist_ok=True)
        for member in zf.infolist():
            # Normalize path and ensure it's within output directory
            member_path = (output_dir / member.filename).resolve()
            if not str(member_path).startswith(str(output_dir.resolve())):
                raise SecurityError(f"Attempted path traversal: {member.filename}")
            # Ensure directory structure exists
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
            else:
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(member_path, 'wb') as target:
                    shutil.copyfileobj(source, target)

    @staticmethod
    def _safe_extract_tar(tf: tarfile.TarFile, output_dir: Path) -> None:
        """Extract tar archive safely, preventing path traversal."""
        output_dir.mkdir(parents=True, exist_ok=True)
        # On Python 3.12+ we could use data_filter, but for compatibility we implement manually
        for member in tf.getmembers():
            # Prevent absolute paths and directory traversal
            if member.name.startswith('/') or '..' in member.name:
                raise SecurityError(f"Unsafe path in archive: {member.name}")
            member_path = (output_dir / member.name).resolve()
            if not str(member_path).startswith(str(output_dir.resolve())):
                raise SecurityError(f"Attempted path traversal: {member.name}")
            if member.isfile():
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with open(member_path, 'wb') as f:
                    f.write(tf.extractfile(member).read())
            elif member.isdir():
                member_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compress_file(file_path: str, archive_path: str, fmt: str = 'zip') -> None:
        """
        Compress a single file into an archive.

        :param file_path: Path to the file to compress.
        :param archive_path: Path for the output archive.
        :param fmt: Compression format ('zip', 'gzip', 'tar').
        :raises FileNotFoundError: If the input file does not exist.
        :raises ValueError: If format is unsupported.
        :raises OSError: On I/O errors.
        :raises SecurityError: On path security violations.
        """
        src = CompressionUtility._validate_path(file_path)
        if not src.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        CompressionUtility._validate_format(fmt)
        archive_path = Path(archive_path)

        fmt = fmt.lower()
        try:
            if fmt == 'gzip':
                # gzip compresses a single file; keeping original extension is common
                with open(src, 'rb') as f_in, gzip.open(archive_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            elif fmt == 'zip':
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(src, arcname=src.name)
            elif fmt == 'tar':
                with tarfile.open(archive_path, 'w:gz') as tf:
                    tf.add(src, arcname=src.name)
        except OSError as e:
            raise OSError(f"Failed to compress file: {e}") from e

    @staticmethod
    def compress_directory(dir_path: str, archive_path: str, fmt: str = 'zip') -> None:
        """
        Compress a directory and its contents into an archive.

        :param dir_path: Path to the directory to compress.
        :param archive_path: Path for the output archive.
        :param fmt: Compression format ('zip' or 'tar'). GZIP is not supported for directories.
        :raises FileNotFoundError: If the directory does not exist.
        :raises ValueError: If format is unsupported or if gzip is used for a directory.
        :raises OSError: On I/O errors.
        :raises SecurityError: On path security violations.
        """
        src = CompressionUtility._validate_path(dir_path)
        if not src.is_dir():
            raise ValueError(f"Path is not a directory: {dir_path}")
        CompressionUtility._validate_format(fmt)
        if fmt.lower() == 'gzip':
            raise ValueError("GZIP does not support directory compression. Use TAR or ZIP.")
        archive_path = Path(archive_path)

        fmt = fmt.lower()
        try:
            if fmt == 'zip':
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(src):
                        for file in files:
                            full_path = Path(root) / file
                            arcname = full_path.relative_to(src.parent)
                            zf.write(full_path, arcname=arcname)
            elif fmt == 'tar':
                with tarfile.open(archive_path, 'w:gz') as tf:
                    tf.add(src, arcname=src.name)
        except OSError as e:
            raise OSError(f"Failed to compress directory: {e}") from e

    @staticmethod
    def decompress_file(archive_path: str, output_dir: str, fmt: Optional[str] = None) -> None:
        """
        Decompress an archive into the specified output directory.

        :param archive_path: Path to the archive to decompress.
        :param output_dir: Directory to extract files into.
        :param fmt: Format of the archive. If None, it is inferred from the file extension.
        :raises FileNotFoundError: If archive does not exist.
        :raises ValueError: If format cannot be inferred or is unsupported.
        :raises OSError: On I/O errors.
        :raises SecurityError: On path traversal attempts.
        """
        archive = CompressionUtility._validate_path(archive_path)
        if not archive.is_file():
            raise ValueError(f"Path is not a file: {archive_path}")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        if fmt is None:
            # Infer from file extension
            suffix = archive.suffix.lower()
            if suffix == '.zip':
                fmt = 'zip'
            elif suffix in ('.gz', '.gzip'):
                fmt = 'gzip'
            elif suffix in ('.tar', '.tar.gz', '.tgz'):
                fmt = 'tar'
            else:
                raise ValueError(f"Cannot infer format from extension {suffix}. Please specify format.")
        else:
            CompressionUtility._validate_format(fmt)
            fmt = fmt.lower()

        try:
            if fmt == 'gzip':
                # gzip decompresses to a single file; output file name is archive name without .gz
                output_file = out / archive.stem
                with gzip.open(archive, 'rb') as f_in, open(output_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            elif fmt == 'zip':
                with zipfile.ZipFile(archive, 'r') as zf:
                    CompressionUtility._safe_extract_zip(zf, out)
            elif fmt == 'tar':
                with tarfile.open(archive, 'r:*') as tf:
                    CompressionUtility._safe_extract_tar(tf, out)
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as e:
            raise OSError(f"Failed to decompress archive: {e}") from e

    @staticmethod
    def list_contents(archive_path: str, fmt: Optional[str] = None) -> List[str]:
        """
        List the contents of an archive.

        :param archive_path: Path to the archive.
        :param fmt: Format of the archive. If None, inferred from extension.
        :return: List of filenames (and directory names) inside the archive.
        :raises FileNotFoundError: If archive does not exist.
        :raises ValueError: If format cannot be inferred or is unsupported.
        :raises OSError: On I/O errors.
        """
        archive = CompressionUtility._validate_path(archive_path)
        if not archive.is_file():
            raise ValueError(f"Path is not a file: {archive_path}")

        if fmt is None:
            suffix = archive.suffix.lower()
            if suffix == '.zip':
                fmt = 'zip'
            elif suffix in ('.gz', '.gzip'):
                fmt = 'gzip'
            elif suffix in ('.tar', '.tar.gz', '.tgz'):
                fmt = 'tar'
            else:
                raise ValueError(f"Cannot infer format from extension {suffix}. Please specify format.")
        else:
            CompressionUtility._validate_format(fmt)
            fmt = fmt.lower()

        contents = []
        try:
            if fmt == 'gzip':
                # gzip archives contain a single file (compressed stream); we only know the original name if embedded
                # We can show the archive name and compressed size
                file_size = archive.stat().st_size
                contents.append(f"{archive.name} (compressed size: {file_size} bytes)")
            elif fmt == 'zip':
                with zipfile.ZipFile(archive, 'r') as zf:
                    contents = [info.filename for info in zf.infolist()]
            elif fmt == 'tar':
                with tarfile.open(archive, 'r:*') as tf:
                    contents = [member.name for member in tf.getmembers()]
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as e:
            raise OSError(f"Failed to read archive: {e}") from e

        return contents


class SecurityError(Exception):
    """Exception raised for security violations (e.g., path traversal)."""
    pass


def main():
    """Command-line interface for the compression utility."""
    import argparse

    parser = argparse.ArgumentParser(description="File compression utility supporting ZIP, GZIP, TAR.")
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Compress command
    compress_parser = subparsers.add_parser('compress', help='Compress files or directories')
    compress_parser.add_argument('source', help='Source file or directory path')
    compress_parser.add_argument('archive', help='Output archive path')
    compress_parser.add_argument('-f', '--format', choices=['zip', 'gzip', 'tar'], default='zip',
                                 help='Archive format (default: zip)')
    compress_parser.add_argument('--type', dest='compress_type', choices=['file', 'dir'], default='file',
                                 help='Type of source: file or directory (default: file)')

    # Decompress command
    decompress_parser = subparsers.add_parser('decompress', help='Decompress an archive')
    decompress_parser.add_argument('archive', help='Archive path')
    decompress_parser.add_argument('output', help='Output directory')
    decompress_parser.add_argument('-f', '--format', choices=['zip', 'gzip', 'tar'], default=None,
                                   help='Archive format (inferred from extension if not specified)')

    # List command
    list_parser = subparsers.add_parser('list', help='List contents of an archive')
    list_parser.add_argument('archive', help='Archive path')
    list_parser.add_argument('-f', '--format', choices=['zip', 'gzip', 'tar'], default=None,
                             help='Archive format (inferred from extension if not specified)')

    args = parser.parse_args()

    try:
        if args.command == 'compress':
            if args.compress_type == 'file':
                CompressionUtility.compress_file(args.source, args.archive, args.format)
            else:
                CompressionUtility.compress_directory(args.source, args.archive, args.format)
            print(f"Compression successful: {args.archive}")
        elif args.command == 'decompress':
            CompressionUtility.decompress_file(args.archive, args.output, args.format)
            print(f"Decompression successful to: {args.output}")
        elif args.command == 'list':
            items = CompressionUtility.list_contents(args.archive, args.format)
            print(f"Contents of {args.archive}:")
            for item in items:
                print(f"  {item}")
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.exit(1)


if __name__ == '__main__':
    main()