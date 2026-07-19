"""Image Processor CLI with Pillow, NumPy, and batch processing."""
import os, argparse, logging
from typing import Tuple, Optional
from PIL import Image, ImageFilter
import numpy as np

logging.basicConfig(level=logging.INFO)

def process_image(input_path: str, output_path: str, size: Optional[Tuple[int, int]] = None, 
                  crop: Optional[Tuple[int, int, int, int]] = None, rotate: float = 0.0,
                  grayscale: bool = False, blur: bool = False):
    """Apply transformations to a single image."""
    try:
        img = Image.open(input_path)
        
        if crop:
            img = img.crop(crop)
        if rotate:
            img = img.rotate(rotate, expand=True)
        if size:
            img = img.resize(size, Image.Resampling.LANCZOS)
            
        # Convert to numpy for advanced processing if needed
        img_array = np.array(img)
        
        if grayscale:
            # Using numpy for grayscale conversion
            if len(img_array.shape) == 3:
                gray = np.dot(img_array[...,:3], [0.2989, 0.5870, 0.1140]).astype(np.uint8)
                img = Image.fromarray(gray, mode='L')
                
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(radius=2))
            
        # Convert back to RGB if saving as JPEG and image is grayscale
        if output_path.lower().endswith(('.jpg', '.jpeg')) and img.mode != 'RGB':
            img = img.convert('RGB')
            
        img.save(output_path)
        logging.info(f"Processed: {input_path} -> {output_path}")
    except Exception as e:
        logging.error(f"Failed to process {input_path}: {e}")

def batch_process(input_dir: str, output_dir: str, **kwargs):
    """Process all images in a directory."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    valid_ext = {'.png', '.jpg', '.jpeg', '.webp'}
    for filename in os.listdir(input_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in valid_ext:
            in_path = os.path.join(input_dir, filename)
            out_path = os.path.join(output_dir, filename)
            process_image(in_path, out_path, **kwargs)

def main():
    parser = argparse.ArgumentParser(description="Image Processor")
    parser.add_argument("input", help="Input file or directory")
    parser.add_argument("output", help="Output file or directory")
    parser.add_argument("--size", type=int, nargs=2, metavar=('W', 'H'), help="Resize dimensions")
    parser.add_argument("--crop", type=int, nargs=4, metavar=('L', 'T', 'R', 'B'), help="Crop box")
    parser.add_argument("--rotate", type=float, default=0.0, help="Rotation angle")
    parser.add_argument("--grayscale", action="store_true", help="Convert to grayscale")
    parser.add_argument("--blur", action="store_true", help="Apply Gaussian blur")
    
    args = parser.parse_args()
    kwargs = {
        'size': tuple(args.size) if args.size else None,
        'crop': tuple(args.crop) if args.crop else None,
        'rotate': args.rotate,
        'grayscale': args.grayscale,
        'blur': args.blur
    }
    
    if os.path.isdir(args.input):
        batch_process(args.input, args.output, **kwargs)
    else:
        process_image(args.input, args.output, **kwargs)

if __name__ == "__main__":
    main()