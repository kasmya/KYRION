"""
Image Processor Module

Provides functionality for image resizing, format conversion, filter application,
and batch processing of image folders. Uses Pillow (PIL) for image operations.

Security considerations:
- Validates file paths to prevent directory traversal
- Restricts operations to allowed image formats
- Handles errors explicitly without exposing sensitive information
- Uses safe file operations with proper cleanup
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Tuple, List, Optional, Union, Literal
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError


# Supported formats and their standard extensions
SUPPORTED_FORMATS = {
    "JPEG": [".jpg", ".jpeg"],
    "PNG": [".png"],
    "WEBP": [".webp"]
}

# Supported filters
SUPPORTED_FILTERS = {
    "blur": ImageFilter.BLUR,
    "sharpen": ImageFilter.SHARPEN,
    "edge_detection": ImageFilter.FIND_EDGES,
    "emboss": ImageFilter.EMBOSS,
    "contour": ImageFilter.CONTOUR,
    "smooth": ImageFilter.SMOOTH,
    "detail": ImageFilter.DETAIL
}

# Maximum allowed image dimensions (security: prevent decompression bombs)
MAX_DIMENSION = 10000


class ImageProcessorError(Exception):
    """Base exception for image processor errors."""
    pass


class InvalidPathError(ImageProcessorError):
    """Raised when a file path is invalid or unsafe."""
    pass


class UnsupportedFormatError(ImageProcessorError):
    """Raised when an image format is not supported."""
    pass


class InvalidImageError(ImageProcessorError):
    """Raised when an image file is corrupted or not a valid image."""
    pass


class ProcessingError(ImageProcessorError):
    """Raised when an image processing operation fails."""
    pass


def _validate_path(path: Union[str, Path], must_exist: bool = True) -> Path:
    """
    Validate and normalize a file path.

    Args:
        path: Path to validate
        must_exist: Whether the path must exist

    Returns:
        Normalized Path object

    Raises:
        InvalidPathError: If path is invalid or unsafe
    """
    try:
        path_obj = Path(path).resolve()
    except (OSError, ValueError) as e:
        raise InvalidPathError(f"Invalid path: {path}") from e

    # Prevent directory traversal
    if ".." in str(path_obj):
        raise InvalidPathError(f"Path contains directory traversal: {path}")

    if must_exist and not path_obj.exists():
        raise InvalidPathError(f"Path does not exist: {path}")

    return path_obj


def _validate_format(format_str: str) -> str:
    """
    Validate and normalize image format string.

    Args:
        format_str: Format string (e.g., 'JPEG', 'PNG', 'WEBP')

    Returns:
        Uppercase format string

    Raises:
        UnsupportedFormatError: If format is not supported
    """
    format_upper = format_str.upper()
    if format_upper not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported format: {format_str}. "
            f"Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
        )
    return format_upper


def _validate_size(size: Tuple[int, int]) -> Tuple[int, int]:
    """
    Validate image size tuple.

    Args:
        size: (width, height) tuple

    Returns:
        Validated size tuple

    Raises:
        ValueError: If size is invalid
    """
    if not isinstance(size, (tuple, list)) or len(size) != 2:
        raise ValueError("Size must be a tuple of (width, height)")

    width, height = size
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("Width and height must be integers")

    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be positive")

    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ValueError(f"Dimensions exceed maximum allowed ({MAX_DIMENSION}px)")

    return (width, height)


def _get_output_path(input_path: Path, output_dir: Optional[Path], 
                     suffix: str = "", new_extension: Optional[str] = None) -> Path:
    """
    Generate output path for processed image.

    Args:
        input_path: Original image path
        output_dir: Output directory (None for same directory)
        suffix: Suffix to add to filename
        new_extension: New file extension (with dot)

    Returns:
        Output Path object
    """
    if output_dir is None:
        output_dir = input_path.parent
    
    stem = input_path.stem
    ext = new_extension or input_path.suffix
    new_name = f"{stem}{suffix}{ext}"
    return output_dir / new_name


def _open_image_safely(path: Path) -> Image.Image:
    """
    Open image with security checks.

    Args:
        path: Path to image file

    Returns:
        PIL Image object

    Raises:
        InvalidImageError: If file is not a valid image
    """
    try:
        img = Image.open(path)
        # Force load to verify it's a valid image
        img.load()
        # Check for decompression bombs
        if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
            raise InvalidImageError(
                f"Image dimensions exceed maximum allowed ({MAX_DIMENSION}px)"
            )
        return img
    except UnidentifiedImageError as e:
        raise InvalidImageError(f"Cannot identify image file: {path}") from e
    except (OSError, ValueError) as e:
        raise InvalidImageError(f"Error opening image: {path}") from e


def resize_image(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    size: Tuple[int, int],
    keep_aspect_ratio: bool = True,
    resample: Image.Resampling = Image.Resampling.LANCZOS
) -> None:
    """
    Resize an image to specified dimensions.

    Args:
        input_path: Path to input image
        output_path: Path to save resized image
        size: Target (width, height) in pixels
        keep_aspect_ratio: If True, maintain aspect ratio (fit within size)
        resample: Resampling filter to use

    Raises:
        InvalidPathError: If paths are invalid
        InvalidImageError: If input is not a valid image
        ProcessingError: If resize operation fails
    """
    input_path = _validate_path(input_path)
    output_path = _validate_path(output_path, must_exist=False)
    size = _validate_size(size)

    try:
        img = _open_image_safely(input_path)
        
        if keep_aspect_ratio:
            img.thumbnail(size, resample)
        else:
            img = img.resize(size, resample)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)
        
    except ImageProcessorError:
        raise
    except Exception as e:
        raise ProcessingError(f"Failed to resize image: {e}") from e


def convert_image(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    format: str,
    quality: int = 85,
    optimize: bool = True
) -> None:
    """
    Convert image to a different format.

    Args:
        input_path: Path to input image
        output_path: Path to save converted image
        format: Target format ('JPEG', 'PNG', 'WEBP')
        quality: Quality for lossy formats (1-100)
        optimize: Whether to optimize file size

    Raises:
        InvalidPathError: If paths are invalid
        UnsupportedFormatError: If format is not supported
        InvalidImageError: If input is not a valid image
        ProcessingError: If conversion fails
    """
    input_path = _validate_path(input_path)
    output_path = _validate_path(output_path, must_exist=False)
    format = _validate_format(format)

    if not 1 <= quality <= 100:
        raise ValueError("Quality must be between 1 and 100")

    try:
        img = _open_image_safely(input_path)
        
        # Handle format-specific requirements
        save_kwargs = {"format": format, "optimize": optimize}
        
        if format == "JPEG":
            # Convert RGBA to RGB for JPEG
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            save_kwargs["quality"] = quality
        elif format == "WEBP":
            save_kwargs["quality"] = quality
            save_kwargs["method"] = 6  # Best compression
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, **save_kwargs)
        
    except ImageProcessorError:
        raise
    except Exception as e:
        raise ProcessingError(f"Failed to convert image: {e}") from e


def apply_filter(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    filter_type: str,
    **filter_args
) -> None:
    """
    Apply a filter to an image.

    Args:
        input_path: Path to input image
        output_path: Path to save filtered image
        filter_type: Filter name (blur, sharpen, edge_detection, emboss, contour, smooth, detail)
        **filter_args: Additional arguments for specific filters

    Raises:
        InvalidPathError: If paths are invalid
        ValueError: If filter_type is not supported
        InvalidImageError: If input is not a valid image
        ProcessingError: If filter application fails
    """
    input_path = _validate_path(input_path)
    output_path = _validate_path(output_path, must_exist=False)

    if filter_type not in SUPPORTED_FILTERS:
        raise ValueError(
            f"Unsupported filter: {filter_type}. "
            f"Supported filters: {', '.join(SUPPORTED_FILTERS.keys())}"
        )

    try:
        img = _open_image_safely(input_path)
        filter_obj = SUPPORTED_FILTERS[filter_type]
        
        # Apply filter with any additional arguments
        filtered_img = img.filter(filter_obj, **filter_args)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        filtered_img.save(output_path)
        
    except ImageProcessorError:
        raise
    except Exception as e:
        raise ProcessingError(f"Failed to apply filter: {e}") from e


def batch_process(
    folder_path: Union[str, Path],
    operation: Literal["resize", "convert", "filter"],
    output_dir: Optional[Union[str, Path]] = None,
    recursive: bool = False,
    **operation_kwargs
) -> List[Path]:
    """
    Batch process all supported images in a folder.

    Args:
        folder_path: Path to folder containing images
        operation: Operation to perform ('resize', 'convert', 'filter')
        output_dir: Output directory (None for same directory with suffix)
        recursive: Whether to process subdirectories
        **operation_kwargs: Arguments for the specific operation

    Returns:
        List of output file paths

    Raises:
        InvalidPathError: If folder path is invalid
        ValueError: If operation is not supported
        ProcessingError: If batch processing fails
    """
    folder_path = _validate_path(folder_path)
    
    if not folder_path.is_dir():
        raise InvalidPathError(f"Path is not a directory: {folder_path}")

    if output_dir is not None:
        output_dir = _validate_path(output_dir, must_exist=False)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Collect image files
    image_files = []
    pattern = "**/*" if recursive else "*"
    for ext_list in SUPPORTED_FORMATS.values():
        for ext in ext_list:
            image_files.extend(folder_path.glob(f"{pattern}{ext}"))
            image_files.extend(folder_path.glob(f"{pattern}{ext.upper()}"))

    if not image_files:
        return []

    # Map operation to function
    operations = {
        "resize": resize_image,
        "convert": convert_image,
        "filter": apply_filter
    }

    if operation not in operations:
        raise ValueError(f"Unsupported operation: {operation}")

    op_func = operations[operation]
    output_files = []
    errors = []

    for img_path in image_files:
        try:
            # Generate output path
            if operation == "convert":
                new_ext = f".{operation_kwargs.get('format', '').lower()}"
                suffix = "_converted"
            elif operation == "resize":
                new_ext = None
                suffix = "_resized"
            else:  # filter
                new_ext = None
                suffix = f"_{operation_kwargs.get('filter_type', 'filtered')}"

            out_path = _get_output_path(img_path, output_dir, suffix, new_ext)
            
            # Call operation function
            op_func(img_path, out_path, **operation_kwargs)
            output_files.append(out_path)
            
        except ImageProcessorError as e:
            errors.append(f"{img_path}: {e}")
        except Exception as e:
            errors.append(f"{img_path}: Unexpected error - {e}")

    if errors:
        error_msg = f"Batch processing completed with {len(errors)} errors:\n" + "\n".join(errors)
        if not output_files:
            raise ProcessingError(error_msg)
        else:
            # Print warnings but don't raise if some succeeded
            print(f"Warnings during batch processing:\n{error_msg}", file=sys.stderr)

    return output_files


def get_image_info(input_path: Union[str, Path]) -> dict:
    """
    Get basic information about an image file.

    Args:
        input_path: Path to image file

    Returns:
        Dictionary with image info (format, size, mode, etc.)

    Raises:
        InvalidPathError: If path is invalid
        InvalidImageError: If file is not a valid image
    """
    input_path = _validate_path(input_path)
    
    try:
        img = _open_image_safely(input_path)
        return {
            "path": str(input_path),
            "format": img.format,
            "size": img.size,
            "mode": img.mode,
            "width": img.width,
            "height": img.height
        }
    except ImageProcessorError:
        raise
    except Exception as e:
        raise InvalidImageError(f"Failed to get image info: {e}") from e


if __name__ == "__main__":
    # Example usage and simple CLI
    import argparse
    
    parser = argparse.ArgumentParser(description="Image Processor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Resize command
    resize_parser = subparsers.add_parser("resize", help="Resize an image")
    resize_parser.add_argument("input", help="Input image path")
    resize_parser.add_argument("output", help="Output image path")
    resize_parser.add_argument("--width", type=int, required=True, help="Target width")
    resize_parser.add_argument("--height", type=int, required=True, help="Target height")
    resize_parser.add_argument("--keep-aspect", action="store_true", default=True, help="Keep aspect ratio")
    
    # Convert command
    convert_parser = subparsers.add_parser("convert", help="Convert image format")
    convert_parser.add_argument("input", help="Input image path")
    convert_parser.add_argument("output", help="Output image path")
    convert_parser.add_argument("--format", choices=["JPEG", "PNG", "WEBP"], required=True, help="Target format")
    convert_parser.add_argument("--quality", type=int, default=85, help="Quality (1-100)")
    
    # Filter command
    filter_parser = subparsers.add_parser("filter", help="Apply filter to image")
    filter_parser.add_argument("input", help="Input image path")
    filter_parser.add_argument("output", help="Output image path")
    filter_parser.add_argument("--type", choices=list(SUPPORTED_FILTERS.keys()), required=True, help="Filter type")
    
    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Batch process images in folder")
    batch_parser.add_argument("folder