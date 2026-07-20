"""
image_processor.py

A small image processing library that supports:
- Resizing images
- Converting between JPEG, PNG and WebP
- Applying basic filters (blur, sharpen, edge detection)
- Batch processing of directories

Only the Pillow library (PIL) is used, which is a well‑known dependency.
The module follows security best practices by:
    * Restricting processed files to a whitelist of extensions.
    * Normalising paths and preventing directory traversal.
    * Using context managers for file I/O.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterable, List, Literal, Tuple, Union

from PIL import Image, ImageFilter, UnidentifiedImageError

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Allowed file extensions (lower case, without leading dot)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# --------------------------------------------------------------------------- #
# Custom Exceptions
# --------------------------------------------------------------------------- #

class ImageProcessorError(Exception):
    """Base class for all image‑processor related errors."""


class UnsupportedFormatError(ImageProcessorError):
    """Raised when an unsupported file format is encountered."""


class ImageOperationError(ImageProcessorError):
    """Raised when an operation on an image fails."""


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #

def _validate_path(file_path: Path) -> Path:
    """
    Validate that a path points to a file with an allowed extension and is
    inside a safe directory (i.e. no path traversal tricks).

    Args:
        file_path: The path to validate.

    Returns:
        The resolved absolute path.

    Raises:
        UnsupportedFormatError: If the extension is not whitelisted.
        FileNotFoundError: If the file does not exist.
    """
    resolved = file_path.expanduser().resolve(strict=False)

    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {resolved}")

    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(f"Extension '{resolved.suffix}' is not supported.")

    return resolved


def _ensure_directory(path: Path) -> Path:
    """
    Ensure that a directory exists; if not, create it.

    Args:
        path: Directory path.

    Returns:
        The resolved absolute path.
    """
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


# --------------------------------------------------------------------------- #
# Core Functionalities
# --------------------------------------------------------------------------- #

ResizeMode = Literal["fit", "fill", "stretch"]  # can be extended later
FilterName = Literal["blur", "sharpen", "edge"]


def resize_image(
    src: Union[str, Path],
    dst: Union[str, Path],
    size: Tuple[int, int],
    mode: ResizeMode = "fit",
) -> None:
    """
    Resize an image and save it to a new location.

    Args:
        src: Source image path.
        dst: Destination image path.
        size: Target size as (width, height).
        mode: How to handle aspect ratio.
            - "fit": preserve aspect ratio, fit inside `size`.
            - "fill": preserve aspect ratio, fill and crop to `size`.
            - "stretch": ignore aspect ratio.

    Raises:
        ImageOperationError: If Pillow cannot process the image.
    """
    src_path = _validate_path(Path(src))
    dst_path = Path(dst).expanduser().resolve()
    _ensure_directory(dst_path.parent)

    try:
        with Image.open(src_path) as im:
            logger.debug("Opened image %s (size=%s, mode=%s)", src_path, im.size, im.mode)

            if mode == "fit":
                im.thumbnail(size, Image.Resampling.LANCZOS)
                new_im = im
            elif mode == "fill":
                # Compute scaling factor and crop
                ratio = max(size[0] / im.width, size[1] / im.height)
                new_size = (int(im.width * ratio), int(im.height * ratio))
                im_resized = im.resize(new_size, Image.Resampling.LANCZOS)
                left = (im_resized.width - size[0]) // 2
                top = (im_resized.height - size[1]) // 2
                new_im = im_resized.crop((left, top, left + size[0], top + size[1]))
            elif mode == "stretch":
                new_im = im.resize(size, Image.Resampling.LANCZOS)
            else:
                raise ValueError(f"Unsupported resize mode: {mode}")

            new_im.save(dst_path)
            logger.info("Resized image saved to %s", dst_path)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageOperationError(f"Failed to resize image '{src_path}': {exc}") from exc


def convert_image_format(
    src: Union[str, Path],
    dst: Union[str, Path],
    fmt: Literal["JPEG", "PNG", "WEBP"],
    quality: int = 85,
) -> None:
    """
    Convert an image from its current format to another (JPEG, PNG, WEBP).

    Args:
        src: Source image path.
        dst: Destination image path (extension can be omitted; will be added).
        fmt: Target format.
        quality: Quality/compression setting (relevant for JPEG & WEBP).

    Raises:
        ImageOperationError: If conversion fails.
    """
    src_path = _validate_path(Path(src))
    dst_path = Path(dst).expanduser().resolve()
    _ensure_directory(dst_path.parent)

    # Normalize destination suffix
    dst_path = dst_path.with_suffix(f".{fmt.lower()}")

    try:
        with Image.open(src_path) as im:
            save_kwargs = {}
            if fmt == "JPEG":
                save_kwargs["quality"] = max(1, min(100, quality))
                if im.mode in ("RGBA", "LA"):
                    # JPEG does not support alpha; convert with white background
                    background = Image.new("RGB", im.size, (255, 255, 255))
                    background.paste(im, mask=im.split()[-1])  # paste using alpha channel as mask
                    im = background
                else:
                    im = im.convert("RGB")
            elif fmt == "WEBP":
                save_kwargs["quality"] = max(1, min(100, quality))

            im.save(dst_path, fmt, **save_kwargs)
            logger.info("Converted %s to %s (%s)", src_path, dst_path, fmt)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageOperationError(f"Failed to convert image '{src_path}': {exc}") from exc


def apply_filter(
    src: Union[str, Path],
    dst: Union[str, Path],
    filter_name: FilterName,
) -> None:
    """
    Apply a predefined filter to an image.

    Args:
        src: Source image path.
        dst: Destination image path.
        filter_name: One of "blur", "sharpen", "edge".

    Raises:
        ImageOperationError: If the filter cannot be applied.
    """
    src_path = _validate_path(Path(src))
    dst_path = Path(dst).expanduser().resolve()
    _ensure_directory(dst_path.parent)

    FILTER_MAP = {
        "blur": ImageFilter.BLUR,
        "sharpen": ImageFilter.SHARPEN,
        "edge": ImageFilter.FIND_EDGES,
    }

    if filter_name not in FILTER_MAP:
        raise ValueError(f"Unsupported filter: {filter_name}")

    try:
        with Image.open(src_path) as im:
            filtered = im.filter(FILTER_MAP[filter_name])
            filtered.save(dst_path)
            logger.info("Applied filter '%s' to %s, saved as %s", filter_name, src_path, dst_path)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageOperationError(f"Failed to apply filter on '{src_path}': {exc}") from exc


def batch_process(
    sources: Iterable[Union[str, Path]],
    destination_dir: Union[str, Path],
    *,
    resize: Tuple[int, int] | None = None,
    resize_mode: ResizeMode = "fit",
    convert_to: Literal["JPEG", "PNG", "WEBP"] | None = None,
    filter_name: FilterName | None = None,
    quality: int = 85,
) -> List[Path]:
    """
    Process a batch of images applying the selected operations.

    The order of operations is: resize → filter → format conversion.

    Args:
        sources: Iterable of source image paths.
        destination_dir: Directory where processed images will be stored.
        resize: Desired size (width, height) or None to skip resizing.
        resize_mode: Resize mode (only used if `resize` is set).
        convert_to: Target