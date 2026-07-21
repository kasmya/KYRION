"""
Image Processor Module

A comprehensive image processing utility that supports:
- Resizing images with various algorithms
- Format conversion between JPEG, PNG, and WebP
- Applying filters: blur, sharpen, edge detection
- Batch processing of image folders

Security features:
- Path validation to prevent directory traversal
- File size limits to prevent resource exhaustion
- Format validation to prevent malicious file processing
- Safe temporary file handling

Dependencies:
- Pillow (PIL): Industry-standard image processing library
"""

from __future__ import annotations

import os
import sys
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Literal, Optional, Sequence
from dataclasses import dataclass
from enum import Enum

try:
    from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
except ImportError as e:
    raise ImportError(
        "Pillow is required. Install with: pip install Pillow"
    ) from e


# =============================================================================
# Configuration & Constants
# =============================================================================

MAX_IMAGE_DIMENSION = 8192  # Maximum width/height in pixels
MAX_FILE_SIZE_MB = 100      # Maximum input file size in MB
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".jpe", ".jfif"}

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# =============================================================================
# Custom Exceptions
# =============================================================================

class ImageProcessorError(Exception):
    """Base exception for image processor errors."""
    pass


class ValidationError(ImageProcessorError):
    """Raised when input validation fails."""
    pass


class ProcessingError(ImageProcessorError):
    """Raised when image processing operation fails."""
    pass


class BatchProcessingError(ImageProcessorError):
    """Raised when batch processing encounters errors."""
    def __init__(self, message: str, failed_files: list[Path]) -> None:
        super().__init__(message)
        self.failed_files = failed_files


# =============================================================================
# Data Classes & Enums
# =============================================================================

class ResizeAlgorithm(Enum):
    """Supported resize algorithms."""
    LANCZOS = Image.LANCZOS
    BICUBIC = Image.BICUBIC
    BILINEAR = Image.BILINEAR
    NEAREST = Image.NEAREST
    BOX = Image.BOX
    HAMMING = Image.HAMMING


class FilterType(Enum):
    """Supported filter types."""
    BLUR = "blur"
    SHARPEN = "sharpen"
    EDGE_DETECT = "edge_detect"
    EMBOSS = "emboss"
    CONTOUR = "contour"
    SMOOTH = "smooth"
    DETAIL = "detail"


@dataclass(frozen=True)
class ProcessingResult:
    """Result of a single image processing operation."""
    input_path: Path
    output_path: Path
    original_size: tuple[int, int]
    new_size: tuple[int, int]
    original_format: str
    output_format: str
    file_size_bytes: int
    success: bool
    error_message: Optional[str] = None


@dataclass(frozen=True)
class BatchResult:
    """Result of batch processing operation."""
    total_files: int
    successful: int
    failed: int
    results: list[ProcessingResult]
    errors: list[tuple[Path, str]]


# =============================================================================
# Validation Functions
# =============================================================================

def validate_image_path(path: Path, must_exist: bool = True) -> None:
    """
    Validate an image file path for security and correctness.

    Args:
        path: Path to validate.
        must_exist: If True, path must exist. If False, parent must exist.

    Raises:
        ValidationError: If path is invalid or unsafe.
    """
    if not isinstance(path, Path):
        raise ValidationError(f"Path must be a Path object, got {type(path)}")

    # Resolve to absolute path to prevent directory traversal
    try:
        resolved = path.resolve(strict=must_exist)
    except FileNotFoundError:
        raise ValidationError(f"File not found: {path}")
    except OSError as e:
        raise ValidationError(f"Invalid path: {path} ({e})")

    # Check for directory traversal attempts
    if ".." in path.parts:
        raise ValidationError(f"Directory traversal not allowed: {path}")

    # Validate extension
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file extension: {path.suffix}. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # Check file size if exists
    if must_exist and resolved.is_file():
        size_mb = resolved.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise ValidationError(
                f"File too large: {size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB limit"
            )


def validate_dimensions(width: int, height: int) -> None:
    """
    Validate image dimensions.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.

    Raises:
        ValidationError: If dimensions are invalid.
    """
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValidationError("Dimensions must be integers")

    if width <= 0 or height <= 0:
        raise ValidationError("Dimensions must be positive")

    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValidationError(
            f"Dimensions exceed maximum: {width}x{height} > {MAX_IMAGE_DIMENSION}"
        )


