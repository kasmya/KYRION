"""
Image Processing Utility with Pillow and NumPy.

Features:
- Resize, crop, rotate images
- Convert between formats (PNG, JPEG, WebP, etc.)
- Apply filters (grayscale, blur, sharpen, edge detection)
- Batch processing of directories
- CLI with argparse
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Union
from enum import Enum
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageDraw, ImageFont

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('image_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ImageFormat(str, Enum):
    """Supported image formats."""
    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WEBP"
    BMP = "BMP"
    GIF = "GIF"
    TIFF = "TIFF"

class FilterType(str, Enum):
    """Available filter types."""
    GRAYSCALE = "grayscale"
    BLUR = "blur"
    GAUSSIAN_BLUR = "gaussian_blur"
    SHARPEN = "sharpen"
    EDGE_ENHANCE = "edge_enhance"
    EMBOSS = "emboss"
    CONTOUR = "contour"
    SMOOTH = "smooth"
    DETAIL = "detail"

class ImageProcessor:
    """Advanced image processing operations."""
    
    def __init__(self):
        """Initialize image processor."""
        self.supported_formats = {fmt.value.lower() for fmt in ImageFormat}
    
    def open_image(self, path: Union[str, Path]) -> Image.Image:
        """
        Open an image file.
        
        Args:
            path: Path to image file
            
        Returns:
            PIL Image object
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        
        try:
            image = Image.open(path)
            logger.info(f"Opened image: {path} ({image.size}, {image.mode})")
            return image
        except Exception as e:
            logger.error(f"Failed to open image {path}: {str(e)}")
            raise
    
    def save_image(
        self,
        image: Image.Image,
        path: Union[str, Path],
        format: Optional[ImageFormat] = None,
        quality: int = 95,
        optimize: bool = True
    ) -> Path:
        """
        Save image to file.
        
        Args:
            image: PIL Image to save
            path: Output path
            format: Output format
            quality: JPEG/WebP quality (1-100)
            optimize: Optimize file size
            
        Returns:
            Path to saved image
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        save_kwargs = {'optimize': optimize}
        
        if format:
            save_kwargs['format'] = format.value
        
        if format in [ImageFormat.JPEG, ImageFormat.WEBP]:
            save_kwargs['quality'] = quality
        
        try:
            image.save(path, **save_kwargs)
            file_size = path.stat().st_size
            logger.info(f"Saved image: {path} ({self._format_size(file_size)})")
            return path
        except Exception as e:
            logger.error(f"Failed to save image {path}: {str(e)}")
            raise
    
    def resize(
        self,
        image: Image.Image,
        width: Optional[int] = None,
        height: Optional[int] = None,
        keep_aspect_ratio: bool = True,
        resample: int = Image.LANCZOS
    ) -> Image.Image:
        """
        Resize image to specified dimensions.
        
        Args:
            image: Input image
            width: Target width
            height: Target height
            keep_aspect_ratio: Maintain aspect ratio
            resample: Resampling filter
            
        Returns:
            Resized image
        """
        if width is None and height is None:
            raise ValueError("At least one of width or height must be specified")
        
        original_size = image.size
        
        if keep_aspect_ratio:
            if width is None:
                ratio = height / original_size[1]
                width = int(original_size[0] * ratio)
            elif height is None:
                ratio = width / original_size[0]
                height = int(original_size[1] * ratio)
            else:
                # Fit within box while maintaining aspect ratio
                ratio = min(width / original_size[0], height / original_size[1])
                width = int(original_size[0] * ratio)
                height = int(original_size[1] * ratio)
        
        resized = image.resize((width, height), resample)
        logger.info(f"Resized: {original_size} -> {resized.size}")
        
        return resized
    
    def crop(
        self,
        image: Image.Image,
        left: int,
        top: int,
        right: int,
        bottom: int
    ) -> Image.Image:
        """
        Crop image to specified box.
        
        Args:
            image: Input image
            left: Left coordinate
            top: Top coordinate
            right: Right coordinate
            bottom: Bottom coordinate
            
        Returns:
            Cropped image
        """
        # Validate crop box
        width, height = image.size
        
        left = max(0, min(left, width))
        top = max(0, min(top, height))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))
        
        cropped = image.crop((left, top, right, bottom))
        logger.info(f"Cropped: {image.size} -> {cropped.size}")
        
        return cropped
    
    def rotate(
        self,
        image: Image.Image,
        angle: float,
        expand: bool = True,
        fill_color: Optional[Tuple[int, ...]] = None
    ) -> Image.Image:
        """
        Rotate image by specified angle.
        
        Args:
            image: Input image
            angle: Rotation angle in degrees
            expand: Expand output to fit rotated image
            fill_color: Color to fill empty areas
            
        Returns:
            Rotated image
        """
        if fill_color is None:
            # Use transparent for RGBA, white otherwise
            fill_color = (255, 255, 255, 0) if image.mode == 'RGBA' else (255, 255, 255)
        
        rotated = image.rotate(angle, expand=expand, fillcolor=fill_color, resample=Image.BICUBIC)
        logger.info(f"Rotated by {angle}°: {image.size} -> {rotated.size}")
        
        return rotated
    
    def apply_filter(
        self,
        image: Image.Image,
        filter_type: FilterType,
        **kwargs
    ) -> Image.Image:
        """
        Apply filter to image.
        
        Args:
            image: Input image
            filter_type: Type of filter to apply
            **kwargs: Additional filter parameters
            
        Returns:
            Filtered image
        """
        filter_map = {
            FilterType.GRAYSCALE: lambda img: ImageOps.grayscale(img),
            FilterType.BLUR: lambda img: img.filter(ImageFilter.BLUR),
            FilterType.GAUSSIAN_BLUR: lambda img: img.filter(
                ImageFilter.GaussianBlur(radius=kwargs.get('radius', 2))
            ),
            FilterType.SHARPEN: lambda img: img.filter(ImageFilter.SHARPEN),
            FilterType.EDGE_ENHANCE: lambda img: img.filter(ImageFilter.EDGE_ENHANCE),
            FilterType.EMBOSS: lambda img: img.filter(ImageFilter.EMBOSS),
            FilterType.CONTOUR: lambda img: img.filter(ImageFilter.CONTOUR),
            FilterType.SMOOTH: lambda img: img.filter(ImageFilter.SMOOTH),
            FilterType.DETAIL: lambda img: img.filter(ImageFilter.DETAIL),
        }
        
        filter_func = filter_map.get(filter_type)
        
        if not filter_func:
            raise ValueError(f"Unknown filter: {filter_type}")
        
        filtered = filter_func(image)
        logger.info(f"Applied filter: {filter_type.value}")
        
        return filtered
    
    def adjust_brightness(self, image: Image.Image, factor: float) -> Image.Image:
        """
        Adjust image brightness.
        
        Args:
            image: Input image
            factor: Brightness factor (1.0 = original)
            
        Returns:
            Adjusted image
        """
        enhancer = ImageEnhance.Brightness(image)
        return enhancer.enhance(factor)
    
    def adjust_contrast(self, image: Image.Image, factor: float) -> Image.Image:
        """
        Adjust image contrast.
        
        Args:
            image: Input image
            factor: Contrast factor (1.0 = original)
            
        Returns:
            Adjusted image
        """
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)
    
    def adjust_saturation(self, image: Image.Image, factor: float) -> Image.Image:
        """
        Adjust color saturation.
        
        Args:
            image: Input image
            factor: Saturation factor (1.0 = original, 0 = grayscale)
            
        Returns:
            Adjusted image
        """
        enhancer = ImageEnhance.Color(image)
        return enhancer.enhance(factor)
    
    def add_watermark(
        self,
        image: Image.Image,
        text: str,
        position: str = "bottom-right",
        opacity: float = 0.5,
        font_size: int = 36,
        color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Image.Image:
        """
        Add text watermark to image.
        
        Args:
            image: Input image
            text: Watermark text
            position: Position ('center', 'top-left', 'top-right', 'bottom-left', 'bottom-right')
            opacity: Text opacity (0-1)
            font_size: Font size
            color: Text color (RGB)
            
        Returns:
            Watermarked image
        """
        # Convert to RGBA if needed
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # Create overlay
        overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Use default font
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # Calculate text position
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        width, height = image.size
        padding = 20
        
        positions = {
            'center': ((width - text_width) // 2, (height - text_height) // 2),
            'top-left': (padding, padding),
            'top-right': (width - text_width - padding, padding),
            'bottom-left': (padding, height - text_height - padding),
            'bottom-right': (width - text_width - padding, height - text_height - padding),
        }
        
        text_pos = positions.get(position, positions['bottom-right'])
        
        # Draw text with opacity
        color_with_opacity = (*color, int(255 * opacity))
        draw.text(text_pos, text, font=font, fill=color_with_opacity)
        
        # Composite images
        watermarked = Image.alpha_composite(image, overlay)
        
        return watermarked
    
    def create_thumbnail(
        self,
        image: Image.Image,
        size: Tuple[int, int] = (128, 128)
    ) -> Image.Image:
        """
        Create a thumbnail.
        
        Args:
            image: Input image
            size: Thumbnail size
            
        Returns:
            Thumbnail image
        """
        thumb = image.copy()
        thumb.thumbnail(size, Image.LANCZOS)
        return thumb
    
    def process_batch(
        self,
        input_dir: Union[str, Path],
        output_dir: Union[str, Path],
        operations: List[dict],
        max_workers: int = 4
    ) -> List[Path]:
        """
        Batch process multiple images.
        
        Args:
            input_dir: Directory containing images
            output_dir: Output directory
            operations: List of operations to apply
            max_workers: Maximum concurrent workers
            
        Returns:
            List of output file paths
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all images
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff'}
        image_files = [
            f for f in input_dir.rglob('*')
            if f.suffix.lower() in image_extensions
        ]
        
        if not image_files:
            logger.warning(f"No images found in {input_dir}")
            return []
        
        logger.info(f"Processing {len(image_files)} images with {max_workers} workers")
        
        output_files = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._process_single_image, img_path, output_dir, operations
                ): img_path
                for img_path in image_files
            }
            
            for future in as_completed(futures):
                img_path = futures[future]
                try:
                    result = future.result()
                    output_files.append(result)
                    logger.info(f"Processed: {img_path.name}")
                except Exception as e:
                    logger.error(f"Failed to process {img_path}: {str(e)}")
        
        logger.info(f"Batch processing complete: {len(output_files)}/{len(image_files)} successful")
        return output_files
    
    def _process_single_image(
        self,
        input_path: Path,
        output_dir: Path,
        operations: List[dict]
    ) -> Path:
        """
        Process a single image with operations.
        
        Args:
            input_path: Input image path
            output_dir: Output directory
            operations: List of operations
            
        Returns:
            Output file path
        """
        image = self.open_image(input_path)
        
        # Apply operations
        for op in operations:
            op_type = op.get('type')
            
            if op_type == 'resize':
                image = self.resize(
                    image,
                    width=op.get('width'),
                    height=op.get('height'),
                    keep_aspect_ratio=op.get('keep_aspect_ratio', True)
                )
            elif op_type == 'crop':
                image = self.crop(
                    image,
                    op['left'], op['top'], op['right'], op['bottom']
                )
            elif op_type == 'rotate':
                image = self.rotate(
                    image,
                    op['angle'],
                    expand=op.get('expand', True)
                )
            elif op_type == 'filter':
                filter_type = FilterType(op['filter_type'])
                image = self.apply_filter(image, filter_type, **op.get('params', {}))
            elif op_type == 'brightness':
                image = self.adjust_brightness(image, op['factor'])
            elif op_type == 'contrast':
                image = self.adjust_contrast(image, op['factor'])
            elif op_type == 'saturation':
                image = self.adjust_saturation(image, op['factor'])
            elif op_type == 'watermark':
                image = self.add_watermark(
                    image,
                    op['text'],
                    position=op.get('position', 'bottom-right'),
                    opacity=op.get('opacity', 0.5)
                )
        
        # Determine output format
        output_format = operations[-1].get('format') if operations else None
        if output_format:
            output_format = ImageFormat[output_format.upper()]
        
        # Generate output path
        output_path = output_dir / f"processed_{input_path.stem}{input_path.suffix}"
        
        # Save processed image
        return self.save_image(
            image,
            output_path,
            format=output_format,
            quality=operations[-1].get('quality', 95)
        )
    
    @staticmethod
    def get_image_info(path: Union[str, Path]) -> dict:
        """
        Get image metadata.
        
        Args:
            path: Image path
            
        Returns:
            Dictionary with image information
        """
        path = Path(path)
        image = Image.open(path)
        
        info = {
            'filename': path.name,
            'format': image.format,
            'mode': image.mode,
            'size': image.size,
            'width': image.width,
            'height': image.height,
            'file_size': path.stat().st_size,
            'file_size_human': ImageProcessor._format_size(path.stat().st_size)
        }
        
        # Get EXIF data if available
        exif = image._getexif()
        if exif:
            info['exif'] = {
                'camera': exif.get(272, 'Unknown'),
                'date_taken': exif.get(36867, 'Unknown'),
                'iso': exif.get(34855, 'Unknown'),
            }
        
        return info
    
    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

