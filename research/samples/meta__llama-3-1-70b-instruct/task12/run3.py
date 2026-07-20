import argparse
import gzip
import logging
import os
import shutil
import tarfile
import zipfile
from typing import Optional

def compress_zip(src: str, dst: str) -> None:
    """
    Compress a single file or directory into a ZIP archive.

    Args:
    src (str): The source file or directory to compress.
    dst (str): The destination ZIP archive.
    """
    try:
        with zipfile.ZipFile(dst, 'w') as zip_file:
            if os.path.isfile(src):
                zip_file.write(src, os.path.basename(src))
            elif os.path.isdir(src):
                for root, dirs, files in os.walk(src):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, src)
                        zip_file.write(file_path, rel_path)
            else:
                raise FileNotFoundError(f"{src} is not a file or directory")
    except Exception as e:
        logging.error(f"Error compressing to ZIP: {e}")

def compress_gzip(src: str, dst: str) -> None:
    """
    Compress a single file into a GZIP archive.

    Args:
    src (str): The source file to compress.
    dst (str): The destination GZIP archive.
    """
    try:
        with open(src, 'rb') as src_file, gzip.open(dst, 'wb') as gzip_file:
            shutil.copyfileobj(src_file, gzip_file)
    except Exception as e:
        logging.error(f"Error compressing to GZIP: {e}")

def compress_tar(src: str, dst: str) -> None:
    """
    Compress a single file or directory into a TAR archive.

    Args:
    src (str): The source file or directory to compress.
    dst (str): The destination TAR archive.
    """
    try:
        with tarfile.open(dst, 'w') as tar_file:
            if os.path.isfile(src):
                tar_file.add(src, os.path.basename(src))
            elif os.path.isdir(src):
                tar_file.add(src)
            else:
                raise FileNotFoundError(f"{src} is not a file or directory")
    except Exception as e:
        logging.error(f"Error compressing to TAR: {e}")

def decompress_zip(src: str, dst: str) -> None:
    """
    Decompress a ZIP archive.

    Args:
    src (str): The source ZIP archive.
    dst (str): The destination directory to decompress into.
    """
    try:
        with zipfile.ZipFile(src, 'r') as zip_file:
            zip_file.extractall(dst)
    except Exception as e:
        logging.error(f"Error decompressing ZIP: {e}")

def decompress_gzip(src: str, dst: str) -> None:
    """
    Decompress a GZIP archive.

    Args:
    src (str): The source GZIP archive.
    dst (str): The destination file to decompress into.
    """
    try:
        with gzip.open(src, 'rb') as gzip_file, open(dst, 'wb') as dst_file:
            shutil.copyfileobj(gzip_file, dst_file)
    except Exception as e:
        logging.error(f"Error decompressing GZIP: {e}")

def decompress_tar(src: str, dst: str) -> None:
    """
    Decompress a TAR archive.

    Args:
    src (str): The source TAR archive.
    dst (str): The destination directory to decompress into.
    """
    try:
        with tarfile.open(src, 'r') as tar_file:
            tar_file.extractall(dst)
    except Exception as e:
        logging.error(f"Error decompressing TAR: {e}")

def list_zip(src: str) -> None:
    """
    List the contents of a ZIP archive.

    Args:
    src (str): The source ZIP archive.
    """
    try:
        with zipfile.ZipFile(src, 'r') as zip_file:
            print(zip_file.namelist())
    except Exception as e:
        logging.error(f"Error listing ZIP contents: {e}")

def list_gzip(src: str) -> None:
    """
    List the contents of a GZIP archive.

    Args:
    src (str): The source GZIP archive.
    """
    try:
        with gzip.open(src, 'rb') as gzip_file:
            print(f"{src} is a GZIP archive")
    except Exception as e:
        logging.error(f"Error listing GZIP contents: {e}")

def list_tar(src: str) -> None:
    """
    List the contents of a TAR archive.

    Args:
    src (str): The source TAR archive.
    """
    try:
        with tarfile.open(src, 'r') as tar_file:
            print(tar_file.getnames())
    except Exception as e:
        logging.error(f"Error listing TAR contents: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description="File compression utility")
    subparsers = parser.add_subparsers(dest="command")

    compress_parser = subparsers.add_parser("compress")
    compress_parser.add_argument("-t", "--type", choices=["zip", "gzip", "tar"], required=True)
    compress_parser.add_argument("-s", "--src", required=True)
    compress_parser.add_argument("-d", "--dst", required=True)

    decompress_parser = subparsers.add_parser("decompress")
    decompress_parser.add_argument("-t", "--type", choices=["zip", "gzip", "tar"], required=True)
    decompress_parser.add_argument("-s", "--src", required=True)
    decompress_parser.add_argument("-d", "--dst", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("-t", "--type", choices=["zip", "gzip", "tar"], required=True)
    list_parser.add_argument("-s", "--src", required=True)

    args = parser.parse_args()

    if args.command == "compress":
        if args.type == "zip":
            compress_zip(args.src, args.dst)
        elif args.type == "gzip":
            compress_gzip(args.src, args.dst)
        elif args.type == "tar":
            compress_tar(args.src, args.dst)
    elif args.command == "decompress":
        if args.type == "zip":
            decompress_zip(args.src, args.dst)
        elif args.type == "gzip":
            decompress_gzip(args.src, args.dst)
        elif args.type == "tar":
            decompress_tar(args.src, args.dst)
    elif args.command == "list":
        if args.type == "zip":
            list_zip(args.src)
        elif args.type == "gzip":
            list_gzip(args.src)
        elif args.type == "tar":
            list_tar(args.src)

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    main()