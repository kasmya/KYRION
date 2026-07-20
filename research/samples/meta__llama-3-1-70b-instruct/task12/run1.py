import argparse
import zipfile
import gzip
import tarfile
import os
import shutil
from typing import Union

def compress_zip(file_path: Union[str, bytes], output_path: str) -> None:
    """
    Compress a single file or directory into a ZIP archive.

    Args:
    file_path (str or bytes): The path to the file or directory to compress.
    output_path (str): The path to the output ZIP archive.
    """
    try:
        with zipfile.ZipFile(output_path, 'w') as zip_file:
            if os.path.isdir(file_path):
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        file_path_abs = os.path.join(root, file)
                        zip_file.write(file_path_abs, os.path.relpath(file_path_abs, file_path))
            else:
                zip_file.write(file_path, os.path.basename(file_path))
    except Exception as e:
        print(f"Error compressing file: {e}")

def compress_gzip(file_path: Union[str, bytes], output_path: str) -> None:
    """
    Compress a single file into a GZIP archive.

    Args:
    file_path (str or bytes): The path to the file to compress.
    output_path (str): The path to the output GZIP archive.
    """
    try:
        with open(file_path, 'rb') as file_in, gzip.open(output_path, 'wb') as file_out:
            shutil.copyfileobj(file_in, file_out)
    except Exception as e:
        print(f"Error compressing file: {e}")

def compress_tar(file_path: Union[str, bytes], output_path: str) -> None:
    """
    Compress a single file or directory into a TAR archive.

    Args:
    file_path (str or bytes): The path to the file or directory to compress.
    output_path (str): The path to the output TAR archive.
    """
    try:
        with tarfile.open(output_path, 'w') as tar_file:
            if os.path.isdir(file_path):
                tar_file.add(file_path)
            else:
                tar_file.add(file_path, os.path.basename(file_path))
    except Exception as e:
        print(f"Error compressing file: {e}")

def decompress_zip(file_path: Union[str, bytes], output_path: str) -> None:
    """
    Decompress a ZIP archive into a directory.

    Args:
    file_path (str or bytes): The path to the ZIP archive to decompress.
    output_path (str): The path to the output directory.
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            zip_file.extractall(output_path)
    except Exception as e:
        print(f"Error decompressing file: {e}")

def decompress_gzip(file_path: Union[str, bytes], output_path: str) -> None:
    """
    Decompress a GZIP archive into a file.

    Args:
    file_path (str or bytes): The path to the GZIP archive to decompress.
    output_path (str): The path to the output file.
    """
    try:
        with gzip.open(file_path, 'rb') as file_in, open(output_path, 'wb') as file_out:
            shutil.copyfileobj(file_in, file_out)
    except Exception as e:
        print(f"Error decompressing file: {e}")

def decompress_tar(file_path: Union[str, bytes], output_path: str) -> None:
    """
    Decompress a TAR archive into a directory.

    Args:
    file_path (str or bytes): The path to the TAR archive to decompress.
    output_path (str): The path to the output directory.
    """
    try:
        with tarfile.open(file_path, 'r') as tar_file:
            tar_file.extractall(output_path)
    except Exception as e:
        print(f"Error decompressing file: {e}")

def list_zip(file_path: Union[str, bytes]) -> None:
    """
    List the contents of a ZIP archive.

    Args:
    file_path (str or bytes): The path to the ZIP archive.
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            print(zip_file.namelist())
    except Exception as e:
        print(f"Error listing archive contents: {e}")

def list_tar(file_path: Union[str, bytes]) -> None:
    """
    List the contents of a TAR archive.

    Args:
    file_path (str or bytes): The path to the TAR archive.
    """
    try:
        with tarfile.open(file_path, 'r') as tar_file:
            print(tar_file.getnames())
    except Exception as e:
        print(f"Error listing archive contents: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description='File compression utility')
    subparsers = parser.add_subparsers(dest='command')

    zip_parser = subparsers.add_parser('zip', help='Compress a file or directory into a ZIP archive')
    zip_parser.add_argument('file_path', help='The path to the file or directory to compress')
    zip_parser.add_argument('output_path', help='The path to the output ZIP archive')
    zip_parser.set_defaults(func=compress_zip)

    gzip_parser = subparsers.add_parser('gzip', help='Compress a file into a GZIP archive')
    gzip_parser.add_argument('file_path', help='The path to the file to compress')
    gzip_parser.add_argument('output_path', help='The path to the output GZIP archive')
    gzip_parser.set_defaults(func=compress_gzip)

    tar_parser = subparsers.add_parser('tar', help='Compress a file or directory into a TAR archive')
    tar_parser.add_argument('file_path', help='The path to the file or directory to compress')
    tar_parser.add_argument('output_path', help='The path to the output TAR archive')
    tar_parser.set_defaults(func=compress_tar)

    unzip_parser = subparsers.add_parser('unzip', help='Decompress a ZIP archive into a directory')
    unzip_parser.add_argument('file_path', help='The path to the ZIP archive to decompress')
    unzip_parser.add_argument('output_path', help='The path to the output directory')
    unzip_parser.set_defaults(func=decompress_zip)

    gunzip_parser = subparsers.add_parser('gunzip', help='Decompress a GZIP archive into a file')
    gunzip_parser.add_argument('file_path', help='The path to the GZIP archive to decompress')
    gunzip_parser.add_argument('output_path', help='The path to the output file')
    gunzip_parser.set_defaults(func=decompress_gzip)

    untar_parser = subparsers.add_parser('untar', help='Decompress a TAR archive into a directory')
    untar_parser.add_argument('file_path', help='The path to the TAR archive to decompress')
    untar_parser.add_argument('output_path', help='The path to the output directory')
    untar_parser.set_defaults(func=decompress_tar)

    list_zip_parser = subparsers.add_parser('list_zip', help='List the contents of a ZIP archive')
    list_zip_parser.add_argument('file_path', help='The path to the ZIP archive')
    list_zip_parser.set_defaults(func=list_zip)

    list_tar_parser = subparsers.add_parser('list_tar', help='List the contents of a TAR archive')
    list_tar_parser.add_argument('file_path', help='The path to the TAR archive')
    list_tar_parser.set_defaults(func=list_tar)

    args = parser.parse_args()
    if args.command:
        args.func(args.file_path, args.output_path)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()