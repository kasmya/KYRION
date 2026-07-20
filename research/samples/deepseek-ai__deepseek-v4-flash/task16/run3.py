import io
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union, Dict
from PIL import Image, ImageFilter, UnidentifiedImageError

class ImageProcessor:
    """
    A safe and flexible image processor supporting resize, format conversion,
    filtering (blur, sharpen, edge detection), and batch processing.

    Validates file paths, extensions, and performs basic security checks.
    Uses Pillow (PIL) for all image operations.
    """

    # Whitelist of allowed output formats (lowercase)
    ALLOWED_FORMATS: Dict[str, str] = {
        "jpeg": "JPEG",
        "jpg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
    }

    # Map filter names to PIL ImageFilter classes
    FILTERS: Dict[str, ImageFilter.Filter] = {
        "blur": ImageFilter.BLUR,
        "sharpen": ImageFilter.SHARPEN,
        "edge_enhance": ImageFilter.EDGE_ENHANCE,
        "edge_detect": ImageFilter.FIND_EDGES,
    }

    def __init__(self, max_image_size_mb: float = 50.0):
        """
        Initialize the ImageProcessor.

        Args:
            max_image_size_mb: Maximum allowed input image size in MB.
                               Images larger than this will raise an error.
        """
        self.max_image_size_bytes = int(max_image_size_mb * 1024 * 1024)

    def _validate_input_file(self, input_path: Union[str, Path]) -> Path:
        """
        Validate an input file path for existence, extension, and size.

        Args:
            input_path: Path to the input image.

        Returns:
            Path object for the validated file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the extension is not allowed or file too large.
            PermissionError: If the file cannot be read.
        """
        path = Path(input_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        if not path.is_file():
            raise ValueError(f"Input path is not a file: {path}")

        # Check file extension (case-insensitive)
        ext = path.suffix.lower().lstrip(".")
        if ext not in self.ALLOWED_FORMATS and ext not in ("jpg", "jpeg", "png", "webp"):
            raise ValueError(f"Unsupported file extension: {ext}. Allowed: {list(self.ALLOWED_FORMATS.keys())}")

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_image_size_bytes:
            raise ValueError(
                f"Input file too large: {file_size / (1024*1024):.2f} MB "
                f"(max {self.max_image_size_bytes / (1024*1024):.1f} MB)"
            )

        return path

    def _validate_output_path(self, output_path: Union[str, Path], overwrite: bool = False) -> Path:
        """
        Validate an output file path for directory existence and write permissions.

        Args:
            output_path: Desired output path.
            overwrite: If False, raises FileExistsError if file exists.

        Returns:
            Path object for the output file.

        Raises:
            FileExistsError: If the file already exists and overwrite is False.
            PermissionError: If the parent directory is not writable.
        """
        path = Path(output_path).resolve()
        parent = path.parent
        if not parent.exists():
            raise FileNotFoundError(f"Output directory does not exist: {parent}")
        if not os.access(parent, os.W_OK):
            raise PermissionError(f"No write permission for directory: {parent}")
        if path.exists() and not overwrite:
            raise FileExistsError(f"Output file already exists and overwrite is False: {path}")
        return path

    def _load_image(self, input_path: Path) -> Image.Image:
        """
        Load an image from a validated path.

        Args:
            input_path: Validated Path to image file.

        Returns:
            PIL Image object.

        Raises:
            UnidentifiedImageError: If the image cannot be parsed.
            IOError: Other I/O errors.
        """
        try:
            img = Image.open(input_path)
            img.load()  # Defer decoding failure here
            return img
        except UnidentifiedImageError:
            raise UnidentifiedImageError(f"Cannot identify image file: {input_path}")
        except Exception as e:
            raise IOError(f"Error reading image {input_path}: {e}")

    def resize(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        size: Tuple[int, int],
        method: Image.Resampling = Image.Resampling.LANCZOS,
        overwrite: bool = False,
    ) -> None:
        """
        Resize an image to the given dimensions.

        Args:
            input_path: Path to input image.
            output_path: Path to save resized image.
            size: (width, height) tuple.
            method: Resampling filter (default LANCZOS).
            overwrite: If False, do not overwrite existing output file.

        Raises:
            Various exceptions from validation and image processing.
        """
        in_path = self._validate_input_file(input_path)
        out_path = self._validate_output_path(output_path, overwrite)

        img = self._load_image(in_path)
        try:
            resized = img.resize(size, method)
            # Save with format derived from output extension
            ext = out_path.suffix.lower().lstrip(".")
            fmt = self.ALLOWED_FORMATS.get(ext)
            if not fmt:
                raise ValueError(f"Unsupported output extension: .{ext}")
            resized.save(out_path, format=fmt)
        except Exception as e:
            raise RuntimeError(f"Resize failed: {e}")

    def convert(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        output_format: Optional[str] = None,
        overwrite: bool = False,
    ) -> None:
        """
        Convert an image to a different format.

        Args:
            input_path: Path to input image.
            output_path: Path to save converted image.
            output_format: Explicit format string (e.g., "PNG"). If None, inferred
                           from output_path extension.
            overwrite: If False, do not overwrite existing output file.

        Raises:
            ValueError: If output_format is invalid or cannot be inferred.
            Other I/O and image processing errors.
        """
        in_path = self._validate_input_file(input_path)
        out_path = self._validate_output_path(output_path, overwrite)

        # Determine format
        if output_format:
            fmt = output_format.upper()
            if fmt not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(f"Unsupported output format: {output_format}. Use JPEG, PNG, or WEBP.")
        else:
            ext = out_path.suffix.lower().lstrip(".")
            fmt = self.ALLOWED_FORMATS.get(ext)
            if not fmt:
                raise ValueError(
                    f"Cannot infer format from extension .{ext}. "
                    f"Please specify output_format."
                )

        img = self._load_image(in_path)

        # Handle transparency for JPEG (convert to RGB)
        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        try:
            img.save(out_path, format=fmt)
        except Exception as e:
            raise RuntimeError(f"Convert failed: {e}")

    def apply_filter(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        filter_name: str,
        overwrite: bool = False,
    ) -> None:
        """
        Apply a named filter to an image.

        Filters: 'blur', 'sharpen', 'edge_enhance', 'edge_detect'.

        Args:
            input_path: Path to input image.
            output_path: Path to save filtered image.
            filter_name: One of the supported filter names.
            overwrite: If False, do not overwrite existing output file.

        Raises:
            ValueError: If filter_name is not recognized.
            Other I/O and image processing errors.
        """
        in_path = self._validate_input_file(input_path)
        out_path = self._validate_output_path(output_path, overwrite)

        filter_obj = self.FILTERS.get(filter_name.lower())
        if filter_obj is None:
            raise ValueError(
                f"Unknown filter: '{filter_name}'. "
                f"Supported: {list(self.FILTERS.keys())}"
            )

        img = self._load_image(in_path)
        try:
            filtered = img.filter(filter_obj)
            ext = out_path.suffix.lower().lstrip(".")
            fmt = self.ALLOWED_FORMATS.get(ext)
            if not fmt:
                raise ValueError(f"Unsupported output extension: .{ext}")
            filtered.save(out_path, format=fmt)
        except Exception as e:
            raise RuntimeError(f"Filter '{filter_name}' failed: {e}")

    def batch_process(
        self,
        input_files: List[Union[str, Path]],
        output_dir: Union[str, Path],
        operations: List[Dict],
        overwrite: bool = False,
    ) -> List[str]:
        """
        Process a batch of images with a sequence of operations.

        Each operation is a dict with keys:
          - 'type': 'resize', 'convert', or 'filter'
          - other args matching the respective method (e.g., 'size', 'output_format', 'filter_name').
          - 'output_suffix' (optional, default "_processed"): appended to original filename.

        Example operation list:
            [
                {"type": "resize", "size": (800, 600)},
                {"type": "filter", "filter_name": "sharpen"},
                {"type": "convert", "output_format": "PNG"}
            ]

        Args:
            input_files: List of paths to input images.
            output_dir: Directory to save all processed images.
            operations: List of operation dicts to apply sequentially.
            overwrite: If False, skip files where output already exists.

        Returns:
            List of output file paths (strings) that were successfully created.

        Raises:
            FileNotFoundError, PermissionError, ValueError for invalid inputs.
            RuntimeError if an operation fails for a particular image.
        """
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        successful = []

        for inp in input_files:
            in_path = self._validate_input_file(inp)
            base_name = in_path.stem
            suffix = "_processed"

            # Determine final output extension: start from original, may be changed by convert op
            ext = in_path.suffix.lower()

            # Process image sequentially
            current_image = self._load_image(in_path)

            try:
                for op in operations:
                    op_type = op.get("type")
                    if op_type == "resize":
                        size = op.get("size")
                        if not size or not isinstance(size, tuple) or len(size) != 2:
                            raise ValueError("Resize operation requires a 'size' tuple (width, height)")
                        method = op.get("method", Image.Resampling.LANCZOS)
                        current_image = current_image.resize(size, method)
                        # Size change doesn't affect format

                    elif op_type == "convert":
                        out_fmt = op.get("output_format")
                        if out_fmt:
                            out_fmt = out_fmt.upper()
                            # Convert format for saving later
                            # We'll use format mapping
                            fmt_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
                            if out_fmt in fmt_map:
                                ext = fmt_map[out_fmt]
                            else:
                                raise ValueError(f"Unsupported format: {out_fmt}")
                        else:
                            # No explicit format, keep current extension
                            pass
                        # Optionally convert image mode for JPEG
                        if ext.lower() in (".jpg", ".jpeg") and current_image.mode in ("RGBA", "LA", "P"):
                            current_image = current_image.convert("RGB")

                    elif op_type == "filter":
                        filter_name = op.get("filter_name")
                        if not filter_name:
                            raise ValueError("Filter operation requires 'filter_name'")
                        filter_obj = self.FILTERS.get(filter_name.lower())
                        if filter_obj is None:
                            raise ValueError(f"Unknown filter: {filter_name}")
                        current_image = current_image.filter(filter_obj)

                    else:
                        raise ValueError(f"Unknown operation type: {op_type}")

                # Determine output filename
                output_filename = f"{base_name}{suffix}{ext}"
                out_path = out_dir / output_filename
                # Validate output (check directory, overwrite)
                self._validate_output_path(out_path, overwrite)

                # Save
                fmt_to_save = self.ALLOWED_FORMATS.get(ext.lstrip(".").lower())
                if not fmt_to_save:
                    # Fallback to PNG (should not happen)
                    raise ValueError(f"Cannot determine format for extension {ext}")

                current_image.save(out_path, format=fmt_to_save)
                successful.append(str(out_path))

            except Exception as e:
                # Log error and continue with next image, or re-raise?
                # Here we catch and print, then continue batch.
                # For strict error handling, we could re-raise, but batch usually continues.
                print(f"Error processing {in_path}: {e}", file=sys.stderr)
                continue

        return successful


def main():
    """
    Command-line interface for ImageProcessor.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Image Processor - resize, convert, filter, batch")
    parser.add_argument("input", nargs="+", help="Input image file(s) or directory (for batch)")
    parser.add_argument("--output-dir", "-o", default=".", help="Output directory (default: current dir)")
    parser.add_argument("--resize", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), help="Resize dimensions")
    parser.add_argument("--convert", choices=["jpeg", "png", "webp"], help="Convert to format")
    parser.add_argument("--filter", choices=["blur", "sharpen", "edge_enhance", "edge_detect"], help="Apply filter")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")

    args = parser.parse_args()

    # Gather input files: if directory, list images with allowed extensions
    input_files = []
    for item in args.input:
        p = Path(item)
        if p.is_dir():
            # List files in directory with image extensions
            for f in sorted(p.iterdir()):
                if f.suffix.lower().lstrip(".") in ImageProcessor.ALLOWED_FORMATS:
                    input_files.append(str(f))
        else:
            input_files.append(item)

    if not input_files:
        print("No valid input images found.", file=sys.stderr)
        sys.exit(1)

    processor = ImageProcessor()

    # Build operation list
    operations = []
    if args.resize:
        operations.append({"type": "resize", "size": tuple(args.resize)})
    if args.convert:
        operations.append({"type": "convert", "output_format": args.convert})
    if args.filter:
        operations.append({"type": "filter", "filter_name": args.filter})

    if not operations:
        # If no operations specified, just copy? For safety, show usage.
        print("No operations specified. Use --resize, --convert, or --filter.")
        sys.exit(1)

    # Run batch
    results = processor.batch_process(input_files, args.output_dir, operations, overwrite=args.overwrite)
    print(f"Processed {len(results)} image(s).")
    for r in results:
        print(f"  - {r}")


if __name__ == "__main__":
    main()