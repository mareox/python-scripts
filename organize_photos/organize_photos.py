#!/usr/bin/env python3
"""
organize_photos.py - A script to organize photos and videos by date into a structured directory.

This script organizes image and video files from a source directory (and its subdirectories)
into a target directory with the structure year/month/day based on the file creation date.
Creation date is extracted from EXIF/metadata if available, otherwise file modification time is used.

The script will prompt for:
- Source directory containing images and videos
- Target directory for organized files
- Whether to copy or move files
- Whether to run in simulation mode
- Whether to show a progress bar
"""

import os
import sys
import shutil
import datetime
import exifread
from pathlib import Path
import logging
import csv
import time

# Optional import for progress bar
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Optional imports for video metadata extraction
try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Define supported image extensions
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
    # Optional extended formats
    '.heic', '.raw', '.cr2', '.nef', '.arw'
}

# Define supported video extensions
VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.wmv', '.mkv', '.flv', '.webm', '.m4v',
    '.3gp', '.mpg', '.mpeg', '.mts', '.m2ts'
}

# Combined supported file extensions
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS)


def get_user_input():
    """Prompt user for source and target directories and options."""
    print("\n=== Photo & Video Organizer ===")
    print("This script organizes photos and videos by date based on metadata or file modification time.\n")
    
    # Get source directory
    while True:
        source_dir = input("Enter source directory path: ").strip()
        source_path = Path(source_dir)
        
        if not source_path.exists():
            print(f"Error: Source directory does not exist: {source_path}")
            continue
        
        if not source_path.is_dir():
            print(f"Error: Source path is not a directory: {source_path}")
            continue
        
        break
    
    # Get target directory
    while True:
        target_dir = input("Enter target directory path: ").strip()
        target_path = Path(target_dir)
        
        # Create target directory if it doesn't exist
        if not target_path.exists():
            try:
                create_now = input("Target directory doesn't exist. Create it now? (y/n): ").strip().lower()
                if create_now == 'y':
                    target_path.mkdir(parents=True)
                    print(f"Created target directory: {target_path}")
                else:
                    print("Please enter a different target directory path.")
                    continue
            except Exception as e:
                print(f"Error: Failed to create target directory: {e}")
                continue
        
        # Check if target is a subdirectory of source to avoid traversal issues
        if target_path.resolve().is_relative_to(source_path.resolve()):
            print("Error: Target directory cannot be a subdirectory of the source directory")
            continue
        
        break
    
    # Get options
    copy_option = input("Copy files instead of moving them? (y/n): ").strip().lower() == 'y'
    dry_run_option = input("Simulate without actually moving/copying files? (y/n): ").strip().lower() == 'y'
    progress_option = False
    
    if TQDM_AVAILABLE:
        progress_option = input("Show progress bar during processing? (y/n): ").strip().lower() == 'y'
    
    # Get report file path
    report_file = input("Enter path for the report file (leave empty for default 'organization_report.csv'): ").strip()
    if not report_file:
        report_file = "organization_report.csv"
    
    # Create a class-like object to mimic the args structure
    class Args:
        pass
    
    args = Args()
    args.source = source_dir
    args.target = target_dir
    args.copy = copy_option
    args.dry_run = dry_run_option
    args.progress = progress_option
    args.report_file = report_file
    
    # Print a summary of the options
    print("\n=== Summary of options ===")
    print(f"Source directory: {args.source}")
    print(f"Target directory: {args.target}")
    print(f"Operation: {'Copy' if args.copy else 'Move'} files")
    print(f"Mode: {'Simulation (dry run)' if args.dry_run else 'Actual file operation'}")
    print(f"Progress bar: {'Enabled' if args.progress and TQDM_AVAILABLE else 'Disabled'}")
    print(f"Report file: {args.report_file}")
    
    # Final confirmation
    confirm = input("\nProceed with these options? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Operation canceled by user.")
        sys.exit(0)
    
    return args


def get_image_files(source_dir):
    """
    Recursively find all image and video files in the source directory.
    
    Args:
        source_dir (Path): Source directory to search
        
    Returns:
        list: List of image and video file paths
    """
    media_files = []
    
    for root, _, files in os.walk(source_dir):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                media_files.append(file_path)
    
    return media_files


def get_exif_date(file_path):
    """
    Extract the DateTimeOriginal from EXIF data.
    
    Args:
        file_path (Path): Path to the image file
        
    Returns:
        datetime or None: Datetime object from EXIF or None if not available
    """
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            
        if 'EXIF DateTimeOriginal' in tags:
            date_str = str(tags['EXIF DateTimeOriginal'])
            # EXIF date format: YYYY:MM:DD HH:MM:SS
            return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception as e:
        logger.debug(f"Error reading EXIF data from {file_path}: {e}")
    
    return None


