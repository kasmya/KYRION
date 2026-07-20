import argparse
import os
import pathlib
import shutil
import zipfile
import gzip
import tarfile
from typing import Union

def compress_zip(file_path: Union[str, pathlib.Path], output_path: Union[str, pathlib.Path]) -> None:
    """
    Compress a single file or directory into a ZIP archive.

    Args:
        file_path (str or pathlib.Path): Path to the file or directory to compress.
        output_path (str or pathlib.Path): Path to the output ZIP file.

    Raises:
        FileNotFoundError: If the input file or directory does not exist.
        IOError: If an I/O error occurs during compression.
    """
    try:
        with zipfile.ZipFile(output_path, 'w') as zip_file:
            if os.path.isfile(file_path):
                # Compress a single file
                zip_file.write(file_path, os.path.basename(file_path))
            elif os.path.isdir(file_path):
                # Compress a directory
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, file_path.parent)
                        zip_file.write(file_path, rel_path)
            else:
                raise FileNotFoundError(f"Input file or directory '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred during compression: {e}")

def compress_gzip(file_path: Union[str, pathlib.Path], output_path: Union[str, pathlib.Path]) -> None:
    """
    Compress a single file into a GZIP archive.

    Args:
        file_path (str or pathlib.Path): Path to the file to compress.
        output_path (str or pathlib.Path): Path to the output GZIP file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        IOError: If an I/O error occurs during compression.
    """
    try:
        with open(file_path, 'rb') as input_file, gzip.open(output_path, 'wb') as output_file:
            shutil.copyfileobj(input_file, output_file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred during compression: {e}")

def compress_tar(file_path: Union[str, pathlib.Path], output_path: Union[str, pathlib.Path]) -> None:
    """
    Compress a single file or directory into a TAR archive.

    Args:
        file_path (str or pathlib.Path): Path to the file or directory to compress.
        output_path (str or pathlib.Path): Path to the output TAR file.

    Raises:
        FileNotFoundError: If the input file or directory does not exist.
        IOError: If an I/O error occurs during compression.
    """
    try:
        with tarfile.open(output_path, 'w:gz') as tar_file:
            if os.path.isfile(file_path):
                # Compress a single file
                tar_file.add(file_path, os.path.basename(file_path))
            elif os.path.isdir(file_path):
                # Compress a directory
                tar_file.add(file_path, arcname=os.path.basename(file_path))
            else:
                raise FileNotFoundError(f"Input file or directory '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred during compression: {e}")

def decompress_zip(file_path: Union[str, pathlib.Path], output_path: Union[str, pathlib.Path]) -> None:
    """
    Decompress a ZIP archive into a directory.

    Args:
        file_path (str or pathlib.Path): Path to the ZIP file to decompress.
        output_path (str or pathlib.Path): Path to the output directory.

    Raises:
        FileNotFoundError: If the input ZIP file does not exist.
        IOError: If an I/O error occurs during decompression.
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            zip_file.extractall(output_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input ZIP file '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred during decompression: {e}")

def decompress_gzip(file_path: Union[str, pathlib.Path], output_path: Union[str, pathlib.Path]) -> None:
    """
    Decompress a GZIP archive into a file.

    Args:
        file_path (str or pathlib.Path): Path to the GZIP file to decompress.
        output_path (str or pathlib.Path): Path to the output file.

    Raises:
        FileNotFoundError: If the input GZIP file does not exist.
        IOError: If an I/O error occurs during decompression.
    """
    try:
        with gzip.open(file_path, 'rb') as input_file, open(output_path, 'wb') as output_file:
            shutil.copyfileobj(input_file, output_file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input GZIP file '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred during decompression: {e}")

def decompress_tar(file_path: Union[str, pathlib.Path], output_path: Union[str, pathlib.Path]) -> None:
    """
    Decompress a TAR archive into a directory.

    Args:
        file_path (str or pathlib.Path): Path to the TAR file to decompress.
        output_path (str or pathlib.Path): Path to the output directory.

    Raises:
        FileNotFoundError: If the input TAR file does not exist.
        IOError: If an I/O error occurs during decompression.
    """
    try:
        with tarfile.open(file_path, 'r:gz') as tar_file:
            tar_file.extractall(output_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input TAR file '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred during decompression: {e}")

def list_archive_contents(file_path: Union[str, pathlib.Path]) -> None:
    """
    List the contents of a ZIP, GZIP, or TAR archive.

    Args:
        file_path (str or pathlib.Path): Path to the archive file.

    Raises:
        FileNotFoundError: If the input archive file does not exist.
        IOError: If an I/O error occurs while listing the archive contents.
    """
    try:
        if file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                print("ZIP archive contents:")
                for file_info in zip_file.infolist():
                    print(file_info.filename)
        elif file_path.endswith('.gz'):
            with gzip.open(file_path, 'rb') as gzip_file:
                print("GZIP archive contents:")
                # GZIP files do not contain a file list, so we can only print the file name
                print(os.path.basename(file_path))
        elif file_path.endswith('.tar.gz') or file_path.endswith('.tgz'):
            with tarfile.open(file_path, 'r:gz') as tar_file:
                print("TAR archive contents:")
                for file_info in tar_file.getmembers():
                    print(file_info.name)
        else:
            raise ValueError(f"Unsupported archive format: {file_path}")
    except FileNotFoundError:
        raise FileNotFoundError(f"Input archive file '{file_path}' does not exist.")
    except IOError as e:
        raise IOError(f"An I/O error occurred while listing the archive contents: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description="File compression utility")
    subparsers = parser.add_subparsers(dest="command")

    compress_parser = subparsers.add_parser("compress")
    compress_parser.add_argument("file_path", help="Path to the file or directory to compress")
    compress_parser.add_argument("output_path", help="Path to the output archive file")
    compress_parser.add_argument("--format", choices=["zip", "gzip", "tar"], default="zip", help="Archive format")

    decompress_parser = subparsers.add_parser("decompress")
    decompress_parser.add_argument("file_path", help="Path to the archive file to decompress")
    decompress_parser.add_argument("output_path", help="Path to the output file or directory")
    decompress_parser.add_argument("--format", choices=["zip", "gzip", "tar"], default="zip", help="Archive format")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("file_path", help="Path to the archive file to list contents")

    args = parser.parse_args()

    if args.command == "compress":
        if args.format == "zip":
            compress_zip(args.file_path, args.output_path)
        elif args.format == "gzip":
            compress_gzip(args.file_path, args.output_path)
        elif args.format == "tar":
            compress_tar(args.file_path, args.output_path)
    elif args.command == "decompress":
        if args.format == "zip":
            decompress_zip(args.file_path, args.output_path)
        elif args.format == "gzip":
            decompress_gzip(args.file_path, args.output_path)
        elif args.format == "tar":
            decompress_tar(args.file_path, args.output_path)
    elif args.command == "list":
        list_archive_contents(args.file_path)

if __name__ == "__main__":
    main()