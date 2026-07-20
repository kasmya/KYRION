import os
import argparse
from typing import List
from PIL import Image, ImageFilter
from PIL.Image import Image as PILImage
import cv2
from skimage import io, filters
import numpy as np

def resize_image(image_path: str, output_path: str, size: tuple) -> None:
    """
    Resizes an image.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to save the resized image.
    - size (tuple): New size of the image.

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - IOError: If the output image cannot be saved.
    """
    try:
        with Image.open(image_path) as img:
            img = img.resize(size)
            img.save(output_path)
    except FileNotFoundError:
        print(f"Error: Input image '{image_path}' does not exist.")
    except IOError as e:
        print(f"Error: Unable to save output image '{output_path}': {e}")

def convert_format(image_path: str, output_path: str, format: str) -> None:
    """
    Converts an image to a different format.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to save the converted image.
    - format (str): New format of the image (e.g., 'jpeg', 'png', 'webp').

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - IOError: If the output image cannot be saved.
    """
    try:
        with Image.open(image_path) as img:
            img.save(output_path, format=format)
    except FileNotFoundError:
        print(f"Error: Input image '{image_path}' does not exist.")
    except IOError as e:
        print(f"Error: Unable to save output image '{output_path}': {e}")

def apply_filter(image_path: str, output_path: str, filter_name: str) -> None:
    """
    Applies a filter to an image.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to save the filtered image.
    - filter_name (str): Name of the filter to apply (e.g., 'blur', 'sharpen', 'edge').

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - IOError: If the output image cannot be saved.
    - ValueError: If the filter name is invalid.
    """
    try:
        with Image.open(image_path) as img:
            if filter_name == 'blur':
                img = img.filter(ImageFilter.GaussianBlur(radius=2))
            elif filter_name == 'sharpen':
                img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
            elif filter_name == 'edge':
                img = img.convert('L')
                img = img.filter(ImageFilter.Kernel(
                    (3, 3),
                    (-1, -1, -1,
                     -1, 8, -1,
                     -1, -1, -1),
                    1,
                    0
                ))
            else:
                raise ValueError("Invalid filter name")
            img.save(output_path)
    except FileNotFoundError:
        print(f"Error: Input image '{image_path}' does not exist.")
    except IOError as e:
        print(f"Error: Unable to save output image '{output_path}': {e}")
    except ValueError as e:
        print(f"Error: {e}")

def edge_detection_opencv(image_path: str, output_path: str) -> None:
    """
    Applies edge detection to an image using OpenCV.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to save the edge-detected image.

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - IOError: If the output image cannot be saved.
    """
    try:
        img = cv2.imread(image_path)
        edges = cv2.Canny(img, 100, 200)
        cv2.imwrite(output_path, edges)
    except FileNotFoundError:
        print(f"Error: Input image '{image_path}' does not exist.")
    except IOError as e:
        print(f"Error: Unable to save output image '{output_path}': {e}")

def edge_detection_skimage(image_path: str, output_path: str) -> None:
    """
    Applies edge detection to an image using scikit-image.

    Args:
    - image_path (str): Path to the input image.
    - output_path (str): Path to save the edge-detected image.

    Raises:
    - FileNotFoundError: If the input image does not exist.
    - IOError: If the output image cannot be saved.
    """
    try:
        img = io.imread(image_path, as_gray=True)
        edges = filters.sobel(img)
        io.imsave(output_path, edges.astype(np.uint8))
    except FileNotFoundError:
        print(f"Error: Input image '{image_path}' does not exist.")
    except IOError as e:
        print(f"Error: Unable to save output image '{output_path}': {e}")

def batch_process(input_dir: str, output_dir: str, func, *args) -> None:
    """
    Batch processes images in a directory.

    Args:
    - input_dir (str): Path to the input directory.
    - output_dir (str): Path to the output directory.
    - func: Function to apply to each image.
    - *args: Arguments to pass to the function.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for filename in os.listdir(input_dir):
        if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            image_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            func(image_path, output_path, *args)

def main() -> None:
    parser = argparse.ArgumentParser(description='Image Processor')
    parser.add_argument('-i', '--input', help='Input directory')
    parser.add_argument('-o', '--output', help='Output directory')
    parser.add_argument('-r', '--resize', nargs=2, type=int, help='Resize image')
    parser.add_argument('-f', '--format', help='Convert image format')
    parser.add_argument('-b', '--filter', help='Apply filter to image')
    parser.add_argument('-e', '--edge', action='store_true', help='Apply edge detection')
    args = parser.parse_args()

    if args.resize:
        batch_process(args.input, args.output, resize_image, args.resize)
    elif args.format:
        batch_process(args.input, args.output, convert_format, args.format)
    elif args.filter:
        batch_process(args.input, args.output, apply_filter, args.filter)
    elif args.edge:
        batch_process(args.input, args.output, edge_detection_skimage)

if __name__ == '__main__':
    main()