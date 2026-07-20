import os
import zipfile
import gzip
import tarfile
from typing import Union, List
from pathlib import Path

def compress_single_file(format: str, src_path: str, dest_path: str) -> None:
    """
    Compress a single file into the specified archive format.

    Args:
    - format (str): Archive format. One of 'zip', 'gzip', 'tar'.
    - src_path (str): Path to the source file.
    - dest_path (str): Path to the destination archive.

    Raises:
    - ValueError: If format is not one of 'zip', 'gzip', 'tar'.
    - FileNotFoundError: If src_path does not exist.
    - PermissionError: If unable to read src_path or write to dest_path.
    """
    if format not in ['zip', 'gzip', 'tar']:
        raise ValueError("Invalid format. Supported formats: zip, gzip, tar")

    src = Path(src_path)
    dest = Path(dest_path)

    if not src.exists():
        raise FileNotFoundError(f"Source file '{src_path}' not found.")
    if not src.is_file():
        raise IsADirectoryError(f"Source '{src_path}' is a directory.")

    try:
        if format == 'zip':
            with zipfile.ZipFile(dest, 'w') as zip_file:
                zip_file.write(src, src.name)
        elif format == 'gzip':
            with open(src, 'rb') as f_in, gzip.open(dest, 'wb') as f_out:
                f_out.write(f_in.read())
        elif format == 'tar':
            with tarfile.open(dest, 'w') as tar_file:
                tar_file.add(src, arcname=src.name)
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {e.filename}") from e

def compress_directory(format: str, src_path: str, dest_path: str) -> None:
    """
    Compress a directory into the specified archive format.

    Args:
    - format (str): Archive format. One of 'zip', 'tar' (gzip for tar is handled internally).
    - src_path (str): Path to the source directory.
    - dest_path (str): Path to the destination archive.

    Raises:
    - ValueError: If format is not one of 'zip', 'tar'.
    - FileNotFoundError: If src_path does not exist.
    - PermissionError: If unable to read src_path or write to dest_path.
    """
    if format not in ['zip', 'tar']:
        raise ValueError("Invalid format for directory compression. Supported formats: zip, tar")

    src = Path(src_path)
    dest = Path(dest_path)

    if not src.exists():
        raise FileNotFoundError(f"Source directory '{src_path}' not found.")
    if not src.is_dir():
        raise NotADirectoryError(f"Source '{src_path}' is not a directory.")

    try:
        if format == 'zip':
            with zipfile.ZipFile(dest, 'w') as zip_file:
                for root, dirs, files in os.walk(src):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, src)
                        zip_file.write(file_path, rel_path)
        elif format == 'tar':
            with tarfile.open(dest, 'w:gz') as tar_file:
                tar_file.add(src, arcname=src.name)
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {e.filename}") from e

def decompress_file(format: str, src_path: str, dest_path: str) -> None:
    """
    Decompress an archive file into the specified destination.

    Args:
    - format (str): Archive format. One of 'zip', 'gzip', 'tar'.
    - src_path (str): Path to the source archive.
    - dest_path (str): Path to the destination directory.

    Raises:
    - ValueError: If format is not one of 'zip', 'gzip', 'tar'.
    - FileNotFoundError: If src_path does not exist.
    - PermissionError: If unable to read src_path or write to dest_path.
    - IsADirectoryError: If dest_path is a file.
    """
    if format not in ['zip', 'gzip', 'tar']:
        raise ValueError("Invalid format. Supported formats: zip, gzip, tar")

    src = Path(src_path)
    dest = Path(dest_path)

    if not src.exists():
        raise FileNotFoundError(f"Source archive '{src_path}' not found.")
    if dest.exists() and not dest.is_dir():
        raise IsADirectoryError(f"Destination '{dest_path}' is a file.")

    try:
        if format == 'zip':
            with zipfile.ZipFile(src, 'r') as zip_file:
                zip_file.extractall(dest)
        elif format == 'gzip':
            with gzip.open(src, 'rb') as f_in, open(dest / src.stem, 'wb') as f_out:
                f_out.write(f_in.read())
        elif format == 'tar':
            with tarfile.open(src, 'r') as tar_file:
                tar_file.extractall(dest)
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {e.filename}") from e

def list_archive_contents(format: str, src_path: str) -> List[str]:
    """
    List the contents of an archive file.

    Args:
    - format (str): Archive format. One of 'zip', 'gzip', 'tar'.
    - src_path (str): Path to the source archive.

    Returns:
    - List[str]: List of archive contents.

    Raises:
    - ValueError: If format is not one of 'zip', 'tar' (gzip not supported for listing).
    - FileNotFoundError: If src_path does not exist.
    - PermissionError: If unable to read src_path.
    """
    if format not in ['zip', 'tar']:
        raise ValueError("Invalid format for listing. Supported formats: zip, tar")

    src = Path(src_path)

    if not src.exists():
        raise FileNotFoundError(f"Source archive '{src_path}' not found.")

    try:
        if format == 'zip':
            with zipfile.ZipFile(src, 'r') as zip_file:
                return zip_file.namelist()
        elif format == 'tar':
            with tarfile.open(src, 'r') as tar_file:
                return tar_file.getnames()
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {e.filename}") from e

if __name__ == "__main__":
    # Example Usage
    try:
        # Compress a single file
        compress_single_file('zip', 'example.txt', 'example.zip')
        compress_single_file('gzip', 'example.txt', 'example.gz')
        compress_single_file('tar', 'example.txt', 'example.tar')

        # Compress a directory (using zip for demo)
        compress_directory('zip', './example_dir', 'example_dir.zip')

        # Decompress an archive
        decompress_file('zip', 'example.zip', './decompressed')
        decompress_file('gzip', 'example.gz', './decompressed_gzip')
        decompress_file('tar', 'example.tar', './decompressed_tar')

        # List archive contents
        print(list_archive_contents('zip', 'example.zip'))
        print(list_archive_contents('tar', 'example.tar'))
    except Exception as e:
        print(f"Error: {e}")