import argparse
import gzip
import os
import shutil
import tarfile
import zipfile
from typing import Optional

def compress_zip(input_path: str, output_path: str) -> None:
    """
    Compress a single file or directory using ZIP format.

    Args:
        input_path (str): Path to the input file or directory.
        output_path (str): Path to the output ZIP file.
    """
    try:
        with zipfile.ZipFile(output_path, 'w') as zip_file:
            if os.path.isfile(input_path):
                zip_file.write(input_path, os.path.basename(input_path))
            elif os.path.isdir(input_path):
                for root, _, files in os.walk(input_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, start=os.path.dirname(input_path))
                        zip_file.write(file_path, rel_path)
            else:
                raise ValueError("Input path is not a file or directory")
    except OSError as e:
        print(f"Error compressing file: {e}")

def compress_gzip(input_path: str, output_path: str) -> None:
    """
    Compress a single file using GZIP format.

    Args:
        input_path (str): Path to the input file.
        output_path (str): Path to the output GZIP file.
    """
    try:
        with open(input_path, 'rb') as input_file, gzip.open(output_path, 'wb') as output_file:
            shutil.copyfileobj(input_file, output_file)
    except OSError as e:
        print(f"Error compressing file: {e}")

def compress_tar(input_path: str, output_path: str) -> None:
    """
    Compress a single file or directory using TAR format.

    Args:
        input_path (str): Path to the input file or directory.
        output_path (str): Path to the output TAR file.
    """
    try:
        with tarfile.open(output_path, 'w') as tar_file:
            if os.path.isfile(input_path):
                tar_file.add(input_path, arcname=os.path.basename(input_path))
            elif os.path.isdir(input_path):
                tar_file.add(input_path)
            else:
                raise ValueError("Input path is not a file or directory")
    except OSError as e:
        print(f"Error compressing file: {e}")

def decompress_zip(input_path: str, output_path: str) -> None:
    """
    Decompress a ZIP file.

    Args:
        input_path (str): Path to the input ZIP file.
        output_path (str): Path to the output directory.
    """
    try:
        with zipfile.ZipFile(input_path, 'r') as zip_file:
            zip_file.extractall(output_path)
    except OSError as e:
        print(f"Error decompressing file: {e}")

def decompress_gzip(input_path: str, output_path: str) -> None:
    """
    Decompress a GZIP file.

    Args:
        input_path (str): Path to the input GZIP file.
        output_path (str): Path to the output file.
    """
    try:
        with gzip.open(input_path, 'rb') as input_file, open(output_path, 'wb') as output_file:
            shutil.copyfileobj(input_file, output_file)
    except OSError as e:
        print(f"Error decompressing file: {e}")

def decompress_tar(input_path: str, output_path: str) -> None:
    """
    Decompress a TAR file.

    Args:
        input_path (str): Path to the input TAR file.
        output_path (str): Path to the output directory.
    """
    try:
        with tarfile.open(input_path, 'r') as tar_file:
            tar_file.extractall(output_path)
    except OSError as e:
        print(f"Error decompressing file: {e}")

def list_zip_contents(input_path: str) -> None:
    """
    List the contents of a ZIP file.

    Args:
        input_path (str): Path to the input ZIP file.
    """
    try:
        with zipfile.ZipFile(input_path, 'r') as zip_file:
            for file in zip_file.namelist():
                print(file)
    except OSError as e:
        print(f"Error listing file contents: {e}")

def list_tar_contents(input_path: str) -> None:
    """
    List the contents of a TAR file.

    Args:
        input_path (str): Path to the input TAR file.
    """
    try:
        with tarfile.open(input_path, 'r') as tar_file:
            for member in tar_file.getmembers():
                print(member.name)
    except OSError as e:
        print(f"Error listing file contents: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description="File compression utility")
    subparsers = parser.add_subparsers(dest="command")

    compress_parser = subparsers.add_parser("compress")
    compress_parser.add_argument("-f", "--format", choices=["zip", "gzip", "tar"], required=True)
    compress_parser.add_argument("-i", "--input", required=True)
    compress_parser.add_argument("-o", "--output", required=True)

    decompress_parser = subparsers.add_parser("decompress")
    decompress_parser.add_argument("-f", "--format", choices=["zip", "gzip", "tar"], required=True)
    decompress_parser.add_argument("-i", "--input", required=True)
    decompress_parser.add_argument("-o", "--output", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("-f", "--format", choices=["zip", "tar"], required=True)
    list_parser.add_argument("-i", "--input", required=True)

    args = parser.parse_args()

    if args.command == "compress":
        if args.format == "zip":
            compress_zip(args.input, args.output)
        elif args.format == "gzip":
            compress_gzip(args.input, args.output)
        elif args.format == "tar":
            compress_tar(args.input, args.output)
    elif args.command == "decompress":
        if args.format == "zip":
            decompress_zip(args.input, args.output)
        elif args.format == "gzip":
            decompress_gzip(args.input, args.output)
        elif args.format == "tar":
            decompress_tar(args.input, args.output)
    elif args.command == "list":
        if args.format == "zip":
            list_zip_contents(args.input)
        elif args.format == "tar":
            list_tar_contents(args.input)

if __name__ == "__main__":
    main()