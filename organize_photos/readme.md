# Photo & Video Organizer - Installation and Usage Guide

## Description
This Python script organizes image and video files from multiple folders into a structured directory based on their creation date. The script prioritizes metadata (EXIF for images, embedded metadata for videos) for determining the creation date and organizes files into a directory structure of `year/month/day`.

## Features
- Supports both photo and video files
- Interactive prompts for all options and paths
- Organizes media based on creation date from metadata (falls back to file modification time)
- Creates a structured directory: `year<####>/month<##>/day<##>` (e.g., `2023/10/15`)
- Handles file name conflicts with unique identifiers
- Supports recursive processing of nested folders
- Options for copying instead of moving files
- Dry-run mode to simulate organization without modifying files
- Progress bar for large collections (if tqdm is installed)
- Generates a detailed CSV report of all processed files

## Installation

### Prerequisites
- Python 3.6 or higher

### Required Packages
Install the required packages using pip:

```bash
pip install exifread
```

### Optional Packages
For progress bar support:
```bash
pip install tqdm
```

For video metadata extraction:
```bash
pip install ffmpeg-python
```

## Usage

### Running the Script
Simply run the script with Python and follow the interactive prompts:

```bash
python organize_photos.py
```

### Interactive Prompts
The script will guide you through several prompts:

1. **Source Directory**: Enter the path to the directory containing your images and videos
2. **Target Directory**: Enter the path where you want to create the organized folder structure
3. **Copy Option**: Choose whether to copy files instead of moving them
4. **Dry Run**: Choose whether to simulate the operation without making actual changes
5. **Progress Bar**: Choose whether to show a progress bar during processing (if tqdm is installed)
6. **Report File**: Enter the path for the CSV report file (default: 'organization_report.csv')

After entering all options, the script will display a summary and ask for confirmation before proceeding.

### Example Interactive Session

```
=== Photo & Video Organizer ===
This script organizes photos and videos by date based on metadata or file modification time.

Enter source directory path: ~/Media
Enter target directory path: ~/Organized_Media
Target directory doesn't exist. Create it now? (y/n): y
Created target directory: /home/user/Organized_Media
Copy files instead of moving them? (y/n): n
Simulate without actually moving/copying files? (y/n): y
Show progress bar during processing? (y/n): y
Enter path for the report file (leave empty for default 'organization_report.csv'): media_report.csv

=== Summary of options ===
Source directory: /home/user/Media
Target directory: /home/user/Organized_Media
Operation: Move files
Mode: Simulation (dry run)
Progress bar: Enabled
Report file: media_report.csv

Proceed with these options? (y/n): y
```

## Report File

The script generates a detailed CSV report with information about each processed file. The report includes:

- **Original Path**: The original location of the file
- **Target Path**: Where the file was moved/copied to
- **File Type**: Whether the file is an image, video, or unknown
- **Date Source**: Where the creation date was extracted from (EXIF, video_metadata, or file_mtime)
- **Status**: Whether the operation was successful
- **Operation**: Whether the file was moved or copied
- **Timestamp**: When the operation was performed

Example report content:
```
Original Path,Target Path,File Type,Date Source,Status,Operation,Timestamp
/home/user/Media/vacation/DSC0001.jpg,/home/user/Organized_Media/2023/07/15/DSC0001.jpg,image,EXIF,Success,Move,2023-10-25 14:32:45
/home/user/Media/videos/trip.mp4,/home/user/Organized_Media/2023/07/15/trip.mp4,video,video_metadata,Success,Move,2023-10-25 14:32:47
/home/user/Media/party.jpg,/home/user/Organized_Media/2023/09/22/party.jpg,image,file_mtime,Success,Move,2023-10-25 14:32:48
```

The report file is useful for:
- Keeping track of where your files were moved
- Identifying files that couldn't be processed
- Understanding which metadata was used for organizing
- Creating a backup record of your organization process

## Supported File Types

### Image Formats
- `.jpg`, `.jpeg` - JPEG images
- `.png` - PNG images
- `.gif` - GIF images
- `.bmp` - Bitmap images
- `.tiff`, `.tif` - TIFF images
- `.heic` - High-Efficiency Image Format
- `.raw`, `.cr2`, `.nef`, `.arw` - Various raw camera formats

### Video Formats
- `.mp4` - MPEG-4 video
- `.mov` - QuickTime video
- `.avi` - AVI video
- `.wmv` - Windows Media Video
- `.mkv` - Matroska video
- `.flv` - Flash video
- `.webm` - WebM video
- `.m4v` - iTunes video
- `.3gp` - 3GPP video
- `.mpg`, `.mpeg` - MPEG video
- `.mts`, `.m2ts` - AVCHD video

## Notes and Limitations

- For video files, the script requires the `ffmpeg-python` package to extract metadata
- If metadata extraction fails, the file modification time is used instead
- The target directory should not be a subdirectory of the source directory
- Files with the same name in the same target directory will be renamed with a unique identifier
- When using dry-
