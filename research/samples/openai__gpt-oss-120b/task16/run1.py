#!/usr/bin/env python3
"""
Image Processor Module

Provides utilities to resize images, convert between JPEG/PNG/WebP,
apply basic filters (blur, sharpen, edge detection) and batch‑process
multiple files safely.

Only Pillow (PIL) and the Python standard library are required.
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Iterable, List, Tuple, Union, Callable, Optional

from enum import Enum, auto

from PIL import Image, ImageFilter, UnidentifiedImageError

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Enums & Type Aliases
# --------------------------------------------------------------------------- #

class ImageFormat(str, Enum):
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


class FilterType(str, Enum):
    BLUR = "blur"
    SHARPEN = "sharpen"
    EDGE_ENHANCE = "edge_enhance"


# Mapping from FilterType to Pillow filter objects
_FILTER_MAP: dict[FilterType, Callable[[], ImageFilter.Filter]] = {
    FilterType.BLUR: ImageFilter.BLUR,
    FilterType.SHARPEN: ImageFilter.SHARPEN,
    FilterType.EDGE_ENHANCE: ImageFilter.FIND_EDGES,
}


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class ImageProcessingError(RuntimeError):
    """Base class for errors raised by ImageProcessor."""


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #

def _safe_path(path: Union[str, Path]) -> Path:
    """
    Resolve a filesystem path safely to avoid path‑traversal attacks.

    Args:
        path: Input path as string or Path.

    Returns:
        A normalized absolute Path object.
    """
    p = Path(path).expanduser().resolve()
    return p


def _ensure_directory(path: Path) -> None:
    """
    Ensure that the directory for *path* exists.

    Args:
        path: Destination file path.

    Raises:
        ImageProcessingError: If the directory cannot be created.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImageProcessingError(f"Unable to create directory {path.parent}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Core Processor
# --------------------------------------------------------------------------- #

class ImageProcessor:
    """
    High‑level wrapper around Pillow to perform common image operations
    with type hints, error handling and security‑focused path handling.
    """

    def __init__(self, *, keep_exif: bool = True) -> None:
        """
        Initialize the processor.

        Args:
            keep_exif: Whether to preserve EXIF metadata on format conversion.
        """
        self.keep_exif = keep_exif

    # ------------------------------------------------------------------- #
    # Core operations
    # ------------------------------------------------------------------- #

    @staticmethod
    def _load_image(src: Path) -> Image.Image:
        """
        Load an image from disk.

        Args:
            src: Path to source image.

        Returns:
            Pillow Image object.

        Raises:
            ImageProcessingError: If the file cannot be opened or is not an image.
        """
        try:
            img = Image.open(src)
            img.load()  # Force loading to catch truncated files early
            return img
        except (OSError, UnidentifiedImageError) as exc:
            raise ImageProcessingError(f"Failed to open image {src}: {exc}") from exc

    def resize(
        self,
        src: Union[str, Path],
        dest: Union[str, Path],
        size: Tuple[int, int],
        *,
        resample: int = Image.LANCZOS,
    ) -> None:
        """
        Resize an image to the given dimensions.

        Args:
            src: Source image path.
            dest: Destination path.
            size: Desired (width, height) in pixels.
            resample: Resampling filter (default: LANCZOS).

        Raises:
            ImageProcessingError: On I/O or processing failure.
        """
        src_path = _safe_path(src)
        dest_path = _safe_path(dest)

        logger.debug("Resizing %s -> %s to %s", src_path, dest_path, size)

        try:
            img = self._load_image(src_path)
            resized = img.resize(size, resample=resample)
            _ensure_directory(dest_path)
            save_kwargs = {}
            if self.keep_exif and "exif" in img.info:
                save_kwargs["exif"] = img.info["exif"]
            resized.save(dest_path, **save_kwargs)
        except Exception as exc:
            raise ImageProcessingError(f"Resize failed for {src_path}: {exc}") from exc

    def convert_format(
        self,
        src: Union[str, Path],
        dest: Union[str, Path],
        fmt: ImageFormat,
        *,
        quality: Optional[int] = None,
    ) -> None:
        """
        Convert an image to a different format.

        Args:
            src: Source image path.
            dest: Destination path (extension may be ignored).
            fmt: Target image format.
            quality: Optional quality (1‑95) for lossy formats (e.g., JPEG).

        Raises:
            ImageProcessingError: On failure.
        """
        src_path = _safe_path(src)
        dest_path = _safe_path(dest)

        logger.debug("Converting %s -> %s as %s", src_path, dest_path, fmt)

        try:
            img = self._load_image(src_path)
            _ensure_directory(dest_path)

            save_kwargs: dict = {"format": fmt.value}
            if quality is not None:
                save_kwargs["quality"] = quality
            if self.keep_exif and "exif" in img.info:
                save_kwargs["exif"] = img.info["exif"]

            img.save(dest_path, **save_kwargs)
        except Exception as exc:
            raise ImageProcessingError(
                f"Format conversion failed for {src_path} to {fmt}"
            ) from exc

    def apply_filter(
        self,
        src: Union[str, Path],
        dest: Union[str, Path],
        filter_type: FilterType,
    ) -> None:
        """
        Apply a visual filter to an image.

        Args:
            src: Source image path.
            dest: Destination path.
            filter_type: Type of filter to apply.

        Raises:
            ImageProcessingError: On I/O or processing failure.
        """
        src_path = _safe_path(src)
        dest_path = _safe_path(dest)

        logger.debug("Applying filter %s on %s -> %s", filter_type, src_path, dest_path)

        try:
            img = self._load_image(src_path)

            filter_obj = _FILTER_MAP[filter_type]
            filtered = img.filter(filter_obj)

            _ensure_directory(dest_path)
            save_kwargs = {}
            if self.keep_exif and "exif" in img.info:
                save_kwargs["exif"] = img.info["exif"]

            filtered.save(dest_path, **save_kwargs)
        except Exception as exc:
            raise ImageProcessingError(
                f"Applying filter {filter_type} failed for {src_path}"
            ) from exc

    # ------------------------------------------------------------------- #
    # Batch processing
    # ------------------------------------------------------------------- #

    def batch_process(
        self,
        sources: Iterable[Union[str, Path]],
        destination_dir: Union[str, Path],
        *,
        resize_to: Optional[Tuple[int, int]] = None,
        convert_to: Optional[ImageFormat] = None,
        filter_type: Optional[FilterType] = None,
        quality: Optional[int] = None,
        overwrite: bool = False,
    ) -> List[Path]:
        """
        Process multiple images sequentially.

        The operations are applied in the order: resize → filter → format conversion.

        Args:
            sources: Iterable of image paths to process.
            destination_dir: Directory where processed images will be saved.
            resize_to: Optional (width, height) tuple