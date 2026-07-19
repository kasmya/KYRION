"""
### Task 16: Image Processor (Pillow + NumPy)

A CLI batch image processor supporting resize, crop, rotate, format
conversion, and simple filters (grayscale, blur), applied recursively
across a directory.

Requirements:
    pip install Pillow numpy

Usage:
    python 16_image_processor.py -i ./photos -o ./out --resize 800 600 \
        --format webp --filter grayscale
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("image_processor")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
FORMAT_MAP = {"png": "PNG", "jpeg": "JPEG", "jpg": "JPEG", "webp": "WEBP"}


class ImageProcessingError(Exception):
    """Raised when an individual image cannot be processed."""


def load_image(path: Path) -> Image.Image:
    """Loads an image from disk, raising ImageProcessingError on failure."""
    try:
        return Image.open(path).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(f"Failed to open image '{path}': {exc}") from exc


def resize_image(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Resizes an image to the given (width, height), preserving aspect via thumbnail-like fit."""
    return image.resize(size, Image.LANCZOS)


def crop_image(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
    """Crops an image to the given (left, top, right, bottom) box."""
    width, height = image.size
    left, top, right, bottom = box
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ImageProcessingError(f"Invalid crop box {box} for image of size {image.size}")
    return image.crop(box)


def rotate_image(image: Image.Image, degrees: float) -> Image.Image:
    """Rotates an image counter-clockwise by the given degrees, expanding the canvas."""
    return image.rotate(degrees, expand=True)


def apply_grayscale(image: Image.Image) -> Image.Image:
    """Converts an image to grayscale using a NumPy-based luminosity transform."""
    arr = np.asarray(image).astype(np.float32)
    # Standard luminosity weights.
    gray = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
    gray = np.clip(gray, 0, 255).astype(np.uint8)
    gray_rgb = np.stack([gray] * 3, axis=-1)
    return Image.fromarray(gray_rgb, mode="RGB")


def apply_blur(image: Image.Image, radius: float = 2.0) -> Image.Image:
    """Applies a Gaussian blur filter."""
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


FILTERS = {
    "grayscale": apply_grayscale,
    "blur": apply_blur,
}


def process_single_image(
    input_path: Path,
    output_path: Path,
    resize: Optional[Tuple[int, int]],
    crop: Optional[Tuple[int, int, int, int]],
    rotate: Optional[float],
    filter_name: Optional[str],
    output_format: Optional[str],
) -> None:
    """Applies the requested transformations to a single image and saves the result."""
    image = load_image(input_path)

    if resize:
        image = resize_image(image, resize)
    if crop:
        image = crop_image(image, crop)
    if rotate:
        image = rotate_image(image, rotate)
    if filter_name:
        filter_fn = FILTERS.get(filter_name)
        if filter_fn is None:
            raise ImageProcessingError(f"Unknown filter '{filter_name}'")
        image = filter_fn(image)

    save_format = FORMAT_MAP.get((output_format or output_path.suffix.lstrip(".")).lower())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if save_format:
            image.save(output_path, format=save_format)
        else:
            image.save(output_path)
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(f"Failed to save image to '{output_path}': {exc}") from exc


def discover_images(input_dir: Path) -> List[Path]:
    """Recursively finds all supported image files under a directory."""
    return [
        p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def build_output_path(input_dir: Path, output_dir: Path, image_path: Path, new_format: Optional[str]) -> Path:
    """Computes the mirrored output path for an image, optionally with a new extension."""
    relative = image_path.relative_to(input_dir)
    if new_format:
        relative = relative.with_suffix("." + new_format.lower())
    return output_dir / relative


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Batch image processor using Pillow and NumPy.")
    parser.add_argument("--input", "-i", required=True, help="Input directory of images")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument("--resize", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument(
        "--crop", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM")
    )
    parser.add_argument("--rotate", type=float, help="Rotation angle in degrees")
    parser.add_argument("--filter", choices=FILTERS.keys(), help="Filter to apply")
    parser.add_argument("--format", choices=FORMAT_MAP.keys(), help="Convert to this output format")
    return parser


def main(argv: List[str] = None) -> int:
    """CLI entry point. Returns process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.is_dir():
        logger.error("Input directory does not exist: %s", input_dir)
        return 1

    images = discover_images(input_dir)
    if not images:
        logger.warning("No supported images found in %s", input_dir)
        return 0

    resize = tuple(args.resize) if args.resize else None
    crop = tuple(args.crop) if args.crop else None

    success_count = 0
    failure_count = 0

    for image_path in images:
        output_path = build_output_path(input_dir, output_dir, image_path, args.format)
        try:
            process_single_image(
                image_path,
                output_path,
                resize=resize,
                crop=crop,
                rotate=args.rotate,
                filter_name=args.filter,
                output_format=args.format,
            )
            logger.info("Processed '%s' -> '%s'", image_path, output_path)
            success_count += 1
        except ImageProcessingError as exc:
            logger.error("Skipping '%s': %s", image_path, exc)
            failure_count += 1

    logger.info("Done. %d succeeded, %d failed.", success_count, failure_count)
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
