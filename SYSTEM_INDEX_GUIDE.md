# System Index Scanning - User Guide

## Overview

The Local PC Assistant now supports comprehensive system-wide file indexing, allowing you to search for files, folders, and applications across your entire system using natural language queries.

## Available Commands

### Quick Scan (Fast)

```
scan system
build index
index system
```

Scans common user locations:

- Desktop, Documents, Downloads, Music, Pictures, Videos
- AppData (user profile)
- Program Files and Program Files (x86)
- Applications and shortcuts

**Expected time:** 10-30 seconds  
**Typical results:** 200-500 items

### Full System Scan (Comprehensive)

```
full system scan
scan all drives
scan all
complete system scan
full scan
```

Scans all available local drives with intelligent filtering:

- Automatically detects all local disk drives (C:, D:, E:, etc.)
- Skips system folders, temporary files, and caches
- Includes all user files and applications across all drives
- Applies duplicate detection to avoid indexing same item multiple times

**Expected time:** 2-10 minutes depending on drive size  
**Typical results:** 10,000+ items

### Scan Specific Drive

```
scan C:
scan D
scan E:/
```

Scans a specific drive letter. The assistant accepts:

- `scan C:` (with colon)
- `scan D` (without colon)
- `scan E:/` (with slash)

**Expected time:** Proportional to drive size

## Using the Index

### Find and Open Files

Once you've built an index, search naturally:

```
open visual studio
open forza horizon
find my resume
launch photoshop
open downloads folder
```

The assistant will:

1. Search the index for matching items
2. Show matches with confidence scores
3. Confirm before opening

### Example Workflow

```
You> full system scan
Assistant> Found 3 drive(s): C, D, E
            Scanning drive C:/... ✓ Drive C:/ complete (8,234 items)
            Scanning drive D:/... ✓ Drive D:/ complete (15,402 items)
            Scanning drive E:/... ✓ Drive E:/ complete (4,156 items)
            Full system scan complete!
            Total items indexed: 27,792

You> open forza horizon 3
Assistant> Found 'Forza Horizon 3' (92% match). Would you like me to open it?

You> yes
Assistant> Done: Opened file in Windows: C:\Games\Forza Horizon 3\game.exe
```

## Smart Features

### Duplicate Handling

- When combining scans, duplicates are automatically detected
- Same file on multiple drives = indexed once
- Multiple shortcuts to same app = all stored but ranked

### Intelligent Filtering

The scanner automatically skips:

- Windows system files
- Temporary and cache folders
- Version control directories (.git, node_modules)
- System volume information
- Pagefile and hibernation files

### Fuzzy Matching

- "vizual studio" → finds "Visual Studio"
- "forza" → finds "Forza Horizon 3"
- Partial name matches work too

## Tips for Best Results

1. **Run after major changes** - If you install new software or move files, rescan
2. **Use descriptive names** - Files with clear names are easier to find
3. **Organize your drives** - The index reflects your filesystem structure
4. **Check index stats** - Run "index stats" to see what's indexed

## Troubleshooting

### Index is incomplete

- Try "full system scan" instead of "scan system"
- Check if certain drives are inaccessible (permissions issues)

### Search finds too many results

- Use more specific terms
- Try including the file extension or type

### Search finds nothing

- Verify the item has been indexed ("index stats")
- Try a different name or part of the name
- Rebuild the index with "full system scan"

### Drive not scanning

- Verify the drive letter is correct
- Check that the drive is accessible and not in use
- Ensure you have read permissions
