from PIL import Image, ImageFilter
from pathlib import Path
from typing import List, Tuple, Optional
import argparse
import logging
import os
import sys

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    Class for processing images: resizing, format conversion, and filter application.
    """

    SUPPORTED_FORMATS: Tuple[str] = ("JPEG", "PNG", "WebP")
    SUPPORTED_FILTERS: Tuple[str] = ("blur", "sharpen", "edge_detection")

    def __init__(self, output_dir: Path):
        """
        Initialize ImageProcessor with output directory.

        :param output_dir: Directory where processed images will be saved.
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _check_format(self, format: str) -> None:
        """
        Validate image format.

        :param format: Image format to check.
        :raises ValueError: If format is not supported.
        """
        if format.upper() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format. Supported formats: {self.SUPPORTED_FORMATS}")

    def _check_filter(self, filter: str) -> None:
        """
        Validate filter name.

        :param filter: Filter to check.
        :raises ValueError: If filter is not supported.
        """
        if filter not in self.SUPPORTED_FILTERS:
            raise ValueError(f"Unsupported filter. Supported filters: {self.SUPPORTED_FILTERS}")

    def resize(self, image_path: Path, size: Tuple[int, int], output_format: str = "JPEG") -> None:
        """
        Resize an image and save with specified format.

        :param image_path: Path to the input image.
        :param size: New size (width, height).
        :param output_format: Output image format (default: JPEG).
        :raises FileNotFoundError: If input image not found.
        :raises Exception: On any I/O error.
        """
        try:
            self._check_format(output_format)
            with Image.open(image_path) as img:
                img = img.resize(size)
                output_path = self.output_dir / f"{Path(image_path).stem}_resized.{output_format.lower()}"
                img.save(output_path, optimize=True, quality=90)
                logger.info(f"Resized image saved to: {output_path}")
        except FileNotFoundError:
            logger.error(f"Image not found: {image_path}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error resizing {image_path}: {e}", exc_info=True)
            raise

    def convert_format(self, image_path: Path, output_format: str) -> None:
        """
        Convert image format.

        :param image_path: Path to the input image.
        :param output_format: Desired output format.
        :raises FileNotFoundError: If input image not found.
        :raises Exception: On any I/O error.
        """
        try:
            self._check_format(output_format)
            with Image.open(image_path) as img:
                output_path = self.output_dir / f"{Path(image_path).stem}.{output_format.lower()}"
                img.save(output_path, optimize=True, quality=90)
                logger.info(f"Format converted image saved to: {output_path}")
        except FileNotFoundError:
            logger.error(f"Image not found: {image_path}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error converting {image_path}: {e}", exc_info=True)
            raise

    def apply_filter(self, image_path: Path, filter: str) -> None:
        """
        Apply a filter to an image.

        :param image_path: Path to the input image.
        :param filter: Name of the filter to apply.
        :raises FileNotFoundError: If input image not found.
        :raises Exception: On any I/O error.
        """
        try:
            self._check_filter(filter)
            with Image.open(image_path) as img:
                if filter == "blur":
                    filtered_img = img.filter(ImageFilter.BLUR)
                elif filter == "sharpen":
                    filtered_img = img.filter(ImageFilter.SHARPEN)
                elif filter == "edge_detection":
                    filtered_img = img.filter(ImageFilter.FIND_EDGES)
                else:
                    raise ValueError("Invalid filter specified internally")
                
                output_path = self.output_dir / f"{Path(image_path).stem}_{filter}.jpg"
                filtered_img.save(output_path, optimize=True, quality=90)
                logger.info(f"Filtered image saved to: {output_path}")
        except FileNotFoundError:
            logger.error(f"Image not found: {image_path}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error applying filter to {image_path}: {e}", exc_info=True)
            raise

    def batch_process(self, images: List[Path], size: Optional[Tuple[int, int]] = None, output_format: Optional[str] = None, filter: Optional[str] = None) -> None:
        """
        Batch process multiple images.

        :param images: List of image paths.
        :param size: Resize size if applicable (default: None).
        :param output_format: Format to convert to if applicable (default: None).
        :param filter: Filter to apply if applicable (default: None).
        """
        for image_path in images:
            if size:
                self.resize(image_path, size, output_format or "JPEG")
            if output_format and not size:
                self.convert_format(image_path, output_format)
            if filter:
                self.apply_filter(image_path, filter)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Processor")
    parser.add_argument("-i", "--input", nargs="+", type=Path, help="Input image(s) or directory")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("./processed"), help="Output directory")
    parser.add_argument("-s", "--size", nargs=2, type=int, help="Resize size (W H)")
    parser.add_argument("-f", "--format", choices=ImageProcessor.SUPPORTED_FORMATS, help="Output format")
    parser.add_argument("--filter", choices=ImageProcessor.SUPPORTED_FILTERS, help="Filter to apply")
    args = parser.parse_args()

    processor = ImageProcessor(args.output_dir)

    images: List[Path] = []
    if args.input:
        for item in args.input:
            if item.is_dir():
                images.extend(item.glob("*.jpg") + item.glob("*.png") + item.glob("*.webp"))
            elif item.is_file() and item.suffix.lower() in (".jpg", ".png", ".webp"):
                images.append(item)
            else:
                logger.warning(f"Skipping non-image file or non-directory: {item}")

    if not images:
        logger.error("No valid images provided or found in specified directories.")
        sys.exit(1)

    processor.batch_process(images, args.size, args.format, args.filter)