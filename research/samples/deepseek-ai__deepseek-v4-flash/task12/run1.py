import os
import io
import zipfile
import gzip
import tarfile
import shutil
from enum import Enum
from typing import List, Optional, Union
from pathlib import Path


class CompressionFormat(Enum):
    ZIP = "zip"
    GZIP = "gzip"
    TAR = "tar"


class CompressionUtility:
    """
    A file compression utility supporting ZIP, GZIP, and TAR formats.
    """

    @staticmethod
    def _validate_path(file_path: str) -> Path:
        """Validate and return a Path object, raising on invalid paths."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {file_path}")
        return path

    @staticmethod
    def _sanitize_archive_name(name: str) -> str:
        """Sanitize archive member names to prevent path traversal."""
        # Convert to POSIX path, strip leading /, remove .. components
        sanitized = os.path.normpath(name).lstrip("/")
        # Ensure no parent directory traversal remains
        if sanitized.startswith("..") or ".." in sanitized.split(os.sep):
            raise ValueError(f"Invalid archive member name: {name}")
        return sanitized

    @staticmethod
    def _get_output_path(input_path: Path, format: CompressionFormat) -> Path:
        """Generate default output path by appending proper extension."""
        suffix_map = {
            CompressionFormat.ZIP: ".zip",
            CompressionFormat.GZIP: ".gz",
            CompressionFormat.TAR: ".tar",
        }
        return input_path.with_suffix(input_path.suffix + suffix_map[format])

    @staticmethod
    def compress_file(
        file_path: str,
        format: CompressionFormat,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Compress a single file.

        Args:
            file_path: Path to the file to compress.
            format: Compression format (zip, gzip, tar).
            output_path: Optional output archive path. If not provided, derived from input.

        Returns:
            Path to the created archive.

        Raises:
            FileNotFoundError: If input file does not exist.
            PermissionError: If insufficient permissions.
            ValueError: If format is unsupported.
        """
        input_path = CompressionUtility._validate_path(file_path)
        if not input_path.is_file():
            raise ValueError(f"Input path is not a file: {file_path}")

        if output_path is None:
            output_path = str(CompressionUtility._get_output_path(input_path, format))

        try:
            if format == CompressionFormat.ZIP:
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    arch_name = CompressionUtility._sanitize_archive_name(
                        input_path.name
                    )
                    zf.write(str(input_path), arcname=arch_name)

            elif format == CompressionFormat.GZIP:
                # GZIP compresses a single file; we store the original name in the archive
                with open(input_path, "rb") as f_in:
                    with gzip.open(output_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                # GNU tar-like behavior is not standard; gzip alone stores no metadata.
                # For consistency, we rename output to .gz (already done by output_path)

            elif format == CompressionFormat.TAR:
                with tarfile.open(output_path, "w:gz") as tar:
                    arch_name = CompressionUtility._sanitize_archive_name(
                        input_path.name
                    )
                    tar.add(str(input_path), arcname=arch_name)

            else:
                raise ValueError(f"Unsupported compression format: {format}")

        except PermissionError:
            raise PermissionError(f"Permission denied when creating archive: {output_path}")
        except OSError as e:
            raise OSError(f"Compression failed: {e}")

        return output_path

    @staticmethod
    def compress_directory(
        dir_path: str,
        format: CompressionFormat,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Compress a directory (recursively).

        Args:
            dir_path: Path to the directory to compress.
            format: Compression format (zip, tar). GZIP is not supported for directories.
            output_path: Optional output archive path.

        Returns:
            Path to the created archive.

        Raises:
            ValueError: If format is gzip (cannot compress directories) or other unsupported.
            FileNotFoundError: If directory not found.
        """
        if format == CompressionFormat.GZIP:
            raise ValueError("GZIP does not support compressing directories.")

        input_path = CompressionUtility._validate_path(dir_path)
        if not input_path.is_dir():
            raise ValueError(f"Input path is not a directory: {dir_path}")

        if output_path is None:
            # Use directory name + extension
            output_path = str(
                input_path.with_name(input_path.name + CompressionUtility._get_output_path(input_path, format).suffix)
            )

        try:
            if format == CompressionFormat.ZIP:
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(str(input_path)):
                        for file in files:
                            full_path = os.path.join(root, file)
                            # Compute relative path from input directory
                            rel_path = os.path.relpath(full_path, str(input_path))
                            # Sanitize to prevent absolute or traversal paths
                            arch_name = CompressionUtility._sanitize_archive_name(rel_path)
                            zf.write(full_path, arcname=arch_name)

            elif format == CompressionFormat.TAR:
                with tarfile.open(output_path, "w:gz") as tar:
                    tar.add(str(input_path), arcname=os.path.basename(str(input_path)),
                            filter=lambda info: CompressionUtility._tar_filter(info, str(input_path)))

            else:
                raise ValueError(f"Unsupported compression format: {format}")

        except PermissionError:
            raise PermissionError(f"Permission denied when creating archive: {output_path}")
        except OSError as e:
            raise OSError(f"Compression failed: {e}")

        return output_path

    @staticmethod
    def _tar_filter(tarinfo: tarfile.TarInfo, base_dir: str) -> Optional[tarfile.TarInfo]:
        """Filter function to prevent path traversal in tar archives."""
        # Normalize the name and check safety
        name = tarinfo.name
        # Ensure the base directory is not escaped (though tarfile should handle relpath)
        if os.path.isabs(name) or ".." in name.split("/"):
            return None  # Skip unsafe entries
        # Optionally set ownership to a non-privileged user
        tarinfo.uid = 0
        tarinfo.gid = 0
        tarinfo.uname = ""
        tarinfo.gname = ""
        return tarinfo

    @staticmethod
    def decompress(
        archive_path: str,
        output_dir: str = ".",
        format: Optional[CompressionFormat] = None,
    ) -> str:
        """
        Decompress an archive to a directory.

        Args:
            archive_path: Path to the archive.
            output_dir: Destination directory (created if it doesn't exist).
            format: Compression format. If None, inferred from file extension.

        Returns:
            Path to the output directory.

        Raises:
            FileNotFoundError: If archive not found.
            ValueError: If format cannot be inferred or is unsupported.
            ExtractionError: For security issues like path traversal.
        """
        archive_path_obj = CompressionUtility._validate_path(archive_path)
        if not archive_path_obj.is_file():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        if format is None:
            suffix = archive_path_obj.suffix.lower()
            if suffix == ".zip":
                format = CompressionFormat.ZIP
            elif suffix == ".gz":
                # GZIP archives are single files; we need to handle that specially
                format = CompressionFormat.GZIP
            elif suffix == ".tar":
                format = CompressionFormat.TAR
            elif suffix == ".tgz":
                format = CompressionFormat.TAR  # .tgz is tar.gz
            else:
                raise ValueError(
                    f"Cannot infer compression format from extension: {archive_path}"
                )

        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            if format == CompressionFormat.ZIP:
                with zipfile.ZipFile(str(archive_path_obj), "r") as zf:
                    # Extract with safety check
                    for info in zf.infolist():
                        # Sanitize name
                        sanitized = CompressionUtility._sanitize_archive_name(info.filename)
                        # Prevent extracting to absolute path or outside output_dir
                        target_path = output_path / sanitized
                        # Ensure the target path is within output_dir
                        try:
                            target_path.relative_to(output_path)
                        except ValueError:
                            raise ValueError(
                                f"Archive member {info.filename} attempts path traversal."
                            )
                    zf.extractall(path=str(output_path))

            elif format == CompressionFormat.GZIP:
                # GZIP decompress: output file name derived from archive name (strip .gz)
                out_file_name = archive_path_obj.stem  # removes .gz
                if not out_file_name:
                    out_file_name = "decompressed"  # fallback
                out_file_path = output_path / out_file_name
                with gzip.open(str(archive_path_obj), "rb") as f_in:
                    with open(str(out_file_path), "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)

            elif format == CompressionFormat.TAR:
                with tarfile.open(str(archive_path_obj), "r:*") as tar:
                    # Use filter function to reject unsafe paths
                    def safe_filter(member: tarfile.TarInfo,
                                    dest: str = str(output_path)) -> Optional[tarfile.TarInfo]:
                        # Normalize and check for directory traversal
                        name = member.name
                        # Convert to POSIX, strip leading /
                        name = os.path.normpath(name).lstrip("/")
                        if name.startswith("..") or ".." in name.split("/"):
                            return None
                        # Ensure final destination is inside output_dir
                        dest_path = os.path.join(dest, name)
                        if not os.path.realpath(dest_path).startswith(os.path.realpath(dest)):
                            return None
                        member.name = name
                        return member

                    tar.extractall(path=str(output_path), filter=safe_filter)

            else:
                raise ValueError(f"Unsupported compression format: {format}")

        except PermissionError:
            raise PermissionError(f"Permission denied when extracting to: {output_dir}")
        except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile) as e:
            raise ValueError(f"Archive is corrupted or invalid: {e}")
        except OSError as e:
            raise OSError(f"Decompression failed: {e}")

        return str(output_path)

    @staticmethod
    def list_contents(archive_path: str, format: Optional[CompressionFormat] = None) -> List[str]:
        """
        List the contents of an archive.

        Args:
            archive_path: Path to the archive.
            format: Compression format. If None, inferred from extension.

        Returns:
            List of member names (strings).

        Raises:
            FileNotFoundError: If archive not found.
            ValueError: If format cannot be inferred.
        """
        archive_path_obj = CompressionUtility._validate_path(archive_path)
        if not archive_path_obj.is_file():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        if format is None:
            suffix = archive_path_obj.suffix.lower()
            if suffix == ".zip":
                format = CompressionFormat.ZIP
            elif suffix == ".gz":
                # For .gz, we only have one member (the original file name is not stored in gzip by default)
                # We'll return the archive name without .gz as a placeholder
                format = CompressionFormat.GZIP
            elif suffix == ".tar":
                format = CompressionFormat.TAR
            elif suffix == ".tgz":
                format = CompressionFormat.TAR
            else:
                raise ValueError(
                    f"Cannot infer compression format from extension: {archive_path}"
                )

        members = []
        try:
            if format == CompressionFormat.ZIP:
                with zipfile.ZipFile(str(archive_path_obj), "r") as zf:
                    members = zf.namelist()

            elif format == CompressionFormat.GZIP:
                # GZIP archives contain a single compressed file; display archive name
                members = [archive_path_obj.stem]

            elif format == CompressionFormat.TAR:
                with tarfile.open(str(archive_path_obj), "r:*") as tar:
                    members = [m.name for m in tar.getmembers()]

            else:
                raise ValueError(f"Unsupported compression format: {format}")

        except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile) as e:
            raise ValueError(f"Archive is corrupted or invalid: {e}")
        except OSError as e:
            raise OSError(f"Failed to read archive: {e}")

        return members