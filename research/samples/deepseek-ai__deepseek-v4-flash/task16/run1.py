import os
from pathlib import Path
from typing import List, Optional, Union, Callable, Dict, Any
from PIL import Image, ImageFilter, ImageEnhance

class ImageProcessor:
    """
    A class for processing images with support for resizing, format conversion,
    and applying various filters (blur, sharpen, edge detection). Includes batch
    processing capabilities, type hints, docstrings, and error handling.
    """

    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}

    def __init__(self, quality: int = 85):
        """
        Initialize the ImageProcessor.

        Args:
            quality: Default quality for JPEG and WebP saving (1-100).
        """
        self.quality = quality

    def _validate_input_path(self, path: Union[str, Path]) -> Path:
        """Validate and return a Path object for an input image."""
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Input file not found: {p}")
        if not p.is_file():
            raise ValueError(f"Path is not a file: {p}")
        if p.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported input format: {p.suffix}. Supported: {self.SUPPORTED_FORMATS}")
        return p

    def _validate_output_path(self, path: Union[str, Path]) -> Path:
        """Validate and return a Path object for output. Creates parent directories if needed."""
        p = Path(path).expanduser().resolve()
        if p.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported output format: {p.suffix}. Supported: {self.SUPPORTED_FORMATS}")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _open_image(self, path: Path) -> Image.Image:
        """Open an image file and return an Image object."""
        try:
            img = Image.open(path)
            img.verify()  # verify it's a valid image
            img = Image.open(path)  # re-open after verify
            return img
        except Exception as e:
            raise RuntimeError(f"Failed to open image {path}: {e}")

    def resize(self,
               image_path: Union[str, Path],
               output_path: Union[str, Path],
               width: int,
               height: int,
               keep_aspect_ratio: bool = True,
               resample: int = Image.LANCZOS) -> None:
        """
        Resize an image to the specified dimensions.

        Args:
            image_path: Path to the input image.
            output_path: Path to save the resized image.
            width: Target width in pixels.
            height: Target height in pixels.
            keep_aspect_ratio: If True, resize to fit within the box while preserving aspect ratio.
            resample: Resampling filter (PIL.Image.LANCZOS, etc.)
        """
        input_p = self._validate_input_path(image_path)
        output_p = self._validate_output_path(output_path)

        img = self._open_image(input_p)
        try:
            if keep_aspect_ratio:
                img.thumbnail((width, height), resample=resample)
            else:
                img = img.resize((width, height), resample=resample)

            img.save(output_p, quality=self.quality)
        except Exception as e:
            raise RuntimeError(f"Resize failed: {e}")

    def convert_format(self,
                       image_path: Union[str, Path],
                       output_path: Union[str, Path],
                       output_format: Optional[str] = None) -> None:
        """
        Convert an image to a different format.

        Args:
            image_path: Path to the input image.
            output_path: Path to save the converted image. The extension determines format.
            output_format: Override format (e.g., 'JPEG', 'PNG', 'WEBP'). If None, inferred from output_path.
        """
        input_p = self._validate_input_path(image_path)
        output_p = self._validate_output_path(output_path)

        img = self._open_image(input_p)
        try:
            if output_format:
                # convert to RGB if saving as JPEG/WebP to avoid alpha issues
                if output_format.upper() in ('JPEG', 'JPG', 'WEBP'):
                    img = img.convert('RGB')
                img.save(output_p, format=output_format, quality=self.quality)
            else:
                img.save(output_p, quality=self.quality)
        except Exception as e:
            raise RuntimeError(f"Format conversion failed: {e}")

    def apply_blur(self,
                   image_path: Union[str, Path],
                   output_path: Union[str, Path],
                   radius: Union[int, float] = 2) -> None:
        """
        Apply a Gaussian blur filter to the image.

        Args:
            image_path: Path to the input image.
            output_path: Path to save the blurred image.
            radius: Blur radius (pixels).
        """
        input_p = self._validate_input_path(image_path)
        output_p = self._validate_output_path(output_path)

        img = self._open_image(input_p)
        try:
            filtered = img.filter(ImageFilter.GaussianBlur(radius=radius))
            filtered.save(output_p, quality=self.quality)
        except Exception as e:
            raise RuntimeError(f"Blur filter failed: {e}")

    def apply_sharpen(self,
                      image_path: Union[str, Path],
                      output_path: Union[str, Path],
                      factor: float = 2.0) -> None:
        """
        Sharpen the image using an enhancement factor.

        Args:
            image_path: Path to the input image.
            output_path: Path to save the sharpened image.
            factor: Sharpening strength (1.0 = no change, 2.0 = strong).
        """
        input_p = self._validate_input_path(image_path)
        output_p = self._validate_output_path(output_path)

        img = self._open_image(input_p)
        try:
            enhancer = ImageEnhance.Sharpness(img)
            sharpened = enhancer.enhance(factor)
            sharpened.save(output_p, quality=self.quality)
        except Exception as e:
            raise RuntimeError(f"Sharpen filter failed: {e}")

    def apply_edge_detection(self,
                              image_path: Union[str, Path],
                              output_path: Union[str, Path]) -> None:
        """
        Apply an edge detection filter (PIL's FIND_EDGES) to the image.

        Args:
            image_path: Path to the input image.
            output_path: Path to save the edge-detected image.
        """
        input_p = self._validate_input_path(image_path)
        output_p = self._validate_output_path(output_path)

        img = self._open_image(input_p)
        try:
            edges = img.filter(ImageFilter.FIND_EDGES)
            edges.save(output_p, quality=self.quality)
        except Exception as e:
            raise RuntimeError(f"Edge detection failed: {e}")

    def process_single(self,
                        image_path: Union[str, Path],
                        output_dir: Union[str, Path],
                        operations: List[Dict[str, Any]],
                        suffix: str = "_processed") -> Path:
        """
        Apply a list of operations to a single image and save the result.

        Each operation is a dict with keys:
            'type': 'resize', 'convert', 'blur', 'sharpen', 'edge'
            'params': dict of parameters for the respective method.

        Args:
            image_path: Path to the input image.
            output_dir: Directory to save the output image.
            operations: List of operation dicts.
            suffix: String to append to the original filename (before extension).

        Returns:
            Path to the saved output image.
        """
        input_p = self._validate_input_path(image_path)
        output_dir = Path(output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build output filename: original_stem + suffix + extension
        output_filename = f"{input_p.stem}{suffix}{input_p.suffix}"
        output_p = output_dir / output_filename

        img = self._open_image(input_p)
        try:
            for op in operations:
                op_type = op.get('type')
                params = op.get('params', {})
                if op_type == 'resize':
                    img = img.copy()
                    w = params.get('width', 100)
                    h = params.get('height', 100)
                    keep_aspect = params.get('keep_aspect_ratio', True)
                    resample = params.get('resample', Image.LANCZOS)
                    if keep_aspect:
                        img.thumbnail((w, h), resample=resample)
                    else:
                        img = img.resize((w, h), resample=resample)
                elif op_type == 'convert':
                    # convert modifies color mode if needed, but format handling is done at save
                    target_format = params.get('format')
                    if target_format and target_format.upper() in ('JPEG', 'JPG', 'WEBP'):
                        img = img.convert('RGB')
                elif op_type == 'blur':
                    radius = params.get('radius', 2)
                    img = img.filter(ImageFilter.GaussianBlur(radius=radius))
                elif op_type == 'sharpen':
                    factor = params.get('factor', 2.0)
                    enhancer = ImageEnhance.Sharpness(img)
                    img = enhancer.enhance(factor)
                elif op_type == 'edge':
                    img = img.filter(ImageFilter.FIND_EDGES)
                else:
                    raise ValueError(f"Unknown operation type: {op_type}")

            img.save(output_p, quality=self.quality)
        except Exception as e:
            raise RuntimeError(f"Single image processing failed: {e}")

        return output_p

    def batch_process(self,
                       input_paths: Union[List[Union[str, Path]], str, Path],
                       output_dir: Union[str, Path],
                       operations: List[Dict[str, Any]],
                       suffix: str = "_processed",
                       glob_pattern: str = "*.*") -> List[Path]:
        """
        Process multiple images in batch.

        Args:
            input_paths: Either a list of file paths, or a single directory path.
            output_dir: Output directory for processed images.
            operations: List of operation dicts (same format as process_single).
            suffix: Suffix to append to filenames.
            glob_pattern: Glob pattern to match files if input_paths is a directory.

        Returns:
            List of paths to saved output images.
        """
        # Resolve input paths
        if isinstance(input_paths, (str, Path)):
            dir_path = Path(input_paths).expanduser().resolve()
            if not dir_path.is_dir():
                raise ValueError(f"Input path is not a directory: {dir_path}")
            # Get all image files recursively? Simple version: use glob directly
            images = sorted([p for p in dir_path.glob(glob_pattern) if p.suffix.lower() in self.SUPPORTED_FORMATS])
        else:
            images = [self._validate_input_path(p) for p in input_paths]

        output_dir = Path(output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for img_path in images:
            try:
                out_path = self.process_single(img_path, output_dir, operations, suffix)
                results.append(out_path)
            except Exception as e:
                # Log error but continue with other images (security: don't expose internal errors)
                print(f"Error processing {img_path}: {e}")
        return results