from PIL import Image, ImageFilter, ImageOps
from typing import List, Tuple, Optional
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler()])

class ImageProcessor:
    """
    A class for processing images: resizing, format conversion, filtering, and batch processing.
    
    Attributes:
    - size: Tuple[int, int] for resize operations
    - output_format: str (e.g., 'JPEG', 'PNG', 'WebP') for format conversion
    - filter_type: str (e.g., 'blur', 'sharpen', 'edge') for applying filters
    """

    def __init__(self, size: Optional[Tuple[int, int]] = None, 
                 output_format: str = 'JPEG', filter_type: str = None):
        """
        Initializes the ImageProcessor with optional size, output format, and filter type.
        
        :param size: Tuple of two integers for resizing (width, height)
        :param output_format: String representing the output image format
        :param filter_type: String indicating the filter to apply
        """
        self.size = size
        self.output_format = output_format.lower()  # Normalize to lowercase for comparison
        self.filter_type = filter_type.lower() if filter_type else None

        # Validate output format
        if self.output_format not in ['jpeg', 'png', 'webp']:
            raise ValueError("Invalid output format. Supported formats: JPEG, PNG, WebP")

        # Validate filter type
        if self.filter_type not in [None, 'blur', 'sharpen', 'edge']:
            raise ValueError("Invalid filter type. Supported filters: blur, sharpen, edge")

    def _apply_filter(self, img: Image) -> Image:
        """
        Applies the specified filter to the image.
        
        :param img: Pillow Image object
        :return: Filtered Image object
        """
        if self.filter_type == 'blur':
            return img.filter(ImageFilter.BLUR)
        elif self.filter_type == 'sharpen':
            return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=0))
        elif self.filter_type == 'edge':
            return ImageOps.grayscale(img).filter(ImageFilter.FIND_EDGES)
        else:
            return img  # No filter applied

    def _convert_format(self, img: Image) -> bytes:
        """
        Converts the image to the specified output format and returns as bytes.
        
        :param img: Pillow Image object
        :return: Bytes of the image in the output format
        """
        # Ensure mode is compatible with the output format
        if self.output_format in ['webp'] and img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        buffer = BytesIO()
        if self.output_format == 'webp':
            img.save(buffer, format="WebP", quality=85)  # Quality adjustment for WebP
        else:
            img.save(buffer, format=self.output_format.upper())
        return buffer.getvalue()

    def process_image(self, input_path: str, output_path: str) -> bool:
        """
        Processes a single image: resizes, applies filter, converts format, and saves.
        
        :param input_path: Path to the input image file
        :param output_path: Desired path for the output image file
        :return: True if successful, False otherwise
        """
        try:
            with Image.open(input_path) as img:
                if self.size:
                    img = img.resize(self.size)
                img = self._apply_filter(img)
                output_bytes = self._convert_format(img)
                
                # Ensure directory exists for output
                output_dir = os.path.dirname(output_path)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                
                with open(output_path, 'wb') as f:
                    f.write(output_bytes)
                logging.info(f"Processed {input_path} -> {output_path}")
                return True
        except Exception as e:
            logging.error(f"Error processing {input_path}: {e}")
            return False

    def batch_process(self, input_paths: List[str], output_dir: str) -> List[bool]:
        """
        Batch processes multiple images.
        
        :param input_paths: List of paths to input image files
        :param output_dir: Directory for output images
        :return: List of boolean indicating success for each input
        """
        results = []
        for path in input_paths:
            filename = os.path.basename(path)
            output_path = os.path.join(output_dir, filename)
            # Preserve original extension for output to handle format conversion correctly
            if self.output_format:
                base, _ = os.path.splitext(filename)
                output_path = os.path.join(output_dir, f"{base}.{self.output_format.lower()}")
            results.append(self.process_image(path, output_path))
        return results


if __name__ == "__main__":
    # Example Usage
    processor = ImageProcessor(
        size=(800, 600),  # Resize to 800x600
        output_format='webp',  # Convert to WebP
        filter_type='sharpen'  # Apply sharpen filter
    )
    
    input_images = ['image1.jpg', 'image2.png', 'image3.bmp']
    output_directory = 'processed_images'
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    batch_results = processor.batch_process(input_images, output_directory)
    for path, success in zip(input_images, batch_results):
        print(f"{path} - {'Success' if success else 'Failed'}")