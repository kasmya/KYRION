import os
from typing import List, Tuple
from PIL import Image, ImageFilter, ImageOps
from PIL.Image import Resampling
from PIL.ExifTags import TAGS
from enum import Enum
import logging
from logging.handlers import RotatingFileHandler
import argparse

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('image_processor.log', maxBytes=1000000, backupCount=1)
logger.addHandler(handler)

class Format(Enum):
    """Supported image formats."""
    JPEG = 'jpeg'
    PNG = 'png'
    WEBP = 'webp'

class Filter(Enum):
    """Supported image filters."""
    BLUR = 'blur'
    SHARPEN = 'sharpen'
    EDGE_DETECTION = 'edge_detection'

def load_image(image_path: str) -> Image:
    """Load an image from a file path."""
    try:
        with Image.open(image_path) as img:
            return img
    except FileNotFoundError:
        logger.error(f"Image file not found: {image_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading image: {image_path} - {str(e)}")
        raise

def save_image(image: Image, output_path: str, format: Format) -> None:
    """Save an image to a file path with the specified format."""
    try:
        image.save(output_path, format=format.value)
    except Exception as e:
        logger.error(f"Error saving image: {output_path} - {str(e)}")
        raise

def resize_image(image: Image, size: Tuple[int, int]) -> Image:
    """Resize an image to the specified size."""
    return image.resize(size, resample=Resampling.LANCZOS)

def apply_filter(image: Image, filter: Filter) -> Image:
    """Apply a filter to an image."""
    if filter == Filter.BLUR:
        return image.filter(ImageFilter.GaussianBlur(radius=2))
    elif filter == Filter.SHARPEN:
        return image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    elif filter == Filter.EDGE_DETECTION:
        return ImageOps.grayscale(image).filter(ImageFilter.Kernel(
            size=(3, 3),
            kernel=(
                -1, -1, -1,
                -1,  8, -1,
                -1, -1, -1
            ),
            scale=1,
            offset=128
        ))

def process_image(image_path: str, output_path: str, size: Tuple[int, int], format: Format, filters: List[Filter]) -> None:
    """Process an image by resizing, converting format, and applying filters."""
    image = load_image(image_path)
    image = resize_image(image, size)
    for filter in filters:
        image = apply_filter(image, filter)
    save_image(image, output_path, format)

def main() -> None:
    parser = argparse.ArgumentParser(description='Image processor')
    parser.add_argument('--input', required=True, help='Input image file or directory')
    parser.add_argument('--output', required=True, help='Output image file or directory')
    parser.add_argument('--size', nargs=2, type=int, required=True, help='Output image size (width height)')
    parser.add_argument('--format', choices=[f.value for f in Format], default=Format.JPEG.value, help='Output image format')
    parser.add_argument('--filters', nargs='+', choices=[f.value for f in Filter], help='Filters to apply (blur, sharpen, edge_detection)')
    args = parser.parse_args()

    format = Format(args.format)
    filters = [Filter(f) for f in args.filters] if args.filters else []

    if os.path.isdir(args.input):
        for file in os.listdir(args.input):
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                input_path = os.path.join(args.input, file)
                output_path = os.path.join(args.output, file)
                if format == Format.JPEG:
                    output_path = output_path.replace('.png', '.jpg').replace('.webp', '.jpg')
                elif format == Format.PNG:
                    output_path = output_path.replace('.jpg', '.png').replace('.webp', '.png')
                elif format == Format.WEBP:
                    output_path = output_path.replace('.jpg', '.webp').replace('.png', '.webp')
                process_image(input_path, output_path, tuple(args.size), format, filters)
    else:
        process_image(args.input, args.output, tuple(args.size), format, filters)

if __name__ == '__main__':
    main()