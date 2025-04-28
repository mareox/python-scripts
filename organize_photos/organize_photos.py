#!/usr/bin/env python3
"""
organize_photos.py - A script to organize photos by date into a structured directory.

This script organizes image files from a source directory (and its subdirectories)
into a target directory with the structure year/month/day based on the image creation date.
Creation date is extracted from EXIF data if available, otherwise file modification time is used.

The script will prompt for:
- Source directory containing images
- Target directory for organized images
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

# Optional import for progress bar
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

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


def get_user_input():
    """Prompt user for source and target directories and options."""
    print("\n=== Photo Organizer ===")
    print("This script organizes photos by date based on EXIF data or file modification time.\n")
    
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
    
    # Create a class-like object to mimic the args structure
    class Args:
        pass
    
    args = Args()
    args.source = source_dir
    args.target = target_dir
    args.copy = copy_option
    args.dry_run = dry_run_option
    args.progress = progress_option
    
    # Print a summary of the options
    print("\n=== Summary of options ===")
    print(f"Source directory: {args.source}")
    print(f"Target directory: {args.target}")
    print(f"Operation: {'Copy' if args.copy else 'Move'} files")
    print(f"Mode: {'Simulation (dry run)' if args.dry_run else 'Actual file operation'}")
    print(f"Progress bar: {'Enabled' if args.progress and TQDM_AVAILABLE else 'Disabled'}")
    
    # Final confirmation
    confirm = input("\nProceed with these options? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Operation canceled by user.")
        sys.exit(0)
    
    return args


def get_image_files(source_dir):
    """
    Recursively find all image files in the source directory.
    
    Args:
        source_dir (Path): Source directory to search
        
    Returns:
        list: List of image file paths
    """
    image_files = []
    
    for root, _, files in os.walk(source_dir):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in IMAGE_EXTENSIONS:
                image_files.append(file_path)
    
    return image_files


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


def get_file_date(file_path):
    """
    Get the creation date of a file, prioritizing EXIF data.
    
    Args:
        file_path (Path): Path to the image file
        
    Returns:
        datetime: Datetime object representing the file's creation date
    """
    # Try to get date from EXIF data first
    exif_date = get_exif_date(file_path)
    if exif_date:
        return exif_date
    
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
    Process a single image file and move/copy it to the target directory.
    
    Args:
        file_path (Path): Source file path
        target_dir (Path): Base target directory
        copy (bool): Whether to copy instead of move
        dry_run (bool): Whether to simulate the operation
        
    Returns:
        tuple: (success, target_path or None if failed)
    """
    try:
        # Get the file's date
        file_date = get_file_date(file_path)
        
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
        
        return True, full_target_path
    
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return False, None


def main():
    """Main function to organize photos."""
    args = get_user_input()
    
    source_dir = Path(args.source)
    target_dir = Path(args.target)
    
    # Find all image files
    logger.info(f"Scanning for image files in {source_dir}...")
    image_files = get_image_files(source_dir)
    file_count = len(image_files)
    logger.info(f"Found {file_count} image files")
    
    if file_count == 0:
        logger.warning("No image files found. Exiting.")
        return
    
    # Process files with optional progress bar
    success_count = 0
    failed_count = 0
    
    if args.progress and TQDM_AVAILABLE:
        # Use tqdm for progress bar if available and requested
        image_files_iter = tqdm(image_files, desc="Processing", unit="file")
    else:
        image_files_iter = image_files
    
    for file_path in image_files_iter:
        success, _ = process_file(file_path, target_dir, args.copy, args.dry_run)
        if success:
            success_count += 1
        else:
            failed_count += 1
    
    # Print summary
    logger.info(f"Processing complete: {success_count} files processed successfully, {failed_count} failed")
    
    if args.dry_run:
        logger.info("This was a dry run. No files were actually moved or copied.")


if __name__ == "__main__":
    main()
