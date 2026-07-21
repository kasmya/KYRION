"""
image_processor.py

A lightweight image processing module that provides functions for resizing,
format conversion, and applying simple filters (blur, sharpen, edge detection).
It also supports batch processing of all supported images within a folder.

Only the Python standard library and the Pillow (PIL) package are required.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterable, Literal, Sequence, Tuple, Union

from PIL import Image, ImageFilter, UnidentifiedImageError

# Public API
__all__: Sequence[str] = (
    "ImageProcessingError",
    "SUPPORTED_FORMATS",
    "SUPPORTED_FILTERS",
    "load_image",
    "save_image",
    "resize_image",
    "convert_image_format",
    "apply_filter",
    "process_image",
    "batch_process_folder",
)

# --------------------------------------------------------------------------- #
# Types and constants
# --------------------------------------------------------------------------- #

ImagePath = Union[str, Path]
ResizeMode = Literal["fit", "fill"]  # fit keeps aspect ratio, fill may crop
FilterName = Literal["blur", "sharpen", "edge"]

SUPPORTED_FORMATS: Tuple[str, ...] = ("JPEG", "PNG", "WEBP")
SUPPORTED_FILTERS: Tuple[FilterName, ...] = ("blur", "sharpen", "edge")

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class ImageProcessingError(RuntimeError):
    """Base exception for all errors raised by this module."""


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _validate_path(path: ImagePath) -> Path:
    """
    Convert to :class:`~pathlib.Path` and ensure the path is absolute and exists.

    Raises:
        ImageProcessingError: If the path does not exist or is not a file.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ImageProcessingError(f"File not found: {p}")
    return p


