"""
Image Processor Module

A comprehensive image processing utility for resizing, format conversion,
filter application, and batch processing of images.

Supports JPEG, PNG, and WebP formats with various image filters including
blur, sharpen, and edge detection.

Example:
    >>> from image_processor import ImageProcessor
    >>> processor = ImageProcessor()
    >>> processor.resize("input.jpg", "output.jpg", (800, 600))
    >>> processor.convert_format("input.png", "output.webp")
    >>> processor.apply_filter("input.jpg", "output.jpg", "blur")
    >>> processor.batch_process("/path/to/images", "/path/to/output", {"resize": (1920, 1080)})
"""

import os
import sys
import logging
import argparse
import traceback
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List, Union, Literal
from dataclasses import dataclass
from enum import Enum

try:
    from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
except ImportError as e:
    raise ImportError(
        "Pillow library is required. Install it with: pip install Pillow"
    ) from e


# Configure module logger
logger = logging.getLogger(__name__)


class ImageFormat(Enum):
    """Supported image formats."""
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


class FilterType(Enum):
    """Supported filter types."""
    BLUR = "blur"
    SHARPEN = "sharpen"
    EDGE_DETECTION = "edge_detection"
    GAUSSIAN_BLUR = "gaussian_blur"
    BOX_BLUR = "box_blur"
    UNSHARP_MASK = "unsharp_mask"
    FIND_EDGES = "find_edges"
    CONTOUR = "contour"
    EMBOSS = "emboss"
    SMOOTH = "smooth"
    SMOOTH_MORE = "smooth_more"
    DETAIL = "detail"
    EDGE_ENHANCE = "edge_enhance"
    EDGE_ENHANCE_MORE = "edge_enhance_more"


@dataclass
class ProcessingOptions:
    """Options for image processing operations."""
    resize: Optional[Tuple[int, int]] = None
    format: Optional[ImageFormat] = None
    quality: int = 85
    optimize: bool = True
    filter_type: Optional[FilterType] = None
    filter_params: Optional[Dict[str, Any]] = None
    maintain_aspect_ratio: bool = True
    background_color: Tuple[int, int, int] = (255, 255, 255)


class ImageProcessorError(Exception):
    """Base exception for image processor errors."""
    pass


class InvalidImageError(ImageProcessorError):
    """Raised when an image file is invalid or corrupted."""
    pass


class UnsupportedFormatError(ImageProcessorError):
    """Raised when an image format is not supported."""
    pass


class ProcessingError(ImageProcessorError):
    """Raised when an image processing operation fails."""
    pass


class ValidationError(ImageProcessorError):
    """Raised when input validation fails."""
    pass


def validate_file_path(path: Union[str, Path], must_exist: bool = True) -> Path:
    """
    Validate and resolve a file path.

    Args:
        path: The file path to validate.
        must_exist: Whether the file must exist.

    Returns:
        Resolved Path object.

    Raises:
        ValidationError: If path is invalid or doesn't exist when required.
    """
    try:
        resolved_path = Path(path).resolve()
    except (OSError, ValueError) as e:
        raise ValidationError(f"Invalid path '{path}': {e}") from e

    if must_exist and not resolved_path.exists():
        raise ValidationError(f"File not found: {resolved_path}")

    if must_exist and not resolved_path.is_file():
        raise ValidationError(f"Path is not a file: {resolved_path}")

    return resolved_path


def validate_output_path(path: Union[str, Path], overwrite: bool = False) -> Path:
    """
    Validate an output file path.

    Args:
        path: The output file path.
        overwrite: Whether to allow overwriting existing files.

    Returns:
        Resolved Path object.

    Raises:
        ValidationError: If path is invalid or file exists and overwrite is False.
    """
    try:
        resolved_path = Path(path).resolve()
    except (OSError, ValueError) as e:
        raise ValidationError(f"Invalid output path '{path}': {e}") from e

    if resolved_path.exists() and not overwrite:
        raise ValidationError(f"Output file already exists: {resolved_path}. Use overwrite=True to replace.")

    # Ensure parent directory exists
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    return resolved_path


def validate_dimensions(width: int, height: int) -> Tuple[int, int]:
    """
    Validate image dimensions.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        Validated (width, height) tuple.

    Raises:
        ValidationError: If dimensions are invalid.
    """
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValidationError("Dimensions must be integers")

    if width <= 0 or height <= 0:
        raise ValidationError("Dimensions must be positive integers")

    if width > 65535 or height > 65535:
        raise ValidationError("Dimensions exceed maximum allowed size (65535x65535)")

    return (width, height)


