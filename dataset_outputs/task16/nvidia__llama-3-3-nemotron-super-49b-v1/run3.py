# image_processor.py
from typing import List, Tuple, Optional
import os
from PIL import Image, ImageFilter
from PIL.Image import ImageFile
from PIL import UnidentifiedImageError
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import sys

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    A class for processing images: resizing, format conversion, and filter application.
    
    Attributes:
    ----------
    input_dir : str
        Directory containing input images.
    output_dir : str
        Directory for output images.
    supported_formats : List[str]
        List of supported image formats.
    supported_filters : Dict[str, Callable]
        Mapping of filter names to their respective Pillow filters.
    """

    def __init__(self, input_dir: str, output_dir: str):
        """
        Initializes the ImageProcessor with input and output directories.
        
        :param input_dir: Directory containing input images.
        :param output_dir: Directory for output images.
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.supported_formats = ["JPEG", "PNG", "WebP"]
        self.supported_filters = {
            "blur": ImageFilter.BLUR,
            "sharpen": ImageFilter.SHARPEN,
            "edge_detection": ImageFilter.FIND_EDGES
        }
        self._validate_directories()

    def _validate_directories(self) -> None:
        """
        Ensures input and output directories exist and are writable.
        """
        for dir_, purpose in [(self.input_dir, "input"), (self.output_dir, "output")]:
            if not os.path.exists(dir_):
                logger.error(f"{purpose.capitalize()} directory '{dir_}' does not exist.")
                sys.exit(1)
            if not os.access(dir_, os.W_OK):
                logger.error(f"Output directory '{dir_}' is not writable.")
                sys.exit(1)

    def resize_image(self, image_path: str, new_size: Tuple[int, int]) -> Optional[str]:
        """
        Resizes an image.
        
        :param image_path: Path to the image file.
        :param new_size: Tuple of (width, height) for the new size.
        :return: Path to the resized image, or None on failure.
        """
        try:
            with Image.open(image_path) as img:
                img.resize(new_size).save(os.path.join(self.output_dir, f"resized_{os.path.basename(image_path)}"))
                return os.path.join(self.output_dir, f"resized_{os.path.basename(image_path)}")
        except (UnidentifiedImageError, OSError) as e:
            logger.error(f"Failed to resize {image_path}: {e}")
            return None

    def convert_format(self, image_path: str, target_format: str) -> Optional[str]:
        """
        Converts an image to a different format.
        
        :param image_path: Path to the image file.
        :param target_format: Desired format (JPEG, PNG, WebP).
        :return: Path to the converted image, or None on failure.
        """
        if target_format.upper() not in self.supported_formats:
            logger.error(f"Unsupported format: {target_format}")
            return None
        try:
            with Image.open(image_path) as img:
                output_path = os.path.join(self.output_dir, f"{os.path.splitext(os.path.basename(image_path))[0]}.{target_format.lower()}")
                img.save(output_path, format=target_format)
                return output_path
        except (UnidentifiedImageError, OSError) as e:
            logger.error(f"Failed to convert {image_path} to {target_format}: {e}")
            return None

    def apply_filter(self, image_path: str, filter_name: str) -> Optional[str]:
        """
        Applies a filter to an image.
        
        :param image_path: Path to the image file.
        :param filter_name: Name of the filter (blur, sharpen, edge_detection).
        :return: Path to the filtered image, or None on failure.
        """
        if filter_name not in self.supported_filters:
            logger.error(f"Unsupported filter: {filter_name}")
            return None
        try:
            with Image.open(image_path) as img:
                filtered_img = img.filter(self.supported_filters[filter_name])
                output_path = os.path.join(self.output_dir, f"{filter_name}_{os.path.basename(image_path)}")
                filtered_img.save(output_path)
                return output_path
        except (UnidentifiedImageError, OSError) as e:
            logger.error(f"Failed to apply {filter_name} to {image_path}: {e}")
            return None

    def batch_process(self, operation: str, **kwargs) -> List[Optional[str]]:
        """
        Batch processes images in the input directory.
        
        :param operation: Operation to perform (resize, convert_format, apply_filter).
        :param kwargs: Operation-specific keyword arguments.
        :return: List of paths to processed images, or None for failures.
        """
        supported_operations = {
            "resize": self.resize_image,
            "convert_format": self.convert_format,
            "apply_filter": self.apply_filter
        }
        
        if operation not in supported_operations:
            logger.error(f"Unsupported operation: {operation}")
            return []
        
        image_paths = [os.path.join(self.input_dir, file) for file in os.listdir(self.input_dir) if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        results = []
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(supported_operations[operation], path, **kwargs): path for path in image_paths}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Error processing {futures[future]}: {e}")
                    results.append(None)
        
        return results

if __name__ == "__main__":
    processor = ImageProcessor("input_images", "output_images")
    
    # Example Usage
    batch_results = processor.batch_process("resize", new_size=(800, 600))
    for result in batch_results:
        if result:
            logger.info(f"Successfully resized image: {result}")
        else:
            logger.info("Resize operation failed for an image.")
    
    # Convert format example
    # processor.batch_process("convert_format", target_format="PNG")
    
    # Apply filter example
    # processor.batch_process("apply_filter", filter_name="blur")