def validate_format(format_name: str) -> str:
    """
    Validate and normalize output format.

    Args:
        format_name: Format name (e.g., 'JPEG', 'PNG', 'WEBP').

    Returns:
        Normalized format name.

    Raises:
        ValidationError: If format is not supported.
    """
    normalized = format_name.upper()
    if normalized not in SUPPORTED_FORMATS:
        raise ValidationError(
            f"Unsupported format: {format_name}. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )
    return normalized


def validate_quality(quality: int) -> None:
    """
    Validate JPEG/WebP quality parameter.

    Args:
        quality: Quality value (1-100).

    Raises:
        ValidationError: If quality is out of range.
    """
    if not isinstance(quality, int) or not (1 <= quality <= 100):
        raise ValidationError("Quality must be an integer between 1 and 100")


# =============================================================================
# Core Processing Functions
# =============================================================================

def load_image(path: Path) -> Image.Image:
    """
    Load and validate an image file.

    Args:
        path: Path to image file.

    Returns:
        PIL Image object.

    Raises:
        ValidationError: If file is invalid or not an image.
        ProcessingError: If image cannot be loaded.
    """
    validate_image_path(path, must_exist=True)

    try:
        with Image.open(path) as img:
            # Force load to verify it's a valid image
            img.load()
            # Return a copy to avoid file handle issues
            return img.copy()
    except UnidentifiedImageError as e:
        raise ValidationError(f"Not a valid image file: {path}") from e
    except OSError as e:
        raise ProcessingError(f"Failed to load image: {path} ({e})") from e


def save_image(
    image: Image.Image,
    output_path: Path,
    format_name: str,
    quality: int = 85,
    optimize: bool = True,
) -> None:
    """
    Save image to file with validation.

    Args:
        image: PIL Image to save.
        output_path: Destination path.
        format_name: Output format (JPEG, PNG, WEBP).
        quality: Quality for lossy formats (1-100).
        optimize: Whether to optimize file size.

    Raises:
        ValidationError: If parameters are invalid.
        ProcessingError: If save operation fails.
    """
    validate_image_path(output_path, must_exist=False)
    format_name = validate_format(format_name)
    validate_quality(quality)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare save arguments
    save_kwargs: dict = {"format": format_name, "optimize": optimize}

    if format_name in ("JPEG", "WEBP"):
        save_kwargs["quality"] = quality
        if format_name == "JPEG":
            # Convert RGBA to RGB for JPEG
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
                image = background
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

    try:
        # Use atomic write via temporary file
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
            image.save(temp_path, **save_kwargs)

        # Atomic replace
        temp_path.replace(output_path)
        logger.debug("Saved image to %s", output_path)

    except OSError as e:
        # Clean up temp file on failure
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise ProcessingError(f"Failed to save image: {output_path} ({e})") from e


def resize_image(
    image: Image.Image,
    width: int,
    height: int,
    algorithm: ResizeAlgorithm = ResizeAlgorithm.LANCZOS,
    maintain_aspect: bool = True,
) -> Image.Image:
    """
    Resize an image.

    Args:
        image: Source image.
        width: Target width.
        height: Target height.
        algorithm: Resampling algorithm.
        maintain_aspect: If True, maintain aspect ratio (fit within bounds).

    Returns:
        Resized image.

    Raises:
        ValidationError: If dimensions are invalid.
        ProcessingError: If resize operation fails.
    """
    validate_dimensions(width, height)

    try:
        if maintain_aspect:
            # Calculate aspect-preserving dimensions
            img_ratio = image.width / image.height
            target_ratio = width / height

            if img_ratio > target_ratio:
                # Width is limiting factor
                new_width = width
                new_height = int(width / img_ratio)
            else:
                # Height is limiting factor
                new_height = height
                new_width = int(height * img_ratio)

            validate_dimensions(new_width, new_height)
            return image.resize((new_width, new_height), algorithm.value)
        else:
            return image.resize((width, height), algorithm.value)

    except OSError as e:
        raise ProcessingError(f"Resize failed: {e}") from e


def apply_filter(image: Image.Image, filter_type: FilterType) -> Image.Image:
    """
    Apply a filter to an image.

    Args:
        image: Source image.
        filter_type: Type of filter to apply.

    Returns:
        Filtered image.

    Raises:
        ProcessingError: If filter application fails.
    """
    try:
        filter_map = {
            FilterType.BLUR: ImageFilter.BLUR,
            FilterType.SHARPEN: ImageFilter.SHARPEN,
            FilterType.EDGE_DETECT: ImageFilter.FIND_EDGES,
            FilterType.EMBOSS: ImageFilter.EMBOSS,
            FilterType.CONTOUR: ImageFilter.CONTOUR,
            FilterType.SMOOTH: ImageFilter.SMOOTH,
            FilterType.DETAIL: ImageFilter.DETAIL,
        }

        pil_filter = filter_map.get(filter_type)
        if pil_filter is None:
            raise ValidationError(f"Unknown filter type: {filter_type}")

        return image.filter(pil_filter)

    except OSError as e:
        raise ProcessingError(f"Filter application failed: {e}") from e


def convert_format(
    image: Image.Image,
    target_format: str,
    quality: int = 85,
) -> Image.Image:
    """
    Convert image to target format (mode adjustment).

    Args:
        image: Source image.
        target_format: Target format (JPEG, PNG, WEBP).
        quality: Quality for lossy formats.

    Returns:
        Image converted to appropriate mode for target format.

    Raises:
        ValidationError: If format is unsupported.
    """
    target_format = validate_format(target_format)

    if target_format == "JPEG":
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            if image.mode in ("RGBA", "LA"):
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image)
            return background
        elif image.mode not in ("RGB", "L", "CMYK"):
            return image.convert("RGB")

    elif target_format == "PNG":
        # PNG supports all modes, but ensure compatibility
        if image.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
            return image.convert("RGBA")

    elif target_format == "WEBP":
        # WebP supports RGB, RGBA
        if image.mode not in ("RGB", "RGBA"):
            return image.convert("RGBA" if "A" in image.mode else "RGB")

    return image


