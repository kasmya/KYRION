"""
Image Processor module for resizing, format conversion, and applying filters.

Supports JPEG, PNG, and WebP formats. Filters: blur, sharpen, edge detection.
Batch processing with security checks for file paths and extensions.
Uses Pillow (PIL) exclusively.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union
from enum import Enum

from PIL import Image, ImageFilter, UnidentifiedImageError


class ImageFormat(Enum):
    """Supported output image formats."""
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


class FilterType(Enum):
    """Available image filters."""
    BLUR = "blur"
    SHARPEN = "sharpen"
    EDGE_DETECTION = "edge_detection"


# Mapping from filter type to PIL ImageFilter constant
_FILTER_MAP = {
    FilterType.BLUR: ImageFilter.BLUR,
    FilterType.SHARPEN: ImageFilter.SHARPEN,
    FilterType.EDGE_DETECTION: ImageFilter.FIND_EDGES,
}

# Valid input image extensions (lowercase)
_VALID_INPUT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ImageProcessorError(Exception):
    """Custom exception for image processing errors."""
    pass


class ImageProcessor:
    """
    Provides image processing operations: resize, convert, filter, and batch processing.
    """

    def __init__(self) -> None:
        """Initialize the processor (no state needed)."""
        pass

    # ------------------------------------------------------------------
    # Public high-level methods
    # ------------------------------------------------------------------

    def resize(
        self,
        image: Image.Image,
        size: Tuple[int, int],
        keep_aspect: bool = True,
        resample: int = Image.LANCZOS,
    ) -> Image.Image:
        """
        Resize an image to the specified dimensions.

        Args:
            image: PIL Image object.
            size: Desired (width, height) tuple.
            keep_aspect: If True, resize keeping aspect ratio; the image is padded to the exact size.
            resample: Resampling filter (default LANCZOS for high quality).

        Returns:
            Resized PIL Image.

        Raises:
            ImageProcessorError: If size is invalid.
        """
        self._validate_size(size)

        if keep_aspect:
            return self._resize_keep_aspect(image, size, resample)
        else:
            return image.resize(size, resample)

    def convert_format(
        self,
        image: Image.Image,
        output_format: Union[str, ImageFormat],
        output_path: Union[str, Path],
        quality: Optional[int] = None,
    ) -> Path:
        """
        Convert image to a different format and save to disk.

        Args:
            image: PIL Image object.
            output_format: Target format as string (e.g., "JPEG") or ImageFormat enum.
            output_path: Path to save the converted image.
            quality: Quality for lossy formats (JPEG/WebP). If None, use Pillow default.

        Returns:
            Path to the saved file.

        Raises:
            ImageProcessorError: If format is unsupported or save fails.
        """
        fmt = self._resolve_format(output_format)
        output_path = Path(output_path).resolve()

        # Convert RGBA to RGB for JPEG (JPEG does not support alpha)
        if fmt == ImageFormat.JPEG and image.mode == "RGBA":
            image = image.convert("RGB")

        save_kwargs = {"format": fmt.value}
        if quality is not None:
            save_kwargs["quality"] = quality

        try:
            image.save(str(output_path), **save_kwargs)
        except (OSError, ValueError) as e:
            raise ImageProcessorError(f"Failed to save image to {output_path}: {e}")

        return output_path

    def apply_filter(
        self,
        image: Image.Image,
        filter_type: Union[str, FilterType],
    ) -> Image.Image:
        """
        Apply a predefined filter to the image.

        Args:
            image: PIL Image object.
            filter_type: Filter name as string (case-insensitive) or FilterType enum.

        Returns:
            Filtered PIL Image.

        Raises:
            ImageProcessorError: If filter type is unknown.
        """
        ft = self._resolve_filter(filter_type)
        pil_filter = _FILTER_MAP.get(ft)
        if pil_filter is None:
            raise ImageProcessorError(f"Unsupported filter: {filter_type}")

        return image.filter(pil_filter)

    def process_batch(
        self,
        input_dir: Union[str, Path],
        output_dir: Union[str, Path],
        output_format: Union[str, ImageFormat] = "JPEG",
        resize_to: Optional[Tuple[int, int]] = None,
        filter_type: Optional[Union[str, FilterType]] = None,
        quality: Optional[int] = None,
        output_prefix: str = "",
    ) -> List[Path]:
        """
        Process all valid images in a directory with the same operations.

        Supported input formats: .jpg, .jpeg, .png, .webp.

        Args:
            input_dir: Directory containing input images.
            output_dir: Directory to save processed images.
            output_format: Output image format.
            resize_to: Optional (width, height) tuple to resize all images.
            filter_type: Optional filter to apply.
            quality: Quality for lossy formats.
            output_prefix: Optional prefix for output filenames.

        Returns:
            List of output file paths.

        Raises:
            ImageProcessorError: If directories are invalid or processing fails.
        """
        in_dir = Path(input_dir).expanduser().resolve()
        out_dir = Path(output_dir).expanduser().resolve()

        if not in_dir.is_dir():
            raise ImageProcessorError(f"Input directory does not exist: {in_dir}")
        out_dir.mkdir(parents=True, exist_ok=True)

        # Gather valid image files
        image_files = [
            f for f in in_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _VALID_INPUT_EXTENSIONS
        ]

        if not image_files:
            raise ImageProcessorError(f"No valid image files found in {in_dir}")

        results: List[Path] = []

        for img_path in image_files:
            try:
                pil_image = self.load_image(img_path)
            except ImageProcessorError as e:
                # Log and skip problematic files
                print(f"Skipping {img_path}: {e}", file=sys.stderr)
                continue

            # Apply resize if requested
            if resize_to is not None:
                pil_image = self.resize(pil_image, resize_to)

            # Apply filter if requested
            if filter_type is not None:
                pil_image = self.apply_filter(pil_image, filter_type)

            # Build output path
            out_name = f"{output_prefix}{img_path.stem}.{self._ext_for_format(output_format)}"
            out_path = out_dir / out_name

            try:
                self.convert_format(pil_image, output_format, out_path, quality)
                results.append(out_path)
            except ImageProcessorError as e:
                print(f"Error saving {out_path}: {e}", file=sys.stderr)

        return results

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def load_image(path: Union[str, Path]) -> Image.Image:
        """
        Load an image from disk.

        Args:
            path: Path to image file.

        Returns:
            PIL Image object.

        Raises:
            ImageProcessorError: If file does not exist or cannot be opened.
        """
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise ImageProcessorError(f"File not found: {path}")
        try:
            return Image.open(str(path)).copy()  # copy to force loading
        except (UnidentifiedImageError, OSError) as e:
            raise ImageProcessorError(f"Cannot open image at {path}: {e}")

    @staticmethod
    def _validate_size(size: Tuple[int, int]) -> None:
        """Check that size tuple contains positive integers."""
        if not (isinstance(size, tuple) and len(size) == 2):
            raise ImageProcessorError("Size must be a tuple of (width, height)")
        w, h = size
        if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0):
            raise ImageProcessorError("Width and height must be positive integers")

    @staticmethod
    def _resize_keep_aspect(
        image: Image.Image,
        target_size: Tuple[int, int],
        resample: int,
    ) -> Image.Image:
        """Resize image to fit inside target_size, padding if needed to reach exact size."""
        target_w, target_h = target_size
        # Calculate aspect ratio preserving resize
        image.thumbnail((target_w, target_h), resample)
        # Create new canvas and paste centered
        new_img = Image.new("RGBA" if image.mode == "RGBA" else "RGB", target_size, (255, 255, 255, 0))
        paste_x = (target_w - image.width) // 2
        paste_y = (target_h - image.height) // 2
        new_img.paste(image, (paste_x, paste_y))
        return new_img

    @staticmethod
    def _resolve_format(fmt: Union[str, ImageFormat]) -> ImageFormat:
        """Convert string to ImageFormat enum, with validation."""
        if isinstance(fmt, ImageFormat):
            return fmt
        if not isinstance(fmt, str):
            raise ImageProcessorError(f"Invalid format type: {type(fmt)}")

        upper = fmt.upper()
        for member in ImageFormat:
            if member.value == upper:
                return member
        raise ImageProcessorError(f"Unsupported format: {fmt}. Supported: JPEG, PNG, WebP")

    @staticmethod
    def _resolve_filter(ft: Union[str, FilterType]) -> FilterType:
        """Convert string to FilterType enum, case-insensitive."""
        if isinstance(ft, FilterType):
            return ft
        if not isinstance(ft, str):
            raise ImageProcessorError(f"Invalid filter type: {type(ft)}")

        lower = ft.lower()
        for member in FilterType:
            if member.value == lower:
                return member
        raise ImageProcessorError(
            f"Unknown filter: {ft}. Available: {', '.join(f.value for f in FilterType)}"
        )

    @staticmethod
    def _ext_for_format(fmt: Union[str, ImageFormat]) -> str:
        """Return file extension (without dot) for a given format."""
        resolved = ImageProcessor._resolve_format(fmt)
        # WebP uses .webp, others use lowercase of format name
        if resolved == ImageFormat.WEBP:
            return "webp"
        return resolved.value.lower()  # jpeg, png


# ======================================================================
# Example usage (if run as script)
# ======================================================================
if __name__ == "__main__":
    # Simple demonstration – can be removed in production
    processor = ImageProcessor()
    try:
        # Load an image (provide a valid path for testing)
        img = processor.load_image("test.jpg")  # Change to your actual image
    except ImageProcessorError as e:
        print(f"Load error: {e}")
        sys.exit(1)

    # Resize
    resized = processor.resize(img, (200, 200), keep_aspect=True)
    # Apply filter
    filtered = processor.apply_filter(resized, FilterType.SHARPEN)
    # Save as PNG
    processor.convert_format(filtered, "PNG", "output_sharpened.png")

    # Batch convert all images in a directory
    # processor.process_batch(
    #     input_dir="images/",
    #     output_dir="processed/",
    #     output_format="WEBP",
    #     resize_to=(800, 600),
    #     filter_type="sharpen",
    #     quality=90
    # )