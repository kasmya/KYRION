import argparse
import gzip
import io
import logging
import os
import pathlib
import shutil
import tarfile
import zipfile
from typing import Optional

def compress_zip(file_path: pathlib.Path, output_path: pathlib.Path, recursive: bool = False) -> None:
    """
    Compress a file or directory into a ZIP archive.

    Args:
        file_path (pathlib.Path): Path to the file or directory to compress.
        output_path (pathlib.Path): Path to the output ZIP file.
        recursive (bool): Whether to compress the directory recursively. Defaults to False.
    """
    with zipfile.ZipFile(output_path, 'w') as zip_file:
        if recursive:
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    file_path = pathlib.Path(root) / file
                    zip_file.write(file_path, file_path.relative_to(file_path.parent))
        else:
            zip_file.write(file_path, file_path.name)

def compress_gzip(file_path: pathlib.Path, output_path: pathlib.Path) -> None:
    """
    Compress a file into a GZIP archive.

    Args:
        file_path (pathlib.Path): Path to the file to compress.
        output_path (pathlib.Path): Path to the output GZIP file.
    """
    with open(file_path, 'rb') as file, gzip.open(output_path, 'wb') as gzip_file:
        shutil.copyfileobj(file, gzip_file)

def compress_tar(file_path: pathlib.Path, output_path: pathlib.Path, recursive: bool = False) -> None:
    """
    Compress a file or directory into a TAR archive.

    Args:
        file_path (pathlib.Path): Path to the file or directory to compress.
        output_path (pathlib.Path): Path to the output TAR file.
        recursive (bool): Whether to compress the directory recursively. Defaults to False.
    """
    with tarfile.open(output_path, 'w') as tar_file:
        if recursive:
            tar_file.add(file_path, arcname=os.path.basename(file_path))
        else:
            tar_file.add(file_path, arcname=file_path.name)

def decompress_zip(file_path: pathlib.Path, output_path: pathlib.Path) -> None:
    """
    Decompress a ZIP archive.

    Args:
        file_path (pathlib.Path): Path to the ZIP file to decompress.
        output_path (pathlib.Path): Path to the output directory.
    """
    with zipfile.ZipFile(file_path, 'r') as zip_file:
        zip_file.extractall(output_path)

def decompress_gzip(file_path: pathlib.Path, output_path: pathlib.Path) -> None:
    """
    Decompress a GZIP archive.

    Args:
        file_path (pathlib.Path): Path to the GZIP file to decompress.
        output_path (pathlib.Path): Path to the output file.
    """
    with gzip.open(file_path, 'rb') as gzip_file, open(output_path, 'wb') as file:
        shutil.copyfileobj(gzip_file, file)

def decompress_tar(file_path: pathlib.Path, output_path: pathlib.Path) -> None:
    """
    Decompress a TAR archive.

    Args:
        file_path (pathlib.Path): Path to the TAR file to decompress.
        output_path (pathlib.Path): Path to the output directory.
    """
    with tarfile.open(file_path, 'r') as tar_file:
        tar_file.extractall(output_path)

def list_zip(file_path: pathlib.Path) -> None:
    """
    List the contents of a ZIP archive.

    Args:
        file_path (pathlib.Path): Path to the ZIP file.
    """
    with zipfile.ZipFile(file_path, 'r') as zip_file:
        for file in zip_file.namelist():
            print(file)

def list_gzip(file_path: pathlib.Path) -> None:
    """
    List the contents of a GZIP archive.

    Args:
        file_path (pathlib.Path): Path to the GZIP file.
    """
    print(f"The GZIP file '{file_path}' contains a single file.")

def list_tar(file_path: pathlib.Path) -> None:
    """
    List the contents of a TAR archive.

    Args:
        file_path (pathlib.Path): Path to the TAR file.
    """
    with tarfile.open(file_path, 'r') as tar_file:
        for file in tar_file.getnames():
            print(file)

def main() -> None:
    parser = argparse.ArgumentParser(description='File Compression Utility')
    parser.add_argument('command', choices=['compress', 'decompress', 'list'])
    parser.add_argument('--format', choices=['zip', 'gzip', 'tar'])
    parser.add_argument('--recursive', action='store_true')
    parser.add_argument('file_path', type=pathlib.Path)
    parser.add_argument('output_path', type=pathlib.Path, nargs='?')

    args = parser.parse_args()

    if args.command == 'compress':
        if args.format == 'zip':
            compress_zip(args.file_path, args.output_path, args.recursive)
        elif args.format == 'gzip':
            compress_gzip(args.file_path, args.output_path)
        elif args.format == 'tar':
            compress_tar(args.file_path, args.output_path, args.recursive)
    elif args.command == 'decompress':
        if args.format == 'zip':
            decompress_zip(args.file_path, args.output_path)
        elif args.format == 'gzip':
            decompress_gzip(args.file_path, args.output_path)
        elif args.format == 'tar':
            decompress_tar(args.file_path, args.output_path)
    elif args.command == 'list':
        if args.format == 'zip':
            list_zip(args.file_path)
        elif args.format == 'gzip':
            list_gzip(args.file_path)
        elif args.format == 'tar':
            list_tar(args.file_path)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception as e:
        logging.error(f'An error occurred: {e}')