def validate_quality(quality: int) -> int:
    """
    Validate JPEG/WebP quality parameter.

    Args:
        quality: Quality value (1-100).

    Returns:
        Validated quality value.

    Raises:
        ValidationError: If quality is out of range.
    """
    if not isinstance(quality, int):
        raise ValidationError("Quality must be an integer")

    if quality < 1 or quality > 100:
        raise ValidationError("Quality must be between 1 and 100")

    return quality


def get_image_format_from_path(path: Path) -> ImageFormat:
    """
    Determine image format from file extension.

    Args:
        path: File path.

    Returns:
        ImageFormat enum value.

    Raises:
        UnsupportedFormatError: If format is not supported.
    """
    suffix = path.suffix.lower()
    format_map = {
        ".jpg": ImageFormat.JPEG,
        ".jpeg": ImageFormat.JPEG,
        ".png": ImageFormat.PNG,
        ".webp": ImageFormat.WEBP,
    }

    if suffix not in format_map:
        raise UnsupportedFormatError(
            f"Unsupported file format: {suffix}. Supported: {', '.join(format_map.keys())}"
        )

    return format_map[suffix]


def get_pil_format(image_format: ImageFormat) -> str:
    """
    Convert ImageFormat enum to PIL format string.

    Args:
        image_format: ImageFormat enum value.

    Returns:
        PIL format string.
    """
    return image_format.value


def safe_open_image(path: Path) -> Image.Image:
    """
    Safely open an image file with validation.

    Args:
        path: Path to image file.

    Returns:
        PIL Image object.

    Raises:
        InvalidImageError: If image cannot be opened or is corrupted.
        UnsupportedFormatError: If image format is not supported.
    """
    try:
        img = Image.open(path)
        # Force load to verify image integrity
        img.load()
        return img
    except UnidentifiedImageError as e:
        raise InvalidImageError(f"Cannot identify image file: {path}") from e
    except (OSError, IOError) as e:
        raise InvalidImageError(f"Error reading image file: {path}") from e
    except Exception as e:
        raise InvalidImageError(f"Unexpected error opening image: {path}") from e


def apply_resize(
    image: Image.Image,
    size: Tuple[int, int],
    maintain_aspect_ratio: bool = True,
    background_color: Tuple[int, int, int] = (255, 255, 255),
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    """
    Resize an image with optional aspect ratio preservation.

    Args:
        image: PIL Image object.
        size: Target (width, height) tuple.
        maintain_aspect_ratio: Whether to preserve aspect ratio.
        background_color: Background color for padding (RGB).
        resample: Resampling filter.

    Returns:
        Resized PIL Image object.
    """
    target_width, target_height = size

    if maintain_aspect_ratio:
        # Calculate scaling factor to fit within target dimensions
        img_ratio = image.width / image.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # Image is wider relative to target
            new_width = target_width
            new_height = int(target_width / img_ratio)
        else:
            # Image is taller relative to target
            new_height = target_height
            new_width = int(target_height * img_ratio)

        # Resize image
        resized = image.resize((new_width, new_height), resample=resample)

        # Create new image with target size and background color
        if image.mode in ("RGBA", "LA", "P"):
            # Handle transparency
            background = Image.new("RGBA", (target_width, target_height), background_color + (255,))
            if image.mode == "P":
                image = image.convert("RGBA")
            # Paste resized image centered
            x = (target_width - new_width) // 2
            y = (target_height - new_height) // 2
            background.paste(resized, (x, y), resized if resized.mode == "RGBA" else None)
            return background.convert(image.mode) if image.mode != "RGBA" else background
        else:
            background = Image.new("RGB", (target_width, target_height), background_color)
            x = (target_width - new_width) // 2
            y = (target_height - new_height) // 2
            background.paste(resized, (x, y))
            return background
    else:
        # Simple resize without aspect ratio preservation
        return image.resize((target_width, target_height), resample=resample)


def apply_filter(image: Image.Image, filter_type: FilterType, params: Optional[Dict[str, Any]] = None) -> Image.Image:
    """
    Apply a filter to an image.

    Args:
        image: PIL Image object.
        filter_type: Type of filter to apply.
        params: Optional filter parameters.

    Returns:
        Filtered PIL Image object.

    Raises:
        ProcessingError: If filter application fails.
    """
    if params is None:
        params = {}

    try:
        if filter_type == FilterType.BLUR:
            radius = params.get("radius", 2)
            return image.filter(ImageFilter.BoxBlur(radius))

        elif filter_type == FilterType.GAUSSIAN_BLUR:
            radius = params.get("radius", 2)
            return image.filter(ImageFilter.GaussianBlur(radius))

        elif filter_type == FilterType.BOX_BLUR:
            radius = params.get("radius", 2)
            return image.filter(ImageFilter.BoxBlur(radius))

        elif filter_type == FilterType.SHARPEN:
            return image.filter(ImageFilter.SHARPEN)

        elif filter_type == FilterType.UNSHARP_MASK:
            radius = params.get("radius", 2)
            percent = params.get("percent", 150)
            threshold = params.get("threshold", 3)
            return image.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))

        elif filter_type == FilterType.EDGE_DETECTION:
            return image.filter(ImageFilter.FIND_EDGES)

        elif filter_type == FilterType.FIND_EDGES:
            return image.filter(ImageFilter.FIND_EDGES)

        elif filter_type == FilterType.CONTOUR:
            return image.filter(ImageFilter.CONTOUR)

        elif filter_type == FilterType.EMBOSS:
            return image.filter(ImageFilter.EMBOSS)

        elif filter_type == FilterType.SMOOTH:
            return image.filter(ImageFilter.SMOOTH)

        elif filter_type == FilterType.SMOOTH_MORE:
            return image.filter(ImageFilter.SMOOTH_MORE)

        elif filter_type == FilterType.DETAIL:
            return image.filter(ImageFilter.DETAIL)

        elif filter_type == FilterType.EDGE_ENHANCE:
            return image.filter(ImageFilter.EDGE_ENHANCE)

        elif filter_type == FilterType.EDGE_ENHANCE_MORE:
            return image.filter(ImageFilter.EDGE_ENHANCE_MORE)

        else:
            raise ProcessingError(f"Unknown filter type: {filter_type}")

    except Exception as e:
        raise ProcessingError(f"Failed to apply filter {filter_type.value}: {e}") from e


