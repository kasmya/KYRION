import os
import gzip
import shutil
import zipfile
import tarfile
from typing import Optional

def compress_to_zip(file_path: str, output_path: str) -> None:
    """Compress a single file or directory to a ZIP archive."""
    try:
        with zipfile.ZipFile(output_path, 'w') as zip_file:
            if os.path.isdir(file_path):
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        file_pathname = os.path.join(root, file)
                        rel_path = os.path.relpath(file_pathname, os.path.dirname(file_path))
                        zip_file.write(file_pathname, rel_path)
            else:
                zip_file.write(file_path, os.path.basename(file_path))
    except OSError as e:
        print(f"Error compressing to ZIP: {e}")
    except zipfile.BadZipFile as e:
        print(f"Invalid ZIP file: {e}")

def compress_to_gzip(file_path: str, output_path: str) -> None:
    """Compress a single file to a GZIP archive (does not support directories)."""
    if os.path.isdir(file_path):
        print("GZIP does not support directories. Use ZIP or TAR instead.")
        return
    try:
        with open(file_path, 'rb') as f_in, gzip.open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    except OSError as e:
        print(f"Error compressing to GZIP: {e}")

def compress_to_tar(file_path: str, output_path: str, compression: Optional[str] = None) -> None:
    """Compress a single file or directory to a TAR archive with optional compression."""
    mode = 'w'
    if compression:
        if compression.lower() == 'gz':
            mode += ':gz'
        elif compression.lower() in ['bz2', 'lzma']:
            mode += f':{compression.lower()}'
        else:
            print("Unsupported compression format for TAR. Defaulting to no compression.")
    try:
        with tarfile.open(output_path, mode) as tar:
            if os.path.isdir(file_path):
                tar.add(file_path)
            else:
                tar.add(file_path)
    except OSError as e:
        print(f"Error compressing to TAR: {e}")
    except tarfile.TarError as e:
        print(f"TAR operation failed: {e}")

def decompress_file(compressed_path: str, output_dir: str) -> None:
    """Decompress a file to the specified output directory."""
    try:
        if compressed_path.endswith('.zip'):
            with zipfile.ZipFile(compressed_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)
        elif compressed_path.endswith('.gz'):
            with gzip.open(compressed_path, 'rb') as f_in, open(os.path.join(output_dir, os.path.splitext(os.path.basename(compressed_path))[0]), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        elif compressed_path.endswith(('.tar', '.tar.gz', '.tar.bz2', '.tar.xz', '.tar.lzma')):
            with tarfile.open(compressed_path, 'r') as tar_ref:
                tar_ref.extractall(output_dir)
        else:
            print("Unsupported archive format for decompression.")
    except OSError as e:
        print(f"Error decompressing file: {e}")
    except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile) as e:
        print(f"Invalid archive file: {e}")

def list_archive_contents(compressed_path: str) -> None:
    """List the contents of an archive file."""
    try:
        if compressed_path.endswith('.zip'):
            with zipfile.ZipFile(compressed_path, 'r') as zip_ref:
                print(zip_ref.namelist())
        elif compressed_path.endswith(('.tar', '.tar.gz', '.tar.bz2', '.tar.xz', '.tar.lzma')):
            with tarfile.open(compressed_path, 'r') as tar_ref:
                print(tar_ref.getnames())
        elif compressed_path.endswith('.gz'):
            print("GZIP files do not support listing contents without decompression.")
        else:
            print("Unsupported archive format for listing contents.")
    except OSError as e:
        print(f"Error listing archive contents: {e}")
    except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile) as e:
        print(f"Invalid archive file: {e}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="File Compression Utility")
    subparsers = parser.add_subparsers(dest="command")

    # Compress to ZIP
    zip_parser = subparsers.add_parser("zip", help="Compress to ZIP")
    zip_parser.add_argument("file_path", help="Path to file or directory to compress")
    zip_parser.add_argument("output_path", help="Output ZIP file path")

    # Compress to GZIP
    gzip_parser = subparsers.add_parser("gzip", help="Compress to GZIP")
    gzip_parser.add_argument("file_path", help="Path to file to compress (directories not supported)")
    gzip_parser.add_argument("output_path", help="Output GZIP file path")

    # Compress to TAR
    tar_parser = subparsers.add_parser("tar", help="Compress to TAR")
    tar_parser.add_argument("file_path", help="Path to file or directory to compress")
    tar_parser.add_argument("output_path", help="Output TAR file path")
    tar_parser.add_argument("--compression", choices=['gz', 'bz2', 'lzma'], help="Compression format for TAR")

    # Decompress
    decompress_parser = subparsers.add_parser("decompress", help="Decompress a file")
    decompress_parser.add_argument("compressed_path", help="Path to compressed file")
    decompress_parser.add_argument("output_dir", help="Directory to extract to")

    # List Archive Contents
    list_parser = subparsers.add_parser("list", help="List archive contents")
    list_parser.add_argument("compressed_path", help="Path to archive file")

    args = parser.parse_args()

    if args.command == "zip":
        compress_to_zip(args.file_path, args.output_path)
    elif args.command == "gzip":
        compress_to_gzip(args.file_path, args.output_path)
    elif args.command == "tar":
        compress_to_tar(args.file_path, args.output_path, args.compression)
    elif args.command == "decompress":
        decompress_file(args.compressed_path, args.output_dir)
    elif args.command == "list":
        list_archive_contents(args.compressed_path)
    else:
        parser.print_help()