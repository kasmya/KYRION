from PIL import Image, ImageFilter
from typing import List, Tuple
import os

class ImageProcessor:
    """
    A class used to process images.

    Methods:
    -------
    resize_image(image_path: str, size: Tuple[int, int]) -> str
        Resizes an image to a specified size.
    convert_format(image_path: str, output_format: str) -> str
        Converts an image to a specified format.
    apply_filter(image_path: str, filter_type: str) -> str
        Applies a filter to an image.
    batch_process(images: List[str], output_dir: str) -> None
        Batch processes multiple images.
    """

    def __init__(self, output_dir: str = 'output'):
        """
        Initializes the ImageProcessor class.

        Args:
        ----
        output_dir (str): The directory where processed images will be saved.
        """
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def resize_image(self, image_path: str, size: Tuple[int, int]) -> str:
        """
        Resizes an image to a specified size.

        Args:
        ----
        image_path (str): The path to the image file.
        size (Tuple[int, int]): The new size of the image.

        Returns:
        -------
        str: The path to the resized image file.
        """
        try:
            with Image.open(image_path) as img:
                img = img.resize(size)
                filename, file_extension = os.path.splitext(image_path)
                output_path = os.path.join(self.output_dir, f'{os.path.basename(filename)}_resized{file_extension}')
                img.save(output_path)
                return output_path
        except OSError as e:
            print(f"Error occurred while resizing image: {e}")
            return None

    def convert_format(self, image_path: str, output_format: str) -> str:
        """
        Converts an image to a specified format.

        Args:
        ----
        image_path (str): The path to the image file.
        output_format (str): The new format of the image.

        Returns:
        -------
        str: The path to the converted image file.
        """
        try:
            with Image.open(image_path) as img:
                filename, _ = os.path.splitext(image_path)
                output_path = os.path.join(self.output_dir, f'{os.path.basename(filename)}.{output_format.lower()}')
                img.save(output_path)
                return output_path
        except OSError as e:
            print(f"Error occurred while converting image format: {e}")
            return None

    def apply_filter(self, image_path: str, filter_type: str) -> str:
        """
        Applies a filter to an image.

        Args:
        ----
        image_path (str): The path to the image file.
        filter_type (str): The type of filter to apply.

        Returns:
        -------
        str: The path to the filtered image file.
        """
        try:
            with Image.open(image_path) as img:
                if filter_type == 'blur':
                    img = img.filter(ImageFilter.GaussianBlur(radius=5))
                elif filter_type == 'sharpen':
                    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
                elif filter_type == 'edge detection':
                    img = img.filter(ImageFilter.FIND_EDGES)
                else:
                    print("Invalid filter type")
                    return None
                filename, file_extension = os.path.splitext(image_path)
                output_path = os.path.join(self.output_dir, f'{os.path.basename(filename)}_{filter_type}{file_extension}')
                img.save(output_path)
                return output_path
        except OSError as e:
            print(f"Error occurred while applying filter: {e}")
            return None

    def batch_process(self, images: List[str], output_dir: str = None) -> None:
        """
        Batch processes multiple images.

        Args:
        ----
        images (List[str]): A list of image file paths.
        output_dir (str): The directory where processed images will be saved.
        """
        if output_dir:
            self.output_dir = output_dir
        for image in images:
            self.resize_image(image, (800, 600))
            self.convert_format(image, 'webp')
            self.apply_filter(image, 'blur')

if __name__ == "__main__":
    image_processor = ImageProcessor()
    images = ['image1.jpg', 'image2.png', 'image3.bmp']
    image_processor.batch_process(images)