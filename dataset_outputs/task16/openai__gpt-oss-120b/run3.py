"""
image_processor.py

A small, self‑contained image processing utility supporting resizing,
format conversion, filtering and batch processing. It uses Pillow (PIL)
and the standard library only.

Features
--------
* Resize images while preserving aspect ratio.
* Convert between JPEG, PNG and WebP.
* Apply common filters: blur, sharpen, edge detection.
* Batch process a directory of images with a configurable pipeline.

Security & robustness
---------------------
* All file system interactions use :class:`pathlib.Path` with strict
  resolution to avoid path traversal.
* Only files with allowed extensions are processed.
* Comprehensive error handling with logging for traceability.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

from PIL import Image, ImageFilter, UnidentifiedImageError

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

ALLOWED_INPUT_EXTS: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")
ALLOWED_OUTPUT_EXTS: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_QUALITY: int = 85  # JPEG quality

# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #


def _ensure_safe_path(path: Path) -> Path:
    """
    Resolve the path and forbid traversal outside the current working directory.

    Raises
    ------
    PermissionError
        If the resolved path is outside the cwd.
    """
    resolved = path.resolve()
    cwd = Path.cwd().resolve()
    if not str(resolved).startswith(str(cwd)):
        raise PermissionError(f"Unsafe path detected: {resolved}")
    return resolved


def _open_image(src: Path) -> Image.Image:
    """
    Open an image file safely.

    Parameters
    ----------
    src : Path
        Path to the image file.

    Returns
    -------
    Image.Image
        Pillow image instance.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    UnidentifiedImageError
        If Pillow cannot identify the file as an image.
    """
    src = _ensure_safe_path(src)
    if not src.is_file():
        raise FileNotFoundError(f"File not found: {src}")

    try:
        img = Image.open(src)
        img.load()  # Force loading to catch errors early
        logger.debug("Opened image %s (mode=%s, size=%s)", src, img.mode, img.size)
        return img
    except UnidentifiedImageError as exc:
        raise UnidentifiedImageError(f"Cannot identify image file: {src}") from exc
    except OSError as exc:
        raise OSError(f"Error opening image {src}: {exc}") from exc


def _save_image(
    img: Image.Image,
    dst: Path,
    fmt: str | None = None,
    quality: int = DEFAULT_QUALITY,
) -> None:
    """
    Save an image safely.

    Parameters
    ----------
    img : Image.Image
        Pillow image to save.
    dst : Path
        Destination file path.
    fmt : str | None, optional
        Output format (e.g., "JPEG", "PNG", "WEBP"). If omitted,
        Pillow infers it from the file suffix.
    quality : int, optional
        Quality for lossy formats (JPEG/WebP). Ignored otherwise.
    """
    dst = _ensure_safe_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs: dict = {}
    if fmt:
        save_kwargs["format"] = fmt.upper()
    if fmt and fmt.upper() in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True

    try:
        img.save(dst, **save_kwargs)
        logger.info("Saved image to %s", dst)
    except OSError as exc:
        raise OSError(f"Failed to save image {dst}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def resize_image(
    src: Path,
    dst: Path,
    max_width: int,
    max_height: int,
    keep_aspect: bool = True,
    resample: int = Image.LANCZOS,
) -> None:
    """
    Resize an image to fit within the given dimensions.

    Parameters
    ----------
    src : Path
        Source image file.
    dst : Path
        Destination file.
    max_width : int
        Maximum width in pixels.
    max_height : int
        Maximum height in pixels.
    keep_aspect : bool, default True
        Preserve aspect ratio. If False, the image is forced to the exact size.
    resample : int, default Image.LANCZOS
        Resampling filter used for resizing.
    """
    img = _open_image(src)

    if keep_aspect:
        img.thumbnail((max_width, max_height), resample=resample)
        logger.debug(
            "Resized (aspect) %s to %s (max %dx%d)", src, img.size, max_width, max_height
        )
    else:
        img = img.resize((max_width, max_height), resample=resample)
        logger.debug(
            "Resized %s to exact size %dx%d", src, max_width, max_height
        )

    _save_image(img, dst)


def convert_format(
    src: Path,
    dst: Path,
    output_format: str,
    quality: int = DEFAULT_QUALITY,
) -> None:
    """
    Convert an image to another format.

    Parameters
    ----------
    src : Path
        Source image file.
    dst : Path
        Destination file (suffix may differ from source).
    output_format : str
        Desired output format: "JPEG", "PNG", or "WEBP".
    quality : int, optional
        Quality/compression level for JPEG or WebP.
    """
    fmt = output_format.lower()
    if f".{fmt}" not in ALLOWED_OUTPUT_EXTS:
        raise ValueError(f"Unsupported output format: {output_format}")

    img = _open_image(src)

    # Convert mode for JPEG compatibility
    if fmt == "jpeg" and img.mode in {"RGBA", "LA"}:
        img = img.convert("RGB")
        logger.debug("Converted image mode to RGB for JPEG output")

    _save_image(img, dst, fmt=fmt, quality=quality)


_FILTER_MAP: dict[str, Callable[[Image.Image], Image.Image]] = {
    "blur": lambda im: im.filter(ImageFilter.BLUR),
    "sharpen": lambda im: im.filter(ImageFilter.SHARPEN),
    "edge": lambda im: im.filter(ImageFilter.FIND_EDGES),
}


def apply_filter(src: Path, dst: Path, filter_name: str) -> None:
    """
    Apply a simple filter to an image.

    Parameters
    ----------
    src : Path
        Source image file.
    dst : Path
        Destination file.
    filter_name : str
        Name of the filter: "blur", "sharpen", or "edge".
    """
    key = filter_name.lower()
    if key not in _FILTER_MAP:
        raise ValueError(f"Unsupported filter: {filter_name}")

    img = _open_image(src)
    filtered = _FILTER_MAP[key](img)
    logger.debug("Applied filter %s to %s", filter_name, src)
    _save_image(filtered, dst)


def batch_process(
    input_dir: Path,
    output_dir: Path,
    pipeline: Sequence[Callable[[Path, Path], None]],
    recurse: bool = False,
    allowed_exts: Tuple[str, ...] = ALLOWED_INPUT_EXTS,
) -> List[Tuple[Path, str]]:
    """
    Apply a sequence of processing functions to all images in a directory.

    Each callable in ``pipeline`` must accept ``src`` and ``dst`` arguments
    (both :class:`pathlib.Path`). The function creates a temporary intermediate
    file for each stage, and finally writes the result to ``output_dir``
    preserving the original relative path.

    Parameters
    ----------
    input_dir :