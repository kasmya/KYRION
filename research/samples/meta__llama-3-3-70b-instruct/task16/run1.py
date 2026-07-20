from PIL import Image, ImageFilter
from typing import List, Tuple
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def resize_image(image_path: str, output_path: str, size: Tuple[int, int]) -> None:
    """
    Resizes an image to the specified size.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to the output image.
    - size (Tuple[int, int]): The new size of the image.

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - PermissionError: If there is no permission to write to the output path.
    """
    try:
        with Image.open(image_path) as img:
            img = img.resize(size)
            img.save(output_path)
            logger.info(f"Resized {image_path} to {output_path}")
    except FileNotFoundError:
        logger.error(f"File not found: {image_path}")
    except PermissionError:
        logger.error(f"No permission to write to {output_path}")

def convert_image(image_path: str, output_path: str, format: str) -> None:
    """
    Converts an image to the specified format.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to the output image.
    - format (str): The new format of the image (e.g. 'JPEG', 'PNG', 'WebP').

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - PermissionError: If there is no permission to write to the output path.
    """
    try:
        with Image.open(image_path) as img:
            img.save(output_path, format=format.upper())
            logger.info(f"Converted {image_path} to {output_path}")
    except FileNotFoundError:
        logger.error(f"File not found: {image_path}")
    except PermissionError:
        logger.error(f"No permission to write to {output_path}")

def apply_filter(image_path: str, output_path: str, filter_name: str) -> None:
    """
    Applies a filter to an image.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to the output image.
    - filter_name (str): The name of the filter to apply (e.g. 'BLUR', 'SHARPEN', 'EDGE_ENHANCE').

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - PermissionError: If there is no permission to write to the output path.
    - ValueError: If the filter name is not recognized.
    """
    filters = {
        'BLUR': ImageFilter.BLUR,
        'SHARPEN': ImageFilter.SHARPEN,
        'EDGE_ENHANCE': ImageFilter.EDGE_ENHANCE
    }
    try:
        with Image.open(image_path) as img:
            if filter_name.upper() in filters:
                img = img.filter(filters[filter_name.upper()])
                img.save(output_path)
                logger.info(f"Applied {filter_name} filter to {image_path}")
            else:
                raise ValueError(f"Unrecognized filter: {filter_name}")
    except FileNotFoundError:
        logger.error(f"File not found: {image_path}")
    except PermissionError:
        logger.error(f"No permission to write to {output_path}")

def batch_process_images(input_paths: List[str], output_paths: List[str], operations: List[str]) -> None:
    """
    Batch processes multiple images.

    Args:
    - input_paths (List[str]): Paths to the input images.
    - output_paths (List[str]): Paths to the output images.
    - operations (List[str]): List of operations to apply to each image (e.g. 'RESIZE', 'CONVERT', 'FILTER').

    Raises:
    - ValueError: If the number of input paths does not match the number of output paths.
    """
    if len(input_paths) != len(output_paths):
        raise ValueError("Number of input paths does not match number of output paths")

    for input_path, output_path in zip(input_paths, output_paths):
        for operation in operations:
            if operation.upper() == 'RESIZE':
                resize_image(input_path, output_path, (800, 600))  # default size
            elif operation.upper() == 'CONVERT':
                convert_image(input_path, output_path, 'JPEG')  # default format
            elif operation.upper() == 'FILTER':
                apply_filter(input_path, output_path, 'BLUR')  # default filter

def main() -> None:
    input_paths = ['image1.jpg', 'image2.png', 'image3.webp']
    output_paths = ['output1.jpg', 'output2.png', 'output3.webp']
    operations = ['RESIZE', 'CONVERT', 'FILTER']
    batch_process_images(input_paths, output_paths, operations)

if __name__ == "__main__":
    main()