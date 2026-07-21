"""
image_processor.py

A small, self‑contained image processing module.

Features
--------
- Resize images.
- Convert among JPEG, PNG, and WebP formats.
- Apply blur, sharpen, or edge‑detection filters.
- Batch‑process all images in a folder with any combination of the above.

Only the Pillow library (the de‑facto standard for image handling in Python)
is required in addition to the standard library.

Security & safety
------------------
- All file system interactions are performed with :class:`pathlib.Path`.
- Input paths are validated to ensure they point to supported image files.
- Output paths are resolved relative to a user‑provided destination directory to
  avoid path‑traversal attacks.
- Exceptions are wrapped in :class:`ImageProcessingError` with clear messages.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterable, Literal, Optional, Tuple, Union

from PIL import Image, ImageFilter, UnidentifiedImageError

# Public API
__all__ = [
    "ImageProcessingError",
    "resize_image",
    "convert_image",
    "apply_filter",
    "process_folder",
]

# --------------------------------------------------------------------------- #
# Types & constants
# --------------------------------------------------------------------------- #

SupportedFormat = Literal["JPEG", "PNG", "WEBP"]
SupportedFilter = Literal["blur", "sharpen", "edge"]

_SUPPORTED_EXTENSIONS: dict[SupportedFormat, tuple[str, ...]] = {
    "JPEG": (".jpg", ".jpeg"),
    "PNG": (".png",),
    "WEBP": (".webp",),
}
_ALL_EXTENSIONS: tuple[str, ...] = tuple(
    ext for exts in _SUPPORTED_EXTENSIONS.values() for ext in exts
)

_FILTER_MAP: dict[SupportedFilter, ImageFilter.Filter] = {
    "blur": ImageFilter.BLUR,
    "sharpen": ImageFilter.SHARPEN,
    "edge": ImageFilter.FIND_EDGES,
}


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class ImageProcessingError(RuntimeError):
    """Base exception for all errors raised by this module."""


# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #
def _ensure_image_file(path: Path) -> None:
    """Validate that *path* exists and has a supported image extension.

    Raises
    ------
    ImageProcessingError
        If the file does not exist, is not a file, or has an unsupported
        extension.
    """
    if not path.is_file():
        raise ImageProcessingError(f"Path does not point to a file: {path}")

    if path.suffix.lower() not in _ALL_EXTENSIONS:
        raise ImageProcessingError(
            f"Unsupported file extension '{path.suffix}' for '{path}'. "
            f"Supported extensions: {', '.join(_ALL_EXTENSIONS)}"
        )


def _resolve_output_path(
    input_path: Path, output_dir: Path, target_format: Optional[SupportedFormat] = None
) -> Path:
    """Create a safe output path inside *output_dir* preserving the stem.

    The function normalises the target format extension if supplied.

    Parameters
    ----------
    input_path: Path
        Original image file.
    output_dir: Path
        Destination directory (must already exist or be created beforehand).
    target_format: SupportedFormat | None
        Desired output format; if ``None`` the original suffix is kept.

    Returns
    -------
    Path
        Fully resolved output file path.

    Raises
    ------
    ImageProcessingError
        If *output_dir* cannot be created or is not a directory.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImageProcessingError(f"Unable to create output directory '{output_dir}': {exc}") from exc

    if not output_dir.is_dir():
        raise ImageProcessingError(f"Output path is not a directory: {output_dir}")

    ext = (
        f".{target_format.lower()}"
        if target_format
        else input_path.suffix.lower()
    )
    return (output_dir / input_path.stem).with_suffix(ext)


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #
def resize_image(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    size: Tuple[int, int],
    resample: int = Image.LANCZOS,
) -> None:
    """
    Resize an image to *size* and save it to *output_path*.

    Parameters
    ----------
    input_path: str | Path
        Path to the source image.
    output_path: str | Path
        Destination path (directory will be created if necessary).
    size: tuple[int, int]
        Desired width and height in pixels.
    resample: int, optional
        Pillow resampling filter; defaults to :data:`Image.LANCZOS`.

    Raises
    ------
    ImageProcessingError
        If loading, processing, or saving fails.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)

    _ensure_image_file(in_path)

    try:
        with Image.open(in_path) as img:
            img = img.convert("RGB")  # Ensure consistent mode for all formats
            resized = img.resize(size, resample=resample)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            resized.save(out_path)
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageProcessingError(f"Failed to resize image '{in_path}': {exc}") from exc


def convert_image(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    fmt: SupportedFormat,
    quality: int = 85,
) -> None:
    """
    Convert an image to a different format.

    Parameters
    ----------
    input_path: str | Path
        Path to the source image.
    output_path: str | Path
        Destination path (extension may be omitted; will be set according to *fmt*).
    fmt: SupportedFormat
        Target image format (``'JPEG'``, ``'PNG'`` or ``'WEBP'``).
    quality: int, optional
        Output quality for lossy formats (JPEG/WebP). Ignored for PNG.

    Raises
    ------
    ImageProcessingError
        If conversion fails.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)

    _ensure_image_file(in_path)

    try:
        with Image.open(in_path) as img:
            # Pillow expects mode 'RGB' for JPEG/WebP; preserve alpha for PNG
            if fmt in ("JPEG", "WEBP"):
                img = img.convert("RGB")
            out_path = out_path.with_suffix(f".{fmt.lower()}")
            out_path.parent.mkdir(parents=True, exist_ok=True)

            save_kwargs: dict = {}
            if fmt in ("JPEG", "WEBP"):
                save_kwargs["quality"] = quality

            img.save(out_path, fmt, **save_kwargs)
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageProcessingError(f"Failed to convert image '{in_path}': {exc}") from exc