def main():
    """CLI entry point for image processor."""
    parser = argparse.ArgumentParser(
        description='Image Processing Utility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Resize an image
  python image_processor.py resize -i input.jpg -o output.jpg --width 800 --height 600
  
  # Apply grayscale filter
  python image_processor.py filter -i input.jpg -o output.jpg -f grayscale
  
  # Batch process a directory
  python image_processor.py batch -i ./photos -o ./processed --resize 800 600 --filter grayscale
  
  # Convert format
  python image_processor.py convert -i input.png -o output.webp -f webp
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Resize command
    resize_parser = subparsers.add_parser('resize', help='Resize image')
    resize_parser.add_argument('-i', '--input', required=True, help='Input image')
    resize_parser.add_argument('-o', '--output', required=True, help='Output image')
    resize_parser.add_argument('--width', type=int, help='Target width')
    resize_parser.add_argument('--height', type=int, help='Target height')
    resize_parser.add_argument('--no-aspect', action='store_true', help='Ignore aspect ratio')
    
    # Filter command
    filter_parser = subparsers.add_parser('filter', help='Apply filter')
    filter_parser.add_argument('-i', '--input', required=True, help='Input image')
    filter_parser.add_argument('-o', '--output', required=True, help='Output image')
    filter_parser.add_argument('-f', '--filter', choices=[f.value for f in FilterType], required=True)
    
    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert format')
    convert_parser.add_argument('-i', '--input', required=True, help='Input image')
    convert_parser.add_argument('-o', '--output', required=True, help='Output image')
    convert_parser.add_argument('-f', '--format', choices=[f.name for f in ImageFormat], required=True)
    convert_parser.add_argument('-q', '--quality', type=int, default=95)
    
    # Batch command
    batch_parser = subparsers.add_parser('batch', help='Batch process directory')
    batch_parser.add_argument('-i', '--input', required=True, help='Input directory')
    batch_parser.add_argument('-o', '--output', required=True, help='Output directory')
    batch_parser.add_argument('--resize', nargs=2, type=int, metavar=('WIDTH', 'HEIGHT'), help='Resize images')
    batch_parser.add_argument('--filter', choices=[f.value for f in FilterType], help='Apply filter')
    batch_parser.add_argument('--workers', type=int, default=4, help='Concurrent workers')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Get image info')
    info_parser.add_argument('image', help='Image path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    processor = ImageProcessor()
    
    try:
        if args.command == 'resize':
            image = processor.open_image(args.input)
            image = processor.resize(
                image, args.width, args.height, not args.no_aspect
            )
            processor.save_image(image, args.output)
            print(f"✅ Image resized: {args.output}")
            
        elif args.command == 'filter':
            image = processor.open_image(args.input)
            filter_type = FilterType(args.filter)
            image = processor.apply_filter(image, filter_type)
            processor.save_image(image, args.output)
            print(f"✅ Filter applied: {args.output}")
            
        elif args.command == 'convert':
            image = processor.open_image(args.input)
            fmt = ImageFormat[args.format]
            processor.save_image(image, args.output, format=fmt, quality=args.quality)
            print(f"✅ Image converted: {args.output}")
            
        elif args.command == 'batch':
            operations = []
            
            if args.resize:
                operations.append({
                    'type': 'resize',
                    'width': args.resize[0],
                    'height': args.resize[1],
                    'keep_aspect_ratio': True
                })
            
            if args.filter:
                operations.append({
                    'type': 'filter',
                    'filter_type': args.filter
                })
            
            if not operations:
                print("❌ No operations specified for batch processing")
                return
            
            output_files = processor.process_batch(
                args.input, args.output, operations, args.workers
            )
            print(f"✅ Processed {len(output_files)} images")
            
        elif args.command == 'info':
            info = ImageProcessor.get_image_info(args.image)
            print("\nImage Information:")
            print("-" * 40)
            for key, value in info.items():
                print(f"{key}: {value}")
                
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
