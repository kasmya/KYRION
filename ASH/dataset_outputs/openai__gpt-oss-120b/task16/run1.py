"""
image_processor.py

A small, self‑contained image processing module that provides functions for
resizing, format conversion, applying simple filters (blur, sharpen,
edge‑detection) and batch‑processing an entire folder.

Only the Pillow library (PIL) is required in addition to the Python
standard library.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageFilter, UnidentifiedImageError

# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
FILTER_MAP: dict[str, Callable[[Image.Image], Image.Image]] = {
    "blur": lambda img: img.filter(ImageFilter.BLUR),
    "sharpen": lambda img: img.filter(ImageFilter.SHARPEN),
    "edge": lambda img: img.filter(ImageFilter.FIND_EDGES),
}

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class ImageProcessingError(RuntimeError):
    """Base exception for all errors raised by this module."""


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _ensure_path_is_image(path: Path) -> None:
    """
    Validate that *path* points to an existing file with an allowed image
    extension.

    Raises:
        ImageProcessingError: If the path does not exist, is not a file,
            or has an unsupported extension.
    """
    if not path.is_file():
        raise ImageProcessingError(f"Path '{path}' is not a file.")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImageProcessingError(
            f"File '{path}' has an unsupported extension. "
            f"Supported: {sorted(ALLOWED_EXTENSIONS)}"
        )


def _safe_output_path(
    output_dir: Path, original_name: str, target_format: Optional[str] = None
) -> Path:
    """
    Construct a safe output file path inside *output_dir*.

    The function normalises the path, ensures the result is a child of
    *output_dir* (preventing directory‑traversal attacks) and adds the
    appropriate file extension if *target_format* is supplied.

    Returns:
        Path: The resolved output file path.

    Raises:
        ImageProcessingError: If the resolved path escapes *output_dir*.
    """
    output_dir = output_dir.resolve()
    stem = Path(original_name).stem
    ext = f".{target_format.lower()}" if target_format else Path(original_name).suffix
    candidate = (output_dir / f"{stem}{ext}").resolve()
    if output_dir not in candidate.parents:
        raise ImageProcessingError("Attempted to write outside the output directory.")
    return candidate


# --------------------------------------------------------------------------- #
# Core processing functions
# --------------------------------------------------------------------------- #


def resize_image(
    input_path: Path,
    output_path: Path,
    size: Tuple[int, int],
    *,
    resample: int = Image.LANCZOS,
) -> None:
    """
    Resize an image to *size* and write the result to *output_path*.

    Args:
        input_path: Path to the source image.
        output_path: Destination path for the resized image.
        size: Desired width and height (width, height).
        resample: Resampling filter to use (default: Image.LANCZOS).

    Raises:
        ImageProcessingError: If the image cannot be opened, processed,
            or saved.
    """
    _ensure_path_is_image(input_path)
    try:
        with Image.open(input_path) as img:
            resized = img.resize(size, resample=resample)
            resized.save(output_path)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProcessingError(
            f"Failed to resize image '{input_path}': {exc}"
        ) from exc


def convert_image_format(
    input_path: Path,
    output_path: Path,
    target_format: str,
    *,
    quality: int = 85,
) -> None:
    """
    Convert an image to *target_format* and write it to *output_path*.

    Args:
        input_path: Path to the source image.
        output_path: Destination path for the converted image.
        target_format: One of ``'JPEG'``, ``'PNG'`` or ``'WEBP'`` (case‑insensitive).
        quality: Quality setting for lossy formats (default: 85).

    Raises:
        ImageProcessingError: If conversion fails or an unsupported format is
            requested.
    """
    _ensure_path_is_image(input_path)
    fmt = target_format.upper()
    if fmt not in ALLOWED_FORMATS:
        raise ImageProcessingError(
            f"Unsupported target format '{target_format}'. "
            f"Allowed: {sorted(ALLOWED_FORMATS)}"
        )
    try:
        with Image.open(input_path) as img:
            rgb_img = img.convert("RGB") if fmt == "JPEG" else img
            rgb_img.save(output_path, format=fmt, quality=quality)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProcessingError(
            f"Failed to convert image '{input_path}' to {fmt}: {exc}"
        ) from exc


def apply_filter(
    input_path: Path,
    output_path: Path,
    filter_name: str,
) -> None:
    """
    Apply a simple filter (blur, sharpen, edge) to an image.

    Args:
        input_path: Path to the source image.
        output_path: Destination path for the filtered image.
        filter_name: Name of the filter – ``'blur'``, ``'sharpen'`` or ``'edge'``.

    Raises:
        ImageProcessingError: If the filter name is unknown or processing fails.
    """
    _ensure_path_is_image(input_path)
    filter_func = FILTER_MAP.get(filter_name.lower())
    if filter_func is None:
        raise ImageProcessingError(
            f"Unsupported filter '{filter_name}'. "
            f"Supported: {sorted(FILTER_MAP)}"
        )
    try:
        with Image.open(input_path) as img:
            filtered = filter_func(img)
            filtered.save(output_path)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProcessingError(
            f"Failed to apply filter '{filter_name}' on '{input_path}': {exc}"
        ) from exc


def process_folder(
    input_dir: Path,
    output_dir: Path,
    *,
    size: Optional[Tuple[int, int]] = None,
    target_format: Optional[str] = None,
    filter_name: Optional[str] = None,
    overwrite: bool = False,
) -> List[Path]:
    """
    Batch‑process every supported image in *input_dir*.

    For each image the following optional steps are performed in order:
    1. Resize (if *size* is provided)
    2. Format conversion (if *target_format* is provided)
    3. Filter application (if *filter_name* is provided)

    The processed files are written to *output_dir* preserving the original
    filename (with a new extension if the format changes).

    Args:
        input_dir: Directory containing source images.
        output_dir: Directory where processed images will be saved.
        size: Desired dimensions for resizing (width, height) or ``None``.
        target_format: Desired output format or ``None``.
        filter_name: Name of filter to apply or ``None``.
        overwrite: If ``True`` existing files in *output_dir* will be overwritten.

    Returns:
        List[Path]: Paths of all successfully processed images.

    Raises:
        ImageProcessingError: If *input_dir* or *output_dir* are invalid,
            or an unrecoverable error occurs during processing.
    """
    if not input_dir.is_dir():
        raise ImageProcessingError(f"Input directory '{input_dir}' does not exist.")
    output_dir.mkdir(parents=True, exist_ok=True)

    processed: List[Path] = []

    for entry in input_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue  # Skip non‑image files silently

        try:
            # Determine the final extension based on target format (if any)
            final_ext = (
                f".{target_format.lower()}"
                if target_format
                else entry.suffix.lower()
            )
            out_path = _safe_output_path(
                output_dir, entry.name, target_format=target_format
            )
            if out_path.exists() and not overwrite:
                raise ImageProcessingError(
                    f"Output file '{out_path}' already exists and overwrite=False."
                )

            # Work on a temporary in‑memory image to avoid repeated disk I/O
            with Image.open(entry) as img:
                working = img

                if size:
                    working = working.resize(size, resample=Image.LANCZOS)

                if filter_name:
                    filter_func = FILTER_MAP.get(filter_name.lower())
                    if not filter_func:
                        raise ImageProcessingError(
                            f"Unsupported filter '{filter_name}'."
                        )
                    working = filter_func(working)

                save_kwargs = {}
                fmt = target_format.upper() if target_format else img.format
                if fmt == "JPEG":
                    working = working.convert("RGB")
                    save_kwargs["quality"] = 85

                working.save(out_path, format=fmt, **save_kwargs)

            processed.append(out_path.resolve())
        except ImageProcessingError:
            # Propagate known errors with context
            raise
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageProcessingError(
                f"Failed processing file '{entry}': {exc}"
            ) from exc

    return processed


__all__ = [
    "ImageProcessingError",
    "resize_image",
    "convert_image_format",
    "apply_filter",
    "process_folder",
]