def get_video_date(file_path):
    """
    Extract the creation date from video metadata.
    
    Args:
        file_path (Path): Path to the video file
        
    Returns:
        datetime or None: Datetime object from video metadata or None if not available
    """
    if not FFMPEG_AVAILABLE:
        return None
    
    try:
        # Try to get creation date from video metadata using ffmpeg
        probe = ffmpeg.probe(str(file_path))
        
        # Look for creation_time in metadata
        # First check format metadata
        if 'format' in probe and 'tags' in probe['format']:
            tags = probe['format']['tags']
            
            # Check for common creation date tags
            for date_tag in ['creation_time', 'creation_date', 'date', 'date-eng']:
                if date_tag in tags:
                    try:
                        # Try various date formats
                        date_str = tags[date_tag]
                        
                        # Try ISO format
                        try:
                            return datetime.datetime.fromisoformat(date_str.split('.')[0].replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            pass
                        
                        # Try common format used in videos
                        try:
                            return datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                        except ValueError:
                            pass
                        
                        # Try another common format
                        try:
                            return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            pass
                    except Exception:
                        continue
        
        # Next check stream metadata
        if 'streams' in probe:
            for stream in probe['streams']:
                if 'tags' in stream:
                    tags = stream['tags']
                    
                    # Check for common creation date tags in streams
                    for date_tag in ['creation_time', 'creation_date', 'date', 'date-eng']:
                        if date_tag in tags:
                            try:
                                # Try various date formats
                                date_str = tags[date_tag]
                                
                                # Try ISO format
                                try:
                                    return datetime.datetime.fromisoformat(date_str.split('.')[0].replace('Z', '+00:00'))
                                except (ValueError, AttributeError):
                                    pass
                                
                                # Try common format used in videos
                                try:
                                    return datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                                except ValueError:
                                    pass
                                
                                # Try another common format
                                try:
                                    return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    pass
                            except Exception:
                                continue
    
    except Exception as e:
        logger.debug(f"Error reading video metadata from {file_path}: {e}")
    
    return None


def get_file_date(file_path):
    """
    Get the creation date of a file, prioritizing metadata.
    
    Args:
        file_path (Path): Path to the file
        
    Returns:
        datetime: Datetime object representing the file's creation date
    """
    # Determine file type
    file_extension = file_path.suffix.lower()
    
    # For image files, try to get date from EXIF data first
    if file_extension in IMAGE_EXTENSIONS:
        exif_date = get_exif_date(file_path)
        if exif_date:
            return exif_date
    
    # For video files, try to get date from video metadata
    if file_extension in VIDEO_EXTENSIONS:
        video_date = get_video_date(file_path)
        if video_date:
            return video_date
    
    # Fall back to file modification time
    try:
        mtime = file_path.stat().st_mtime
        return datetime.datetime.fromtimestamp(mtime)
    except Exception as e:
        logger.warning(f"Could not get modification time for {file_path}: {e}")
        # Use current time as a last resort
        return datetime.datetime.now()


def create_target_path(target_dir, date):
    """
    Create the target path based on the date.
    
    Args:
        target_dir (Path): Base target directory
        date (datetime): Date to use for directory structure
        
    Returns:
        Path: Target path with year/month/day structure
    """
    year_dir = f"{date.year:04d}"
    month_dir = f"{date.month:02d}"
    day_dir = f"{date.day:02d}"
    
    return target_dir / year_dir / month_dir / day_dir


def get_unique_filename(target_path, filename):
    """
    Handle filename conflicts by adding a unique identifier.
    
    Args:
        target_path (Path): Target directory path
        filename (str): Original filename
        
    Returns:
        str: Unique filename
    """
    if not (target_path / filename).exists():
        return filename
    
    name, ext = os.path.splitext(filename)
    counter = 1
    
    while (target_path / f"{name}_{counter}{ext}").exists():
        counter += 1
    
    return f"{name}_{counter}{ext}"


def process_file(file_path, target_dir, copy=False, dry_run=False):
    """
    Process a single file and move/copy it to the target directory.
    
    Args:
        file_path (Path): Source file path
        target_dir (Path): Base target directory
        copy (bool): Whether to copy instead of move
        dry_run (bool): Whether to simulate the operation
        
    Returns:
        tuple: (success, target_path or None if failed, file_type, date_source)
    """
    try:
        # Determine file type
        file_extension = file_path.suffix.lower()
        if file_extension in IMAGE_EXTENSIONS:
            file_type = "image"
        elif file_extension in VIDEO_EXTENSIONS:
            file_type = "video"
        else:
            file_type = "unknown"
        
        # Get the file's date
        file_date = get_file_date(file_path)
        
        # Determine date source
        if file_extension in IMAGE_EXTENSIONS:
            exif_date = get_exif_date(file_path)
            date_source = "EXIF" if exif_date else "file_mtime"
        elif file_extension in VIDEO_EXTENSIONS:
            video_date = get_video_date(file_path)
            date_source = "video_metadata" if video_date else "file_mtime"
        else:
            date_source = "file_mtime"
        
        # Create target directory structure
        target_path = create_target_path(target_dir, file_date)
        
        if not dry_run:
            # Create target directory if it doesn't exist
            target_path.mkdir(parents=True, exist_ok=True)
        
        # Handle potential filename conflicts
        filename = file_path.name
        unique_filename = get_unique_filename(target_path, filename)
        full_target_path = target_path / unique_filename
        
        # Perform the file operation or simulate it
        if not dry_run:
            if copy:
                shutil.copy2(file_path, full_target_path)
            else:
                shutil.move(file_path, full_target_path)
        
        action = "Would copy" if dry_run and copy else "Would move" if dry_run else "Copied" if copy else "Moved"
        logger.info(f"{action} {file_path} to {full_target_path}")
        
        return True, full_target_path, file_type, date_source
    
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return False, None, "error", "error"


def create_report_file(report_file_path, file_data, dry_run=False):
    """
    Create a CSV report file with details of all processed files.
    
    Args:
        report_file_path (str): Path to the report file
        file_data (list): List of tuples containing file data
        dry_run (bool): Whether this was a dry run
    """
    try:
        with open(report_file_path, 'w', newline='', encoding='utf-8') as csv_file:
            csv_writer = csv.writer(csv_file)
            
            # Write header
            csv_writer.writerow([
                'Original Path', 
                'Target Path', 
                'File Type', 
                'Date Source', 
                'Status', 
                'Operation', 
                'Timestamp'
            ])
            
            # Write data rows
            for data in file_data:
                csv_writer.writerow(data)
            
        logger.info(f"Report file created: {report_file_path}")
        
        if dry_run:
            logger.info("Note: Target paths in the report are simulated and files were not actually moved/copied.")
    
    except Exception as e:
        logger.error(f"Failed to create report file: {e}")


def main():
    """Main function to organize photos and videos."""
    args = get_user_input()
    
    source_dir = Path(args.source)
    target_dir = Path(args.target)
    report_file_path = args.report_file
    
    # Find all media files
    logger.info(f"Scanning for image and video files in {source_dir}...")
    media_files = get_image_files(source_dir)
    file_count = len(media_files)
    logger.info(f"Found {file_count} files to process")
    
    if file_count == 0:
        logger.warning("No image or video files found. Exiting.")
        return
    
    # Process files with optional progress bar
    success_count = 0
    failed_count = 0
    image_count = 0
    video_count = 0
    report_data = []
    start_time = time.time()
    
    if args.progress and TQDM_AVAILABLE:
        # Use tqdm for progress bar if available and requested
        media_files_iter = tqdm(media_files, desc="Processing", unit="file")
    else:
        media_files_iter = media_files
    
    for file_path in media_files_iter:
        success, target_path, file_type, date_source = process_file(file_path, target_dir, args.copy, args.dry_run)
        
        # Update counters
        if success:
            success_count += 1
            if file_type == "image":
                image_count += 1
            elif file_type == "video":
                video_count += 1
        else:
            failed_count += 1
        
        # Add to report data
        status = "Success" if success else "Failed"
        operation = "Copy" if args.copy else "Move"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report_data.append([
            str(file_path),
            str(target_path) if target_path else "N/A",
            file_type,
            date_source,
            status,
            operation,
            timestamp
        ])
    
    # Calculate processing time
    end_time = time.time()
    processing_time = end_time - start_time
    
    # Create report file
    create_report_file(report_file_path, report_data, args.dry_run)
    
    # Print summary
    print("\n=== Processing Summary ===")
    print(f"Total files processed: {file_count}")
    print(f"Successful: {success_count} ({image_count} images, {video_count} videos)")
    print(f"Failed: {failed_count}")
    print(f"Processing time: {processing_time:.2f} seconds")
    print(f"Report file: {report_file_path}")
    
    logger.info(f"Processing complete: {success_count} files processed successfully, {failed_count} failed")
    
    if args.dry_run:
        logger.info("This was a dry run. No files were actually moved or copied.")


if __name__ == "__main__":
    main()
