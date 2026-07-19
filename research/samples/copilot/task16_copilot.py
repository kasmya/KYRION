"""
Image Processor using Pillow and NumPy.
Features:
- Resize, crop, rotate images
- Convert formats (PNG, JPEG, WebP)
- Apply filters (grayscale, blur)
- Batch processing of directory
- CLI with argparse
"""

import argparse
import os
from PIL import Image, ImageFilter
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)


def process_image(file: str, output: str, action: str):
    try:
        img = Image.open(file)
        if action == "resize":
            img = img.resize((256, 256))
        elif action == "crop":
            img = img.crop((0, 0, 128, 128))
        elif action == "rotate":
            img = img.rotate(90)
        elif action == "grayscale":
            img = img.convert("L")
        elif action == "blur":
            img = img.filter(ImageFilter.BLUR)
        img.save(output)
        logging.info(f"Processed {file} -> {output}")
    except Exception as e:
        logging.error(f"Error processing {file}: {e}")


def batch_process(directory: str, action: str):
    for file in os.listdir(directory):
        if file.lower().endswith(("png", "jpg", "jpeg")):
            process_image(os.path.join(directory, file), f"processed_{file}", action)


def main():
    parser = argparse.ArgumentParser(description="Image Processor")
    parser.add_argument("action", choices=["resize", "crop", "rotate", "grayscale", "blur"])
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    if os.path.isdir(args.input):
        batch_process(args.input, args.action)
    else:
        process_image(args.input, args.output, args.action)


if __name__ == "__main__":
    main()

