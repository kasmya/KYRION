"""
File Compression Utility with support for multiple formats.

Features:
- Compress/decompress with gzip, bz2, zip
- Command-line interface with argparse
- Progress bar with tqdm
- Recursive directory compression (zip)
- File integrity verification
"""

import os
import sys
import gzip
import bz2
import zipfile
import tarfile
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
import argparse

from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FileCompressor:
    """Handles file compression and decompression operations."""
    
    SUPPORTED_FORMATS = ['gzip', 'bz2', 'zip', 'tar', 'tar.gz', 'tar.bz2']
    
    def __init__(self, chunk_size: int = 8192):
        """
        Initialize compressor.
        
        Args:
            chunk_size: Buffer size for file operations
        """
        self.chunk_size = chunk_size
    
    def compress_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        method: str = 'gzip',
        compression_level: int = 9,
        show_progress: bool = True
    ) -> str:
        """
        Compress a single file.
        
        Args:
            input_path: Path to input file
            output_path: Path for compressed output
            method: Compression method (gzip, bz2, zip)
            compression_level: Compression level (1-9)
            show_progress: Show progress bar
            
        Returns:
            Path to compressed file
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        if not input_path.is_file():
            raise ValueError(f"Input must be a file: {input_path}")
        
        # Determine output path
        if output_path is None:
            suffix_map = {'gzip': '.gz', 'bz2': '.bz2', 'zip': '.zip'}
            suffix = suffix_map.get(method, '.compressed')
            output_path = input_path.with_suffix(input_path.suffix + suffix)
        else:
            output_path = Path(output_path)
        
        # Get file size for progress bar
        file_size = input_path.stat().st_size
        
        logger.info(f"Compressing: {input_path} -> {output_path}")
        logger.info(f"Method: {method}, Level: {compression_level}")
        
        try:
            if method == 'gzip':
                self._compress_gzip(input_path, output_path, compression_level, file_size, show_progress)
            elif method == 'bz2':
                self._compress_bz2(input_path, output_path, compression_level, file_size, show_progress)
            elif method == 'zip':
                self._compress_zip(input_path, output_path, compression_level, file_size, show_progress)
            else:
                raise ValueError(f"Unsupported compression method: {method}")
            
            # Verify compression
            compressed_size = output_path.stat().st_size
            compression_ratio = (1 - compressed_size / file_size) * 100
            
            logger.info(f"Compression complete: {output_path}")
            logger.info(f"Original size: {self._format_size(file_size)}")
            logger.info(f"Compressed size: {self._format_size(compressed_size)}")
            logger.info(f"Compression ratio: {compression_ratio:.1f}%")
            
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Compression failed: {str(e)}")
            if output_path.exists():
                output_path.unlink()
            raise
    
    def _compress_gzip(
        self, input_path: Path, output_path: Path,
        level: int, file_size: int, show_progress: bool
    ) -> None:
        """Compress using gzip."""
        with open(input_path, 'rb') as f_in:
            with gzip.open(output_path, 'wb', compresslevel=level) as f_out:
                if show_progress:
                    with tqdm(total=file_size, unit='B', unit_scale=True, desc='Compressing') as pbar:
                        while True:
                            chunk = f_in.read(self.chunk_size)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            pbar.update(len(chunk))
                else:
                    shutil.copyfileobj(f_in, f_out)
    
    def _compress_bz2(
        self, input_path: Path, output_path: Path,
        level: int, file_size: int, show_progress: bool
    ) -> None:
        """Compress using bz2."""
        with open(input_path, 'rb') as f_in:
            with bz2.open(output_path, 'wb', compresslevel=level) as f_out:
                if show_progress:
                    with tqdm(total=file_size, unit='B', unit_scale=True, desc='Compressing') as pbar:
                        while True:
                            chunk = f_in.read(self.chunk_size)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            pbar.update(len(chunk))
                else:
                    shutil.copyfileobj(f_in, f_out)
    
    def _compress_zip(
        self, input_path: Path, output_path: Path,
        level: int, file_size: int, show_progress: bool
    ) -> None:
        """Compress using zip."""
        compression = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(output_path, 'w', compression, compresslevel=level) as zf:
            if show_progress:
                with tqdm(total=file_size, unit='B', unit_scale=True, desc='Compressing') as pbar:
                    zf.write(input_path, input_path.name)
                    pbar.update(file_size)
            else:
                zf.write(input_path, input_path.name)
    
    def compress_directory(
        self,
        input_dir: str,
        output_path: str,
        method: str = 'zip',
        compression_level: int = 6,
        show_progress: bool = True
    ) -> str:
        """
        Compress an entire directory recursively.
        
        Args:
            input_dir: Directory to compress
            output_path: Output archive path
            method: Compression method (zip, tar, tar.gz, tar.bz2)
            compression_level: Compression level
            show_progress: Show progress bar
            
        Returns:
            Path to compressed archive
        """
        input_dir = Path(input_dir)
        output_path = Path(output_path)
        
        if not input_dir.exists():
            raise FileNotFoundError(f"Directory not found: {input_dir}")
        
        if not input_dir.is_dir():
            raise ValueError(f"Input must be a directory: {input_dir}")
        
        # Get total size for progress
        total_size = sum(f.stat().st_size for f in input_dir.rglob('*') if f.is_file())
        
        logger.info(f"Compressing directory: {input_dir} -> {output_path}")
        logger.info(f"Method: {method}")
        logger.info(f"Total files size: {self._format_size(total_size)}")
        
        try:
            if method == 'zip':
                self._compress_dir_zip(input_dir, output_path, compression_level, show_progress)
            elif method in ['tar', 'tar.gz', 'tar.bz2']:
                mode_map = {
                    'tar': 'w',
                    'tar.gz': 'w:gz',
                    'tar.bz2': 'w:bz2'
                }
                self._compress_dir_tar(input_dir, output_path, mode_map[method], show_progress)
            else:
                raise ValueError(f"Unsupported directory compression method: {method}")
            
            compressed_size = output_path.stat().st_size
            compression_ratio = (1 - compressed_size / total_size) * 100 if total_size > 0 else 0
            
            logger.info(f"Compression complete: {output_path}")
            logger.info(f"Compressed size: {self._format_size(compressed_size)}")
            logger.info(f"Compression ratio: {compression_ratio:.1f}%")
            
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Directory compression failed: {str(e)}")
            if output_path.exists():
                output_path.unlink()
            raise
    
    def _compress_dir_zip(
        self, input_dir: Path, output_path: Path,
        level: int, show_progress: bool
    ) -> None:
        """Compress directory as ZIP."""
        compression = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(output_path, 'w', compression, compresslevel=level) as zf:
            files = list(input_dir.rglob('*'))
            
            if show_progress:
                for file_path in tqdm(files, desc='Compressing', unit='files'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(input_dir)
                        zf.write(file_path, arcname)
            else:
                for file_path in files:
                    if file_path.is_file():
                        arcname = file_path.relative_to(input_dir)
                        zf.write(file_path, arcname)
    
    def _compress_dir_tar(
        self, input_dir: Path, output_path: Path,
        mode: str, show_progress: bool
    ) -> None:
        """Compress directory as TAR archive."""
        with tarfile.open(output_path, mode) as tf:
            if show_progress:
                files = list(input_dir.rglob('*'))
                for file_path in tqdm(files, desc='Compressing', unit='files'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(input_dir)
                        tf.add(file_path, arcname)
            else:
                tf.add(input_dir, input_dir.name)
    
    def decompress_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        show_progress: bool = True
    ) -> str:
        """
        Decompress a file or archive.
        
        Args:
            input_path: Path to compressed file
            output_path: Output path for decompressed content
            show_progress: Show progress bar
            
        Returns:
            Path to decompressed file/directory
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Detect compression method
        suffix = ''.join(input_path.suffixes)
        method = self._detect_compression_method(suffix)
        
        if output_path is None:
            # Remove compression suffix
            output_path = input_path
            for _ in range(len(input_path.suffixes)):
                output_path = output_path.with_suffix('')
        else:
            output_path = Path(output_path)
        
        file_size = input_path.stat().st_size
        
        logger.info(f"Decompressing: {input_path} -> {output_path}")
        logger.info(f"Detected method: {method}")
        
        try:
            if method == 'gzip':
                self._decompress_gzip(input_path, output_path, show_progress)
            elif method == 'bz2':
                self._decompress_bz2(input_path, output_path, show_progress)
            elif method == 'zip':
                self._decompress_zip(input_path, output_path, show_progress)
            elif method in ['tar', 'tar.gz', 'tar.bz2']:
                self._decompress_tar(input_path, output_path, show_progress)
            else:
                raise ValueError(f"Unable to detect compression method for: {input_path}")
            
            logger.info(f"Decompression complete: {output_path}")
            
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Decompression failed: {str(e)}")
            if output_path.exists() and output_path != input_path:
                if output_path.is_file():
                    output_path.unlink()
                elif output_path.is_dir():
                    shutil.rmtree(output_path)
            raise
    
    def _detect_compression_method(self, suffix: str) -> str:
        """Detect compression method from file suffix."""
        suffix = suffix.lower()
        
        if suffix.endswith('.tar.gz'):
            return 'tar.gz'
        elif suffix.endswith('.tar.bz2'):
            return 'tar.bz2'
        elif suffix.endswith('.tar'):
            return 'tar'
        elif suffix.endswith('.gz'):
            return 'gzip'
        elif suffix.endswith('.bz2'):
            return 'bz2'
        elif suffix.endswith('.zip'):
            return 'zip'
        else:
            return 'unknown'
    
    def _decompress_gzip(
        self, input_path: Path, output_path: Path,
        show_progress: bool
    ) -> None:
        """Decompress gzip file."""
        with gzip.open(input_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                if show_progress:
                    file_size = input_path.stat().st_size
                    with tqdm(total=file_size, unit='B', unit_scale=True, desc='Decompressing') as pbar:
                        while True:
                            chunk = f_in.read(self.chunk_size)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            pbar.update(len(chunk))
                else:
                    shutil.copyfileobj(f_in, f_out)
    
    def _decompress_bz2(
        self, input_path: Path, output_path: Path,
        show_progress: bool
    ) -> None:
        """Decompress bz2 file."""
        with bz2.open(input_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                if show_progress:
                    file_size = input_path.stat().st_size
                    with tqdm(total=file_size, unit='B', unit_scale=True, desc='Decompressing') as pbar:
                        while True:
                            chunk = f_in.read(self.chunk_size)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            pbar.update(len(chunk))
                else:
                    shutil.copyfileobj(f_in, f_out)
    
    def _decompress_zip(
        self, input_path: Path, output_path: Path,
        show_progress: bool
    ) -> None:
        """Decompress zip archive."""
        with zipfile.ZipFile(input_path, 'r') as zf:
            members = zf.namelist()
            
            if show_progress:
                for member in tqdm(members, desc='Decompressing', unit='files'):
                    zf.extract(member, output_path)
            else:
                zf.extractall(output_path)
    
    def _decompress_tar(
        self, input_path: Path, output_path: Path,
        show_progress: bool
    ) -> None:
        """Decompress tar archive."""
        with tarfile.open(input_path, 'r:*') as tf:
            if show_progress:
                members = tf.getmembers()
                for member in tqdm(members, desc='Decompressing', unit='files'):
                    tf.extract(member, output_path)
            else:
                tf.extractall(output_path)
    
    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    
    def verify_integrity(self, original: str, decompressed: str) -> bool:
        """
        Verify file integrity by comparing checksums.
        
        Args:
            original: Original file path
            decompressed: Decompressed file path
            
        Returns:
            True if files match
        """
        original_hash = self._compute_checksum(original)
        decompressed_hash = self._compute_checksum(decompressed)
        
        return original_hash == decompressed_hash
    
    @staticmethod
    def _compute_checksum(filepath: str, algorithm: str = 'sha256') -> str:
        """
        Compute file checksum.
        
        Args:
            filepath: File path
            algorithm: Hash algorithm
            
        Returns:
            Hexadecimal checksum
        """
        hash_func = hashlib.new(algorithm)
        
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='File Compression Utility - Compress and decompress files and directories',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compress a file with gzip
  python compressor.py compress -i file.txt -m gzip
  
  # Compress a directory to zip
  python compressor.py compress-dir -i /path/to/dir -o archive.zip
  
  # Decompress a file
  python compressor.py decompress -i file.txt.gz
  
  # Decompress a zip archive
  python compressor.py decompress -i archive.zip -o output_dir
  
Supported formats: gzip, bz2, zip, tar, tar.gz, tar.bz2
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Compress file command
    compress_parser = subparsers.add_parser('compress', help='Compress a single file')
    compress_parser.add_argument('-i', '--input', required=True, help='Input file path')
    compress_parser.add_argument('-o', '--output', help='Output file path')
    compress_parser.add_argument(
        '-m', '--method',
        choices=['gzip', 'bz2', 'zip'],
        default='gzip',
        help='Compression method'
    )
    compress_parser.add_argument(
        '-l', '--level',
        type=int,
        choices=range(1, 10),
        default=6,
        help='Compression level (1-9)'
    )
    compress_parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    
    # Compress directory command
    compress_dir_parser = subparsers.add_parser('compress-dir', help='Compress a directory')
    compress_dir_parser.add_argument('-i', '--input', required=True, help='Input directory path')
    compress_dir_parser.add_argument('-o', '--output', required=True, help='Output archive path')
    compress_dir_parser.add_argument(
        '-m', '--method',
        choices=['zip', 'tar', 'tar.gz', 'tar.bz2'],
        default='zip',
        help='Compression method'
    )
    compress_dir_parser.add_argument(
        '-l', '--level',
        type=int,
        choices=range(1, 10),
        default=6,
        help='Compression level (1-9)'
    )
    compress_dir_parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    
    # Decompress command
    decompress_parser = subparsers.add_parser('decompress', help='Decompress a file or archive')
    decompress_parser.add_argument('-i', '--input', required=True, help='Input compressed file')
    decompress_parser.add_argument('-o', '--output', help='Output path')
    decompress_parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify file integrity')
    verify_parser.add_argument('original', help='Original file path')
    verify_parser.add_argument('decompressed', help='Decompressed file path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    compressor = FileCompressor()
    
    try:
        if args.command == 'compress':
            output = compressor.compress_file(
                input_path=args.input,
                output_path=args.output,
                method=args.method,
                compression_level=args.level,
                show_progress=not args.no_progress
            )
            print(f"✅ File compressed successfully: {output}")
            
        elif args.command == 'compress-dir':
            output = compressor.compress_directory(
                input_dir=args.input,
                output_path=args.output,
                method=args.method,
                compression_level=args.level,
                show_progress=not args.no_progress
            )
            print(f"✅ Directory compressed successfully: {output}")
            
        elif args.command == 'decompress':
            output = compressor.decompress_file(
                input_path=args.input,
                output_path=args.output,
                show_progress=not args.no_progress
            )
            print(f"✅ File decompressed successfully: {output}")
            
        elif args.command == 'verify':
            if compressor.verify_integrity(args.original, args.decompressed):
                print("✅ Files match - integrity verified")
            else:
                print("❌ Files do not match - integrity check failed")
                
    except Exception as e:
        logger.error(f"Operation failed: {str(e)}")
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
