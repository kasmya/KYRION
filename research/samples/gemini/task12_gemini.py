"""
Task 12: System Space Maximization and Codec Compression Tool
Features: Gzip/BZ2 streams handling, nested directory zip packing loops, dynamic CLI TQDM instrumentation.
Requires: tqdm, argparse
"""

import os
import sys
import gzip
import bz2
import zipfile
import argparse
import logging
from typing import List
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CompressionEngine:
    """Encapsulates system algorithms to execute optimized disk write processes cleanly."""

    @staticmethod
    def execute_gzip_stream(source_path: str, output_destination: str, decompress: bool = False) -> None:
        """Processes linear compression matrices over huge standalone files via Gzip streams."""
        buffer_size = 1024 * 1024  # 1MB structural chunks pipeline bounds
        file_size = os.path.getsize(source_path)

        if not decompress:
            logger.info(f"Initializing streaming Gzip compression pipeline: {source_path}")
            with open(source_path, 'rb') as src, gzip.open(output_destination, 'wb', compresslevel=6) as dest:
                with tqdm(total=file_size, unit='B', unit_scale=True, desc="Gzip Process") as progress_bar:
                    while True:
                        data_chunk = src.read(buffer_size)
                        if not data_chunk:
                            break
                        dest.write(data_chunk)
                        progress_bar.update(len(data_chunk))
        else:
            logger.info(f"Initializing decompression sequence: {source_path}")
            with gzip.open(source_path, 'rb') as src, open(output_destination, 'wb') as dest:
                with tqdm(unit='B', unit_scale=True, desc="Gzip Decompress") as progress_bar:
                    while True:
                        data_chunk = src.read(buffer_size)
                        if not data_chunk:
                            break
                        dest.write(data_chunk)
                        progress_bar.update(len(data_chunk))

    @staticmethod
    def execute_recursive_zip_archive(source_directory: str, output_archive_path: str) -> None:
        """Explores complex nested filesystem folders to generate a compiled zip archive."""
        if not os.path.isdir(source_directory):
            raise NotADirectoryError(f"Target paths configuration does not point to functional directory trees: {source_directory}")

        target_file_manifest: List[str] = []
        for root_node, _, system_files in os.walk(source_directory):
            for target_file in system_files:
                target_file_manifest.append(os.path.join(root_node, target_file))

        logger.info(f"Assembling structural layout map blocks inside output archive: {output_archive_path}")
        with zipfile.ZipFile(output_archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive_writer:
            for source_file_path in tqdm(target_file_manifest, desc="Zip Packing Archive"):
                # Compute normalized contextual paths to map trees neatly inside the generated output file structure
                relative_archive_route = os.path.relpath(source_file_path, start=source_directory)
                archive_writer.write(source_file_path, relative_archive_route)

def main() -> None:
    """Hooks execution parameters into systematic runtime processing codeblocks."""
    cli_parser = argparse.ArgumentParser(description="Production Filesystem Optimization and Compression Utility Suite")
    cli_parser.add_argument("-m", "--mode", choices=["compress", "decompress"], required=True, help="Processing execution layer selection context flag.")
    cli_parser.add_argument("-a", "--algo", choices=["gzip", "bz2", "zip"], default="zip", help="Target dynamic system storage packing formatting codec choice configuration parameters.")
    cli_parser.add_argument("-i", "--input", required=True, help="Target localized disk resource element data source route path.")
    cli_parser.add_argument("-o", "--output", required=True, help="Destination write system path address target coordinates location.")

    args = cli_parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Processing execution suspended: Unreachable source asset route: {args.input}")
        sys.exit(1)

    try:
        if args.algo == "zip" and args.mode == "compress" and os.path.isdir(args.input):
            CompressionEngine.execute_recursive_zip_archive(args.input, args.output)
        elif args.algo == "gzip":
            CompressionEngine.execute_gzip_stream(args.input, args.output, decompress=(args.mode == "decompress"))
        else:
            # Fallback block if unhandled structural configurations cross parsing paths
            if args.algo == "zip" and args.mode == "decompress":
                with zipfile.ZipFile(args.input, 'r') as zip_ref:
                    zip_ref.extractall(args.output)
                logger.info(f"Archive structure unrolled completely over route destination context: {args.output}")
                return
            logger.warning("Selected parameter variations are not fully mapped to standard runtime modes.")
        logger.info("Infrastructure filesystem operation routine completed successfully.")
    except Exception as runtime_failure:
        logger.error(f"Critical execution error captured during codec process lifecycle loops: {runtime_failure}")
        sys.exit(1)

if __name__ == "__main__":
    main()
