"""
### Task 12: File Compression Utility (CLI)

A command-line utility supporting compression/decompression with gzip, bz2,
and zip, including recursive directory compression via zip and progress bars.

Requirements:
    pip install tqdm

Usage:
    python 12_file_compression_utility.py compress --method gzip -i input.txt -o output.gz
    python 12_file_compression_utility.py decompress --method gzip -i output.gz -o input.txt
    python 12_file_compression_utility.py compress --method zip -i my_dir/ -o archive.zip
    python 12_file_compression_utility.py decompress --method zip -i archive.zip -o extracted/
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List

from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("file_compression_utility")

CHUNK_SIZE = 1024 * 1024  # 1 MiB


class CompressionError(Exception):
    """Raised when a compression or decompression operation fails."""


def _stream_copy_with_progress(src_path: Path, dst_path: Path, opener_src, opener_dst) -> None:
    """Copies bytes from src to dst through the given opener callables, showing progress."""
    total_size = src_path.stat().st_size if src_path.exists() else 0
    with opener_src(src_path) as fin, opener_dst(dst_path) as fout:
        with tqdm(total=total_size, unit="B", unit_scale=True, desc=dst_path.name) as pbar:
            while True:
                chunk = fin.read(CHUNK_SIZE)
                if not chunk:
                    break
                fout.write(chunk)
                pbar.update(len(chunk))


def compress_gzip(input_path: Path, output_path: Path) -> None:
    """Compresses a single file using gzip."""
    if not input_path.is_file():
        raise CompressionError(f"gzip compression requires a single file, got: {input_path}")
    _stream_copy_with_progress(
        input_path,
        output_path,
        lambda p: open(p, "rb"),
        lambda p: gzip.open(p, "wb"),
    )


def decompress_gzip(input_path: Path, output_path: Path) -> None:
    """Decompresses a gzip file back to its original form."""
    _stream_copy_with_progress(
        input_path,
        output_path,
        lambda p: gzip.open(p, "rb"),
        lambda p: open(p, "wb"),
    )


def compress_bz2(input_path: Path, output_path: Path) -> None:
    """Compresses a single file using bz2."""
    if not input_path.is_file():
        raise CompressionError(f"bz2 compression requires a single file, got: {input_path}")
    _stream_copy_with_progress(
        input_path,
        output_path,
        lambda p: open(p, "rb"),
        lambda p: bz2.open(p, "wb"),
    )


def decompress_bz2(input_path: Path, output_path: Path) -> None:
    """Decompresses a bz2 file back to its original form."""
    _stream_copy_with_progress(
        input_path,
        output_path,
        lambda p: bz2.open(p, "rb"),
        lambda p: open(p, "wb"),
    )


def _iter_files(directory: Path) -> Iterable[Path]:
    """Recursively yields all files under a directory."""
    for root, _dirs, files in os.walk(directory):
        for name in files:
            yield Path(root) / name


def compress_zip(input_path: Path, output_path: Path) -> None:
    """Compresses a file or directory (recursively) into a zip archive."""
    if input_path.is_dir():
        files: List[Path] = list(_iter_files(input_path))
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in tqdm(files, desc="Zipping", unit="file"):
                arcname = file_path.relative_to(input_path.parent)
                zf.write(file_path, arcname=str(arcname))
    elif input_path.is_file():
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            with tqdm(total=1, desc="Zipping", unit="file") as pbar:
                zf.write(input_path, arcname=input_path.name)
                pbar.update(1)
    else:
        raise CompressionError(f"Input path does not exist: {input_path}")


def decompress_zip(input_path: Path, output_path: Path) -> None:
    """Extracts a zip archive into a target directory."""
    if not zipfile.is_zipfile(input_path):
        raise CompressionError(f"{input_path} is not a valid zip archive")

    output_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_path, "r") as zf:
        members = zf.infolist()
        for member in tqdm(members, desc="Extracting", unit="file"):
            zf.extract(member, path=output_path)


COMPRESSORS = {
    "gzip": (compress_gzip, decompress_gzip),
    "bz2": (compress_bz2, decompress_bz2),
    "zip": (compress_zip, decompress_zip),
}


def build_parser() -> argparse.ArgumentParser:
    """Builds the argparse CLI parser."""
    parser = argparse.ArgumentParser(description="Compress or decompress files and directories.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    for action in ("compress", "decompress"):
        sub = subparsers.add_parser(action, help=f"{action} a file or directory")
        sub.add_argument(
            "--method", "-m", choices=COMPRESSORS.keys(), required=True, help="Compression method"
        )
        sub.add_argument("--input", "-i", required=True, help="Input path")
        sub.add_argument("--output", "-o", required=True, help="Output path")

    return parser


def main(argv: List[str] = None) -> int:
    """CLI entry point. Returns process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    compress_fn, decompress_fn = COMPRESSORS[args.method]

    try:
        if not input_path.exists():
            raise CompressionError(f"Input path does not exist: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if args.action == "compress":
            compress_fn(input_path, output_path)
        else:
            decompress_fn(input_path, output_path)

        logger.info("Successfully completed '%s' using method '%s'", args.action, args.method)
        return 0
    except CompressionError as exc:
        logger.error("Compression error: %s", exc)
        return 1
    except OSError as exc:
        logger.error("File system error: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level CLI safety net
        logger.exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