def convert_image_format(
    image: Image.Image,
    target_format: ImageFormat,
    quality: int = 85,
    optimize: bool = True,
) -> Image.Image:
    """
    Convert image to target format with appropriate mode handling.

    Args:
        image: PIL Image object.
        target_format: Target image format.
        quality: Quality for lossy formats (1-100).
        optimize: Whether to optimize file size.

    Returns:
        Converted PIL Image object ready for saving.
    """
    # Handle mode conversions for different formats
    if target_format == ImageFormat.JPEG:
        # JPEG doesn't support transparency
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
        elif image.mode != "RGB":
            return image.convert("RGB")

    elif target_format == ImageFormat.PNG:
        # PNG supports all modes, but optimize palette images
        if image.mode == "P":
            return image.convert("RGBA")

    elif target_format == ImageFormat.WEBP:
        # WebP supports both lossy and lossless
        if image.mode not in ("RGB", "RGBA", "CMYK"):
            return image.convert("RGBA" if "A" in image.mode else "RGB")

    return image


def save_image(
    image: Image.Image,
    output_path: Path,
    image_format: ImageFormat,
    quality: int = 85,
    optimize: bool = True,
) -> None:
    """
    Save image to file with appropriate format options.

    Args:
        image: PIL Image object.
        output_path: Output file path.
        image_format: Target image format.
        quality: Quality for lossy formats.
        optimize: Whether to optimize file size.

    Raises:
        ProcessingError: If saving fails.
    """
    try:
        pil_format = get_pil_format(image_format)
        save_kwargs = {"format": pil_format, "optimize": optimize}

        if image_format in (ImageFormat.JPEG, ImageFormat.WEBP):
            save_kwargs["quality"] = quality
            if image_format == ImageFormat.WEBP:
                save_kwargs["method"] = 6  # Best compression

        image.save(output_path, **save_kwargs)
        logger.debug(f"Saved image to {output_path} as {pil_format}")

    except Exception as e:
        raise ProcessingError(f"Failed to save image to {output_path}: {e}") from e


class ImageProcessor:
    """
    Main image processing class providing high-level operations.

    This class handles image loading, processing, and saving with
    comprehensive error handling and validation.

    Example:
        >>> processor = ImageProcessor()
        >>> processor.resize("input.jpg", "output.jpg", (800, 600))
        >>> processor.convert_format("input.png", "output.webp")
        >>> processor.apply_filter("input.jpg", "output.jpg", "blur")
    """

    def __init__(self, default_quality: int = 85, default_optimize: bool = True):
        """
        Initialize the ImageProcessor.

        Args:
            default_quality: Default quality for lossy formats (1-100).
            default_optimize: Default optimization setting.
        """
        self.default_quality = validate_quality(default_quality)
        self.default_optimize = default_optimize
        logger.debug("ImageProcessor initialized")

    def resize(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        size: Tuple[int, int],
        maintain_aspect_ratio: bool = True,
        background_color: Tuple[int, int, int] = (255, 255, 255),
        quality: Optional[int] = None,
        optimize: Optional[bool] = None,
        overwrite: bool = False,
    ) -> Path:
        """
        Resize an image.

        Args:
            input_path: Path to input image.
            output_path: Path to output image.
            size: Target (width, height) in pixels.
            maintain_aspect_ratio: Preserve aspect ratio with padding.
            background_color: Padding color