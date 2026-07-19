"""
File Compression Utility using gzip, bz2, zipfile.
Features:
- Compress/decompress files
- CLI with argparse
- Progress bar with tqdm
- Recursive directory compression
"""

import argparse
import gzip
import bz2
import zipfile
import os
from tqdm import tqdm
import logging

logging.basicConfig(level=logging.INFO)


def compress_file(input_file: str, output_file: str, method: str):
    with open(input_file, "rb") as f_in:
        data = f_in.read()
        if method == "gzip":
            with gzip.open(output_file, "wb") as f_out:
                f_out.write(data)
        elif method == "bz2":
            with bz2.open(output_file, "wb") as f_out:
                f_out.write(data)
        else:
            raise ValueError("Unsupported method")


def decompress_file(input_file: str, output_file: str, method: str):
    if method == "gzip":
        with gzip.open(input_file, "rb") as f_in:
            data = f_in.read()
    elif method == "bz2":
        with bz2.open(input_file, "rb") as f_in:
            data = f_in.read()
    else:
        raise ValueError("Unsupported method")
    with open(output_file, "wb") as f_out:
        f_out.write(data)


def compress_directory(directory: str, output_file: str):
    with zipfile.ZipFile(output_file, "w") as zipf:
        for root, _, files in os.walk(directory):
            for file in tqdm(files, desc="Compressing"):
                zipf.write(os.path.join(root, file))


def main():
    parser = argparse.ArgumentParser(description="File Compression Utility")
    parser.add_argument("action", choices=["compress", "decompress", "zipdir"])
    parser.add_argument("method", choices=["gzip", "bz2", "zip"], nargs="?")
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()

    if args.action == "compress":
        compress_file(args.input, args.output, args.method)
    elif args.action == "decompress":
        decompress_file(args.input, args.output, args.method)
    elif args.action == "zipdir":
        compress_directory(args.input, args.output)


if __name__ == "__main__":
    main()

