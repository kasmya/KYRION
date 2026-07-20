from PIL import Image, ImageFilter, ImageEnhance
from typing import List, Optional
from pathlib import Path
import os

def resize_image(image_path: str, output_path: str, size: tuple) -> None:
    """
    Resize an image.

    Args:
    image_path (str): Path to the input image.
    output_path (str): Path to the output image.
    size (tuple): New size of the image (width, height).
    """
    try:
        with Image.open(image_path) as img:
            img.thumbnail(size)
            img.save(output_path)
    except FileNotFoundError:
        print(f"Error: File '{image_path}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

def convert_format(image_path: str, output_path: str, format: str) -> None:
    """
    Convert the format of an image.

    Args:
    image_path (str): Path to the input image.
    output_path (str): Path to the output image.
    format (str): New format of the image (e.g., 'JPEG', 'PNG', 'WebP').
    """
    try:
        with Image.open(image_path) as img:
            img.save(output_path, format=format.upper())
    except FileNotFoundError:
        print(f"Error: File '{image_path}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

def apply_filter(image_path: str, output_path: str, filter_name: str) -> None:
    """
    Apply a filter to an image.

    Args:
    image_path (str): Path to the input image.
    output_path (str): Path to the output image.
    filter_name (str): Name of the filter to apply (e.g., 'BLUR', 'SHARPEN', 'EDGE_ENHANCE').
    """
    try:
        with Image.open(image_path) as img:
            if filter_name.upper() == 'BLUR':
                img = img.filter(ImageFilter.GaussianBlur(radius=2))
            elif filter_name.upper() == 'SHARPEN':
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(2.0)
            elif filter_name.upper() == 'EDGE_ENHANCE':
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(1.5)
            img.save(output_path)
    except FileNotFoundError:
        print(f"Error: File '{image_path}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

def batch_process(images: List[str], output_dir: str, size: Optional[tuple] = None, format: Optional[str] = None, filter_name: Optional[str] = None) -> None:
    """
    Batch process multiple images.

    Args:
    images (List[str]): List of paths to the input images.
    output_dir (str): Directory to save the output images.
    size (Optional[tuple]): New size of the images (width, height). Defaults to None.
    format (Optional[str]): New format of the images (e.g., 'JPEG', 'PNG', 'WebP'). Defaults to None.
    filter_name (Optional[str]): Name of the filter to apply (e.g., 'BLUR', 'SHARPEN', 'EDGE_ENHANCE'). Defaults to None.
    """
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for image_path in images:
            filename = Path(image_path).stem
            if size:
                output_path = output_dir / f"{filename}_resized.{Path(image_path).suffix}"
                resize_image(image_path, output_path, size)
            if format:
                output_path = output_dir / f"{filename}.{format.lower()}"
                convert_format(image_path, output_path, format)
            if filter_name:
                output_path = output_dir / f"{filename}_{filter_name.lower()}.{Path(image_path).suffix}"
                apply_filter(image_path, output_path, filter_name)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    images = ["image1.jpg", "image2.png", "image3.webp"]
    output_dir = "output"
    batch_process(images, output_dir, size=(800, 600), format="JPEG", filter_name="BLUR")