def _ensure_output_dir(output_path: Path) -> None:
    """
    Create parent directories for ``output_path`` if they do not exist.

    Raises:
        ImageProcessingError: If the directory cannot be created.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImageProcessingError(f"Failed to create output directory: {exc}") from exc


def _safe_save(image: Image.Image, output_path: Path, format: str) -> None:
    """
    Save an image safely, handling format-specific options.

    Args:
        image: Pillow image instance.
        output_path: Destination file path.
        format: Desired output format (must be in ``SUPPORTED_FORMATS``).

    Raises:
        ImageProcessingError: If saving fails.
    """
    if format.upper() not in SUPPORTED_FORMATS:
        raise ImageProcessingError(f"Unsupported output format: {format}")

    _ensure_output_dir(output_path)

    save_kwargs = {}
    if format.upper() == "JPEG":
        save_kwargs["quality"] = 85  # reasonable default
        save_kwargs["subsampling"] = "4:2:0"

    try:
        image.save(output_path, format=format.upper(), **save_kwargs)
    except OSError as exc:
        raise ImageProcessingError(f"Failed to save image: {exc}") from exc


# --------------------------------------------------------------------------- #
# Core API
# --------------------------------------------------------------------------- #


def load_image(path: ImagePath) -> Image.Image:
    """
    Load an image from disk.

    Args:
        path: Path to the image file.

    Returns:
        Pillow ``Image`` object.

    Raises:
        ImageProcessingError: If loading fails or the file is not a supported image.
    """
    p = _validate_path(path)
    try:
        return Image.open(p).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProcessingError(f"Unable to load image {p}: {exc}") from exc


def save_image(image: Image.Image, output_path: ImagePath, format: str) -> None:
    """
    Save an image to disk with the specified format.

    Args:
        image: Pillow ``Image`` instance to save.
        output_path: Destination file path.
        format: Desired format (e.g., ``"JPEG"``, ``"PNG"``, ``"WEBP"``).

    Raises:
        ImageProcessingError: If saving fails.
    """
    out_path = Path(output_path).expanduser().resolve()
    _safe_save(image, out_path, format)


def resize_image(
    image: Image.Image,
    size: Tuple[int, int],
    mode: ResizeMode = "fit",
) -> Image.Image:
    """
    Resize an image.

    Args:
        image: Pillow ``Image`` instance.
        size: Desired width and height in pixels.
        mode: ``"fit"`` maintains aspect ratio (adds padding if needed),
              ``"fill"`` crops to fill the exact dimensions.

    Returns:
        A new resized ``Image`` instance.

    Raises:
        ImageProcessingError: If resizing fails.
    """
    if mode not in ("fit", "fill"):
        raise ImageProcessingError(f"Invalid resize mode: {mode}")

    try:
        if mode == "fit":
            # Preserve aspect ratio, pad with transparent background if needed
            image.thumbnail(size, Image.Resampling.LANCZOS)
            background = Image.new("RGBA", size, (0, 0, 0, 0))
            offset = ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
            background.paste(image, offset)
            return background
        else:  # fill
            # Resize then crop centrally
            ratio = max(size[0] / image.width, size[1] / image.height)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            resized = image.resize(new_size, Image.Resampling.LANCZOS)
            left = (new_size[0] - size[0]) // 2
            top = (new_size[1] - size[1]) // 2
            right = left + size[0]
            bottom = top + size[1]
            return resized.crop((left, top, right, bottom))
    except Exception as exc:
        raise ImageProcessingError(f"Failed to resize image: {exc}") from exc


def convert_image_format(image: Image.Image, format: str) -> Image.Image:
    """
    Convert an image to another format.

    This function does not modify the image data; it merely ensures the image
    can be saved in the requested format. Pillow handles mode conversion internally.

    Args:
        image: Pillow ``Image`` instance.
        format: Target format (must be in ``SUPPORTED_FORMATS``).

    Returns:
        The same ``Image`` instance (unchanged).

    Raises:
        ImageProcessingError: If the format is unsupported.
    """
    if format.upper() not in SUPPORTED_FORMATS:
        raise ImageProcessingError(f"Unsupported target format: {format}")
    return image  # No operation needed; format is applied during saving


def apply_filter(image: Image.Image, filter_name: FilterName) -> Image.Image:
    """
    Apply a simple filter to an image.

    Args:
        image: Pillow ``Image`` instance.
        filter_name: One of ``"blur"``, ``"sharpen"``, or ``"edge"``.

    Returns:
        A new ``Image`` with the filter applied.

    Raises:
        ImageProcessingError: If the filter name is invalid.
    """
    if filter_name not in SUPPORTED_FILTERS:
        raise ImageProcessingError(f"Unsupported filter: {filter_name}")

    try:
        if filter_name == "blur":
            return image.filter(ImageFilter.GaussianBlur(radius=2))
        if filter_name == "sharpen":
            return image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        if filter_name == "edge":
            return image.filter(ImageFilter.FIND_EDGES)
    except Exception as exc:
        raise ImageProcessingError(f"Failed to apply filter '{filter_name}': {exc}") from exc


def process_image(
    input_path: ImagePath,
    output_path: ImagePath,
    *,
    size: Tuple[int, int] | None = None,
    resize_mode: ResizeMode = "fit",
    target_format: str | None = None,
    filter_name: FilterName | None = None,
) -> None:
    """
    Load an image, optionally resize, convert format, apply a filter, and save it.

    Args:
        input_path: Path to the source image.
        output_path: Destination path for the processed image.
        size: Desired dimensions (width, height). If ``None``, no resizing occurs.
        resize_mode: ``"fit"`` or ``"fill"`` – used only when ``size`` is provided.
        target_format: Desired output format (e.g., ``"JPEG"``). If ``None``,
                       format is inferred from ``output_path`` extension.
        filter_name: Optional filter to apply.

    Raises:
        ImageProcessingError: If any step fails.
    """
    image = load_image(input_path)

    if size:
        image = resize_image(image, size, mode=resize_mode)

    if filter_name:
        image = apply_filter(image, filter_name)

    # Determine format from argument or file extension
    fmt = target_format or Path(output_path).suffix.lstrip(".").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if fmt not in SUPPORTED_FORMATS:
        raise ImageProcessingError(f"Unsupported output format derived from path: {fmt}")

    save_image(image, output_path, fmt)


def batch_process_folder(
    input_folder: ImagePath,
    output_folder: ImagePath,
    *,
    recursive: bool = True,
    include_patterns: Iterable[str] = ("*.jpg", "*.jpeg", "*.png", "*.webp"),
    size: Tuple[int, int] | None = None,
    resize_mode: ResizeMode = "fit",
    target_format: str | None = None,
    filter_name: FilterName | None = None,
) -> None:
    """
    Process all images in a folder (optionally recursively) and write results to another folder.

    Args:
        input_folder: Directory containing source images.
        output_folder: Directory where processed images will be stored.
        recursive: Whether to walk subdirectories.
        include_patterns: Glob patterns for files to include.
        size: Desired dimensions for resizing; ``None`` disables resizing.
        resize_mode: ``"fit"`` or ``"fill"`` – used only when ``size`` is provided.
        target_format: Desired output format; if ``None`` the original format is kept.
        filter_name: Optional filter to apply to every image.

    Raises:
        ImageProcessingError: If folder validation fails or any image cannot be processed.
    """
    input_root = Path(input_folder).expanduser().resolve()
    output_root = Path(output_folder).expanduser().resolve()

    if not input_root.is_dir():
        raise ImageProcessingError(f"Input folder does not exist: {input_root}")

    _ensure_output_dir(output_root / "placeholder")  # ensure we can write

    # Build list of files matching patterns
    files: list[Path] = []
    for pattern in include_patterns:
        if recursive:
            files.extend(input_root.rglob(pattern))
        else:
            files.extend(input_root.glob(pattern))

    if not files:
        raise ImageProcessingError("No matching image files found in the input folder.")

    for src_path in files:
        # Preserve relative path structure
        rel_path = src_path.relative_to(input_root)
        dest_path = output_root / rel_path

        # Adjust extension if target_format is forced
        if target_format:
            dest_path = dest_path.with_suffix(f".{target_format.lower()}")

        try:
            process_image(
                src_path,
                dest_path,
                size=size,
                resize_mode=resize_mode,
                target_format=target_format,
                filter_name=filter_name,
            )
        except ImageProcessingError as exc:
            # Continue processing other files but report the error
            raise ImageProcessingError(f"Failed processing {src_path}: {exc}") from exc