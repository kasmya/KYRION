from PIL import Image, ImageFilter
from typing import List, Tuple
import os
import logging

# Set up logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def resize_image(image_path: str, output_path: str, size: Tuple[int, int]) -> None:
    """
    Resize an image to a specified size.

    Args:
    - image_path (str): The path to the input image.
    - output_path (str): The path to save the resized image.
    - size (Tuple[int, int]): The desired size (width, height) of the resized image.
    """
    try:
        with Image.open(image_path) as img:
            img = img.resize(size)
            img.save(output_path)
            logger.info(f"Resized image saved to {output_path}")
    except OSError as e:
        logger.error(f"Error resizing image: {e}")

def convert_image_format(image_path: str, output_path: str, format: str) -> None:
    """
    Convert an image to a different format.

    Args:
    - image_path (str): The path to the input image.
    - output_path (str): The path to save the converted image.
    - format (str): The desired format of the converted image (e.g., "JPEG", "PNG", "WebP").
    """
    try:
        with Image.open(image_path) as img:
            img.save(output_path, format=format)
            logger.info(f"Converted image saved to {output_path}")
    except OSError as e:
        logger.error(f"Error converting image format: {e}")

def apply_filter(image_path: str, output_path: str, filter_name: str) -> None:
    """
    Apply a filter to an image.

    Args:
    - image_path (str): The path to the input image.
    - output_path (str): The path to save the filtered image.
    - filter_name (str): The name of the filter to apply (e.g., "BLUR", "SHARPEN", "EDGE_ENHANCE").
    """
    try:
        with Image.open(image_path) as img:
            if filter_name == "BLUR":
                img = img.filter(ImageFilter.GaussianBlur(radius=2))
            elif filter_name == "SHARPEN":
                img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
            elif filter_name == "EDGE_ENHANCE":
                img = img.filter(ImageFilter.EDGE_ENHANCE)
            else:
                logger.error(f"Invalid filter name: {filter_name}")
                return
            img.save(output_path)
            logger.info(f"Filtered image saved to {output_path}")
    except OSError as e:
        logger.error(f"Error applying filter: {e}")

def batch_process_images(image_paths: List[str], output_dir: str, resize_size: Tuple[int, int] = None, convert_format: str = None, filter_name: str = None) -> None:
    """
    Batch process multiple images.

    Args:
    - image_paths (List[str]): A list of paths to the input images.
    - output_dir (str): The directory to save the processed images.
    - resize_size (Tuple[int, int]): The desired size (width, height) for resizing images. Defaults to None.
    - convert_format (str): The desired format for converting images. Defaults to None.
    - filter_name (str): The name of the filter to apply to images. Defaults to None.
    """
    for image_path in image_paths:
        filename, file_extension = os.path.splitext(os.path.basename(image_path))
        output_path = os.path.join(output_dir, f"{filename}_processed{file_extension}")
        if resize_size:
            resize_image(image_path, output_path, resize_size)
        if convert_format:
            convert_image_format(image_path, output_path, convert_format)
        if filter_name:
            apply_filter(image_path, output_path, filter_name)

# Example usage:
if __name__ == "__main__":
    image_paths = ["image1.jpg", "image2.png", "image3.webp"]
    output_dir = "processed_images"
    batch_process_images(image_paths, output_dir, resize_size=(800, 600), convert_format="JPEG", filter_name="BLUR")