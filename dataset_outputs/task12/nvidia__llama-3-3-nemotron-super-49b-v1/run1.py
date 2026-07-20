import argparse
import os
from typing import Optional
import zipfile
import gzip
import shutil
import tarfile

def compress_zip(file_path: str, output_path: str) -> None:
    """
    Compress a single file or directory into a ZIP archive.

    Args:
    - file_path (str): Path to the file or directory to compress.
    - output_path (str): Path to the output ZIP file.

    Raises:
    - FileNotFoundError: If the input file/directory does not exist.
    - PermissionError: If there's no permission to read the input or write to the output.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input {file_path} does not exist.")
    
    try:
        with zipfile.ZipFile(output_path, 'w') as zip_f:
            if os.path.isfile(file_path):
                # Compress a single file
                zip_f.write(file_path, os.path.basename(file_path))
            else:
                # Compress a directory
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, start=os.path.dirname(file_path))
                        zip_f.write(file_path, rel_path)
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {file_path} or {output_path}") from e

def compress_gzip(file_path: str, output_path: str) -> None:
    """
    Compress a single file using GZIP.

    Args:
    - file_path (str): Path to the file to compress.
    - output_path (str): Path to the output GZIP file.

    Raises:
    - FileNotFoundError: If the input file does not exist.
    - PermissionError: If there's no permission to read the input or write to the output.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input {file_path} does not exist.")
    
    try:
        with open(file_path, 'rb') as f_in, gzip.open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {file_path} or {output_path}") from e

def compress_tar(file_path: str, output_path: str) -> None:
    """
    Compress a single file or directory into a TAR archive.

    Args:
    - file_path (str): Path to the file or directory to compress.
    - output_path (str): Path to the output TAR file.

    Raises:
    - FileNotFoundError: If the input file/directory does not exist.
    - PermissionError: If there's no permission to read the input or write to the output.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input {file_path} does not exist.")
    
    try:
        with tarfile.open(output_path, 'w') as tar:
            if os.path.isfile(file_path):
                tar.add(file_path, arcname=os.path.basename(file_path))
            else:
                tar.add(file_path)
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {file_path} or {output_path}") from e

def decompress_zip(file_path: str, output_dir: str) -> None:
    """
    Decompress a ZIP archive into a directory.

    Args:
    - file_path (str): Path to the ZIP file.
    - output_dir (str): Path to the output directory.

    Raises:
    - FileNotFoundError: If the ZIP file does not exist.
    - PermissionError: If there's no permission to read the input or write to the output directory.
    - zipfile.BadZipFile: If the ZIP file is corrupted or not a valid ZIP file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"ZIP file {file_path} does not exist.")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_f:
            zip_f.extractall(output_dir)
    except zipfile.BadZipFile as e:
        raise zipfile.BadZipFile(f"{file_path} is not a valid ZIP file") from e
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {file_path} or {output_dir}") from e

def decompress_gzip(file_path: str, output_path: str) -> None:
    """
    Decompress a GZIP file.

    Args:
    - file_path (str): Path to the GZIP file.
    - output_path (str): Path to the output file.

    Raises:
    - FileNotFoundError: If the GZIP file does not exist.
    - PermissionError: If there's no permission to read the input or write to the output.
    - OSError: If the GZIP file is corrupted or not a valid GZIP file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"GZIP file {file_path} does not exist.")
    
    try:
        with gzip.open(file_path, 'rb') as f_in, open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    except OSError as e:
        if e.errno == 22:  # Invalid argument, likely corrupted GZIP
            raise OSError(f"{file_path} is not a valid GZIP file") from e
        else:
            raise PermissionError(f"Permission denied for {file_path} or {output_path}") from e

def decompress_tar(file_path: str, output_dir: str) -> None:
    """
    Decompress a TAR archive into a directory.

    Args:
    - file_path (str): Path to the TAR file.
    - output_dir (str): Path to the output directory.

    Raises:
    - FileNotFoundError: If the TAR file does not exist.
    - PermissionError: If there's no permission to read the input or write to the output directory.
    - tarfile.TarError: If the TAR file is corrupted or not a valid TAR file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"TAR file {file_path} does not exist.")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    try:
        with tarfile.open(file_path, 'r') as tar:
            tar.extractall(output_dir)
    except tarfile.TarError as e:
        raise tarfile.TarError(f"{file_path} is not a valid TAR file") from e
    except PermissionError as e:
        raise PermissionError(f"Permission denied for {file_path} or {output_dir}") from e

def list_zip_contents(file_path: str) -> None:
    """
    List the contents of a ZIP archive.

    Args:
    - file_path (str): Path to the ZIP file.

    Raises:
    - FileNotFoundError: If the ZIP file does not exist.
    - zipfile.BadZipFile: If the ZIP file is corrupted or not a valid ZIP file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"ZIP file {file_path} does not exist.")
    
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_f:
            print(zip_f.namelist())
    except zipfile.BadZipFile as e:
        raise zipfile.BadZipFile(f"{file_path} is not a valid ZIP file") from e

def list_gzip_contents(file_path: str) -> None:
    """
    GZIP files contain a single file; this function informs the user and attempts to read the header.

    Args:
    - file_path (str): Path to the GZIP file.

    Raises:
    - FileNotFoundError: If the GZIP file does not exist.
    - OSError: If the GZIP file is corrupted or not a valid GZIP file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"GZIP file {file_path} does not exist.")
    
    try:
        with gzip.open(file_path, 'rb') as f:
            # GZIP contains a single file, so we just read the first part of the header
            # The filename can be embedded but is not always present or reliable for display
            print("GZIP files typically contain a single file. Filename might not be reliably embedded.")
            # Attempting to read past the header to check validity without extracting
            f.read(10)  # Read a bit more to ensure it's a valid GZIP
    except OSError as e:
        if e.errno == 22:  # Invalid argument, likely corrupted GZIP
            raise OSError(f"{file_path} is not a valid GZIP file") from e
        else:
            raise OSError(f"Error reading {file_path}: {e}") from e

def list_tar_contents(file_path: str) -> None:
    """
    List the contents of a TAR archive.

    Args:
    - file_path (str): Path to the TAR file.

    Raises:
    - FileNotFoundError: If the TAR file does not exist.
    - tarfile.TarError: If the TAR file is corrupted or not a valid TAR file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"TAR file {file_path} does not exist.")
    
    try:
        with tarfile.open(file_path, 'r') as tar:
            print(tar.getnames())
    except tarfile.TarError as e:
        raise tarfile.TarError(f"{file_path} is not a valid TAR file") from e

def main() -> None:
    parser = argparse.ArgumentParser(description="File Compression Utility")
    subparsers = parser.add_subparsers(dest="command",