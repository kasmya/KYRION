"""
Task 16: High-Performance CLI Batch Image Transformation Tool
Features: NumPy matrix filter manipulations, clean aspect dimension recalculations, recursive processing folders loops.
Requires: pillow, numpy, argparse
"""

import os
import sys
import argparse
import logging
from typing import List, Tuple
from PIL import Image, ImageFilter
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ImageTransformationEngine:
    """Executes high-performance transformations across localized physical graphic files blocks."""

    @staticmethod
    def map_to_grayscale_numpy(pil_image_instance: Image.Image) -> Image.Image:
        """Transforms multi-channel input structures into single-channel grayscale space metrics via NumPy arrays."""
        image_matrix = np.array(pil_image_instance)
        
        # Check color depths before applying scalar multipliers
        if len(image_matrix.shape) == 3:
            # Apply standard ITU-R 601-2 luma transform coefficients
            grayscale_coefficients = [0.299, 0.587, 0.114]
            luminance_matrix = np.dot(image_matrix[..., :3], grayscale_coefficients).astype(np.uint8)
            return Image.fromarray(luminance_matrix)
        return pil_image_instance

    @classmethod
    def transform_single_image_file(
        cls, input_file_path: str, output_file_path: str, 
        scale_dimensions: Optional[Tuple[int, int]] = None, apply_blur: bool = False, convert_grayscale: bool = False
    ) -> None:
        """Executes operations sequentially over a single graphic file image asset transaction."""
        try:
            with Image.open(input_file_path) as image_ref:
                processed_image = image_ref.copy()
                
                if scale_dimensions:
                    logger.info(f"Rescaling dimensions layout target constraints to bounds: {scale_dimensions}")
                    processed_image = processed_image.resize(scale_dimensions, Image.Resampling.LANCZOS)
                
                if convert_grayscale:
                    logger.info("Executing matrix projection color space flatten arrays filters pipelines.")
                    processed_image = cls.map_to_grayscale_numpy(processed_image)
                    
                if apply_blur:
                    logger.info("Applying multi-pass Gaussian filtering spatial blur convolutions algorithms.")
                    processed_image = processed_image.filter(ImageFilter.GaussianBlur(radius=2.0))
                
                # Check formatting types before writing records to physical disks destination lines
                target_extension = os.path.splitext(output_file_path)[-1].lower()
                format_mapping = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
                save_format = format_mapping.get(target_extension, "PNG")

                processed_image.save(output_file_path, format=save_format, quality=85)
                logger.info(f"Successfully finalized graphic transformation writing logs destination target: {output_file_path}")
                
        except Exception as file_io_err:
            logger.error(f"Failed to process target image data at location: {input_file_path}. Error: {file_io_err}")

def main() -> None:
    """Coordinates parsing variables arguments flags directly down across operations loops structures."""
    cli_parser = argparse.ArgumentParser(description="Batch Image Transformations Processing Command Line Tool")
    cli_parser.add_argument("-i", "--input_dir", required=True, help="Target localized input data assets inventory directory route path.")
    cli_parser.add_argument("-o", "--output_dir", required=True, help="Destination directory where output assets are written.")
    cli_parser.add_argument("--resize", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), help="Forces dimensional scales overriding over image layouts configurations profiles.")
    cli_parser.add_argument("--blur", action="store_true", help="Applies standard spatial matrix blurring filters optimizations maps.")
    cli_parser.add_argument("--grayscale", action="store_true", help="Flattens incoming pixel channel arrays records to grayscale values variables.")

    args = cli_parser.parse_args()

    if not os.path.exists(args.input_dir):
        logger.error(f"Inbound processing directory is unreachable or invalid: {args.input_dir}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    
    target_dimensions = tuple(args.resize) if args.resize else None
    
    # Process files inside input target folders recursively
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    for filename in os.listdir(args.input_dir):
        file_extension = os.path.splitext(filename)[-1].lower()
        if file_extension in valid_extensions:
            source_file_coordinate = os.path.join(args.input_dir, filename)
            output_file_coordinate = os.path.join(args.output_dir, filename)
            
            ImageTransformationEngine.transform_single_image_file(
                input_file_path=source_file_coordinate,
                output_file_path=output_file_coordinate,
                scale_dimensions=target_dimensions,
                apply_blur=args.blur,
                convert_grayscale=args.grayscale
            )

if __name__ == "__main__":
    main()