# =============================================================================
# High-Level Processing Functions
# =============================================================================

def process_single_image(
    input_path: Path,
    output_path: Path,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    resize_algorithm: ResizeAlgorithm = ResizeAlgorithm.LANCZOS,
    maintain_aspect: bool = True,
    output_format: Optional[str] = None,
    quality: int = 85,
    filters: Optional[Sequence[FilterType]] = None,
) -> ProcessingResult:
    """
    Process a single image with optional resize, format conversion, and filters.

    Args:
        input_path: Path to input image.
        output_path: Path for output image.
        width: Target width (optional).
        height: Target height (optional).
        resize_algorithm: Algorithm for resizing.
        maintain_aspect: Maintain aspect ratio when resizing.
        output_format: Output format (JPEG, PNG, WEBP). Defaults to input format.
        quality: Output quality for lossy formats (1-100).
        filters: Sequence of filters to apply.

    Returns:
        ProcessingResult with operation details.

    Raises:
        ValidationError: If parameters are invalid.
        ProcessingError: If processing fails.
    """
    original_path = input_path
    original_size = (0, 0)
    original_format = ""

    try:
        # Load image
        image = load_image(input_path)
        original_size = image.size
        original_format = image.format or "UNKNOWN"

        # Apply filters first
        if filters:
            for filter_type in filters:
                image = apply_filter(image, filter_type)

        # Resize if requested
        if width is not None or height is not None:
            target_width = width or image.width
            target_height = height or image.height
            image = resize_image(
                image, target_width, target_height,
                resize_algorithm, maintain_aspect
            )

        # Determine output format
        if output_format is None:
            output_format = original_format if original_format in SUPPORTED_FORMATS else "PNG"

        # Convert format if needed
        image = convert_format(image, output_format, quality)

        # Save result
        save_image(image, output_path, output_format, quality)

        return ProcessingResult(
            input_path=original_path,
            output_path=output_path,
            original_size=original_size,
            new_size=image.size,
            original_format=original_format,
            output_format=output_format,
            file_size_bytes=output_path.stat().st_size,
            success=True,
        )

    except (ValidationError, ProcessingError) as e:
        logger.error("Processing failed for %s: %s", input_path, e)
        return ProcessingResult(
            input_path=original_path,
            output_path=output_path,
            original_size=original_size,
            new_size=(0, 0),
            original_format=original_format,
            output_format=output_format or "UNKNOWN",
            file_size_bytes=0,
            success=False,
            error_message=str(e),
        )


def process_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    width: Optional[int] = None,