def apply_filter(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    filter_name: SupportedFilter,
) -> None:
    """
    Apply a simple filter (blur, sharpen, edge detection) to an image.

    Parameters
    ----------
    input_path: str | Path
        Path to the source image.
    output_path: str | Path
        Destination path.
    filter_name: SupportedFilter
        Name of the filter to apply.

    Raises
    ------
    ImageProcessingError
        If the filter cannot be applied or the image cannot be saved.
    """
    if filter_name not in _FILTER_MAP:
        raise ImageProcessingError(f"Unsupported filter: {filter_name}")

    in_path = Path(input_path)
    out_path = Path(output_path)

    _ensure_image_file(in_path)

    try:
        with Image.open(in_path) as img:
            filtered = img.filter(_FILTER_MAP[filter_name])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            filtered.save(out_path)
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageProcessingError(f"Failed to apply filter '{filter_name}' on '{in_path}': {exc}") from exc


def process_folder(
    folder_path: Union[str, Path],
    output_folder: Union[str, Path],
    *,
    size: Optional[Tuple[int, int]] = None,
    convert_to: Optional[SupportedFormat] = None,
    filter_name: Optional[SupportedFilter] = None,
    overwrite: bool = False,
) -> None:
    """
    Batch‑process every supported image in *folder_path*.

    For each image the following operations are performed in order (if supplied):
    1. Resize
    2. Convert format
    3. Apply filter

    Parameters
    ----------
    folder_path: str | Path
        Directory containing source images.
    output_folder: str | Path
        Destination directory for processed images.
    size: tuple[int, int] | None, optional
        Target dimensions for resizing. If ``None`` resizing is skipped.
    convert_to: SupportedFormat | None, optional
        Desired output format. If ``None`` the original format is kept.
    filter_name: SupportedFilter | None, optional
        Filter to apply. If ``None`` no filter is applied.
    overwrite: bool, default False
        Whether to overwrite existing files in *output_folder*.

    Raises
    ------
    ImageProcessingError
        If the source folder cannot be read or any image fails processing.
    """
    src_dir = Path(folder_path)
    dst_dir = Path(output_folder)

    if not src_dir.is_dir():
        raise ImageProcessingError(f"Source folder does not exist or is not a directory: {src_dir}")

    # Gather all files with supported extensions (case‑insensitive)
    image_paths: Iterable[Path] = (
        p for p in src_dir.rglob("*") if p.is_file() and p.suffix.lower() in _ALL_EXTENSIONS
    )

    for img_path in image_paths:
        try:
            # Resolve final output path step‑by‑step
            intermediate_path = img_path

            # 1. Resize (creates a temporary file)
            if size:
                intermediate_path = _resolve_output_path(
                    img_path, dst_dir, target_format=None
                )
                resize_image(img_path, intermediate_path, size)

            # 2. Convert format
            if convert_to:
                target_path = _resolve_output_path(
                    intermediate_path, dst_dir, target_format=convert_to
                )
                convert_image(intermediate_path, target_path, convert_to)
                intermediate_path = target_path

            # 3. Apply filter
            if filter_name:
                target_path = _resolve_output_path(
                    intermediate_path, dst_dir, target_format=None
                )
                apply_filter(intermediate_path, target_path, filter_name)
                intermediate_path = target_path

            # If no operations were specified, just copy the file
            if not any([size, convert_to, filter_name]):
                target_path = _resolve_output_path(img_path, dst_dir, None)
                if not target_path.exists() or overwrite:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with img_path.open("rb") as src_f, target_path.open("wb") as dst_f:
                        dst_f.write(src_f.read())
        except ImageProcessingError as exc:
            raise ImageProcessingError(f"Error processing '{img_path}': {exc}") from exc