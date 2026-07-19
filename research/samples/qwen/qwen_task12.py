"""CLI File Compression Utility with gzip, bz2, zip, and tqdm."""
import os, argparse, logging, zipfile, gzip, bz2, shutil
from typing import List
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)

def compress_file(input_path: str, output_path: str, method: str):
    """Compress a single file using specified method."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
        
    file_size = os.path.getsize(input_path)
    
    if method == 'gzip':
        with open(input_path, 'rb') as f_in, gzip.open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    elif method == 'bz2':
        with open(input_path, 'rb') as f_in, bz2.open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        raise ValueError(f"Unsupported method for single file: {method}")

def compress_directory(input_dir: str, output_zip: str):
    """Recursively compress a directory into a zip file with progress bar."""
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"Not a directory: {input_dir}")
        
    files_to_zip = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            files_to_zip.append(os.path.join(root, f))
            
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in tqdm(files_to_zip, desc="Compressing"):
            arcname = os.path.relpath(file, input_dir)
            zf.write(file, arcname)

def decompress_file(input_path: str, output_path: str, method: str):
    """Decompress a file."""
    if method == 'gzip':
        with gzip.open(input_path, 'rb') as f_in, open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    elif method == 'bz2':
        with bz2.open(input_path, 'rb') as f_in, open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    elif method == 'zip':
        with zipfile.ZipFile(input_path, 'r') as zf:
            zf.extractall(output_path)
    else:
        raise ValueError(f"Unsupported decompression method: {method}")

def main():
    parser = argparse.ArgumentParser(description="File Compression Utility")
    parser.add_argument("action", choices=["compress", "decompress"], help="Action to perform")
    parser.add_argument("input", help="Input file or directory")
    parser.add_argument("output", help="Output file or directory")
    parser.add_argument("-m", "--method", choices=["gzip", "bz2", "zip"], default="gzip", help="Compression method")
    
    args = parser.parse_args()
    
    try:
        if args.action == "compress":
            if os.path.isdir(args.input):
                if args.method != 'zip':
                    logging.warning("Directory compression requires 'zip' method. Switching to zip.")
                compress_directory(args.input, args.output)
            else:
                compress_file(args.input, args.output, args.method)
            logging.info(f"Compressed {args.input} to {args.output}")
        else:
            decompress_file(args.input, args.output, args.method)
            logging.info(f"Decompressed {args.input} to {args.output}")
    except Exception as e:
        logging.error(f"Operation failed: {e}")

if __name__ == "__main__":
    main()