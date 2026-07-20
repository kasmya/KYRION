import argparse
import gzip
import os
import shutil
import tarfile
import zipfile
from typing import Optional

def compress_zip(file_path: str, output_path: str) -> None:
    """
    Compress a single file or directory into a ZIP archive.

    Args:
    file_path (str): The path to the file or directory to compress.
    output_path (str): The path to the output ZIP archive.
    """
    with zipfile.ZipFile(output_path, 'w') as zip_file:
        if os.path.isfile(file_path):
            zip_file.write(file_path, os.path.basename(file_path))
        elif os.path.isdir(file_path):
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, os.path.dirname(file_path))
                    zip_file.write(file_path, rel_path)

def compress_gzip(file_path: str, output_path: str) -> None:
    """
    Compress a single file into a GZIP archive.

    Args:
    file_path (str): The path to the file to compress.
    output_path (str): The path to the output GZIP archive.
    """
    with open(file_path, 'rb') as file, gzip.open(output_path, 'wb') as gzip_file:
        shutil.copyfileobj(file, gzip_file)

def compress_tar(file_path: str, output_path: str) -> None:
    """
    Compress a single file or directory into a TAR archive.

    Args:
    file_path (str): The path to the file or directory to compress.
    output_path (str): The path to the output TAR archive.
    """
    with tarfile.open(output_path, 'w') as tar_file:
        if os.path.isfile(file_path):
            tar_file.add(file_path, os.path.basename(file_path))
        elif os.path.isdir(file_path):
            tar_file.add(file_path)

def decompress_zip(file_path: str, output_path: str) -> None:
    """
    Decompress a ZIP archive to a directory.

    Args:
    file_path (str): The path to the ZIP archive to decompress.
    output_path (str): The path to the output directory.
    """
    with zipfile.ZipFile(file_path, 'r') as zip_file:
        zip_file.extractall(output_path)

def decompress_gzip(file_path: str, output_path: str) -> None:
    """
    Decompress a GZIP archive to a file.

    Args:
    file_path (str): The path to the GZIP archive to decompress.
    output_path (str): The path to the output file.
    """
    with gzip.open(file_path, 'rb') as gzip_file, open(output_path, 'wb') as file:
        shutil.copyfileobj(gzip_file, file)

def decompress_tar(file_path: str, output_path: str) -> None:
    """
    Decompress a TAR archive to a directory.

    Args:
    file_path (str): The path to the TAR archive to decompress.
    output_path (str): The path to the output directory.
    """
    with tarfile.open(file_path, 'r') as tar_file:
        tar_file.extractall(output_path)

def list_zip_contents(file_path: str) -> None:
    """
    List the contents of a ZIP archive.

    Args:
    file_path (str): The path to the ZIP archive to list.
    """
    with zipfile.ZipFile(file_path, 'r') as zip_file:
        print('ZIP Archive Contents:')
        for file in zip_file.namelist():
            print(file)

def list_tar_contents(file_path: str) -> None:
    """
    List the contents of a TAR archive.

    Args:
    file_path (str): The path to the TAR archive to list.
    """
    with tarfile.open(file_path, 'r') as tar_file:
        print('TAR Archive Contents:')
        for file in tar_file.getnames():
            print(file)

def list_gzip_contents(file_path: str) -> None:
    """
    List the contents of a GZIP archive.

    Args:
    file_path (str): The path to the GZIP archive to list.
    """
    print('GZIP Archive Contents:')
    print(os.path.basename(file_path))

def main() -> None:
    parser = argparse.ArgumentParser(description='File compression utility')
    subparsers = parser.add_subparsers(dest='command')

    compress_parser = subparsers.add_parser('compress', help='Compress a file or directory')
    compress_parser.add_argument('-f', '--format', choices=['zip', 'gzip', 'tar'], required=True)
    compress_parser.add_argument('-i', '--input', required=True)
    compress_parser.add_argument('-o', '--output', required=True)

    decompress_parser = subparsers.add_parser('decompress', help='Decompress an archive')
    decompress_parser.add_argument('-f', '--format', choices=['zip', 'gzip', 'tar'], required=True)
    decompress_parser.add_argument('-i', '--input', required=True)
    decompress_parser.add_argument('-o', '--output', required=True)

    list_parser = subparsers.add_parser('list', help='List the contents of an archive')
    list_parser.add_argument('-f', '--format', choices=['zip', 'gzip', 'tar'], required=True)
    list_parser.add_argument('-i', '--input', required=True)

    args = parser.parse_args()

    try:
        if args.command == 'compress':
            if args.format == 'zip':
                compress_zip(args.input, args.output)
            elif args.format == 'gzip':
                compress_gzip(args.input, args.output)
            elif args.format == 'tar':
                compress_tar(args.input, args.output)
        elif args.command == 'decompress':
            if args.format == 'zip':
                decompress_zip(args.input, args.output)
            elif args.format == 'gzip':
                decompress_gzip(args.input, args.output)
            elif args.format == 'tar':
                decompress_tar(args.input, args.output)
        elif args.command == 'list':
            if args.format == 'zip':
                list_zip_contents(args.input)
            elif args.format == 'gzip':
                list_gzip_contents(args.input)
            elif args.format == 'tar':
                list_tar_contents(args.input)
    except FileNotFoundError as e:
        print(f'Error: {e}')
    except IsADirectoryError as e:
        print(f'Error: {e}')
    except NotADirectoryError as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    main()