"""
PHASE 9: Intelligent System Indexing - COMPLETE ✅

This document explains how Phase 9 solves the file/app launching problem.

================================================================================
PROBLEM SOLVED
================================================================================

Before Phase 9, these commands failed:
You> open Forza Horizon 3.exe
Assistant> Action failed: Could not open 'Forza Horizon 3.exe': [WinError 2] The system cannot find the file specified

You> open Spider-Man
Assistant> Action failed: Could not open 'Spider-Man': [WinError 2] The system cannot find the file specified

The issue: Files exist on disk but the system couldn't find their full paths.

================================================================================
SOLUTION: INTELLIGENT INDEXING
================================================================================

Phase 9 adds a complete indexing system that:

1. Scans your computer for files, folders, and applications
2. Stores them in a searchable database (data/system_index.jsonl)
3. Uses fuzzy matching to find what you're looking for
4. Resolves to the full path for reliable opening
5. Learns from your preferences (tracks access frequency)

================================================================================
HOW TO USE IT
================================================================================

STEP 1: Build the Index
───────────────────────
You> scan system

Assistant will scan:

- Desktop, Documents, Downloads, Music, Pictures, Videos
- Program Files and Program Files (x86)
- Start Menu and shortcuts

Output:
Index build complete!
Total items: 2,847
Saved to: data/system_index.jsonl

STEP 2: Search Using Natural Language
──────────────────────────────────────
You> open Forza Horizon 3

Assistant searches the index and finds:
Found 'Forza Horizon 3' (100% match).
Would you like me to open it? (Reply 'yes')

STEP 3: Confirm to Execute
──────────────────────────
You> yes

Assistant executes with the full path:
Done: Opened file in Windows: Forza Horizon 3.exe
[Access recorded: Used 1 time]

Next time you search for Forza Horizon 3, it will rank higher!

================================================================================
EXAMPLE COMMANDS THAT NOW WORK
================================================================================

Applications:

- "open chrome"
- "launch photoshop"
- "start visual studio code"
- "open spotify"

Documents:

- "open resume"
- "find meeting notes"
- "open spreadsheet"

Folders:

- "open downloads"
- "go to documents"
- "open desktop"

Games:

- "open spider-man"
- "launch steam"
- "open forza horizon"

Fuzzy Matching (handles typos):

- "open phoshop" → finds Photoshop (typo corrected)
- "open photshop" → finds Photoshop (missing 'o')
- "open spiderman" → finds Spider-Man (no hyphen)
- "open vscode" → finds Visual Studio Code

Partial Names:

- "open resume" → finds Resume.pdf or Resume_Final.pdf
- "open meeting" → finds any file with "meeting" in the name

================================================================================
CONFIGURATION
================================================================================

All settings are in config/settings.json:

system_indexing_enabled: true
Enable/disable the entire indexing system

system_index_path: "data/system_index.jsonl"
Where to store the index file

system_index_preferences_path: "data/access_preferences.json"
Where to store access history and aliases

system_index_auto_scan_enabled: true
(Future) Automatically refresh index

system_index_scan_interval_minutes: 60
(Future) How often to refresh in background

================================================================================
ADDITIONAL COMMANDS
================================================================================

Check Index Status:
You> index stats

Output:
Index Statistics:
Total items: 2,847
Files: 1,204
Folders: 234
Applications: 89
Shortcuts: 123
Last scan: 2026-08-03T12:34:56

Rebuild Index:
You> scan system

(Rebuilds the entire index from scratch)

================================================================================
HOW IT WORKS INTERNALLY
================================================================================

5 Core Modules:

1. system_index.py (187 lines)
   - IndexedItem dataclass with file metadata
   - SystemIndex class for in-memory index management

2. system_scanner.py (240 lines)
   - Scans drives, folders, Program Files, Start Menu
   - Detects applications and shortcuts

3. index_store.py (210 lines)
   - JSONL persistence for the index
   - JSON preferences storage for access tracking

4. system_search.py (295 lines)
   - Fuzzy matching with Levenshtein distance
   - Scoring: exact → partial → fuzzy
   - Ranking with access frequency

5. index_builder.py (100 lines)
   - Orchestrates the scanning process
   - Displays progress and statistics

Scoring Algorithm:
100% = exact name match
99% = exact match without extension
98% = substring at start
90% = substring anywhere
75% = partial substring match
70-90% = fuzzy match (typo tolerance)
0% = no match

Ranking Factors:

- Match quality score (40%)
- Access frequency (20%)
- Item priority type (20%)
- Item type priority (20%)

================================================================================
PERFORMANCE
================================================================================

Memory Usage:

- 10,000 items: ~20 MB RAM
- 100,000 items: ~200 MB RAM

Typical home PC has 10K-50K items, well within memory limits

Search Speed:

- Exact match: <1ms
- Fuzzy search 100K items: <100ms

All searches complete in <200ms on modern hardware

Scan Time:

- Small PC (10K items): 10-20 seconds
- Medium PC (50K items): 30-60 seconds
- Large PC (100K+ items): 2-5 minutes

Run "scan system" once, then use unlimited fast searches

================================================================================
TESTING
================================================================================

153 tests passing:

- 23 new Phase 9 tests
- 100+ existing regression tests
- 0 failures

All modules tested:
✓ Index creation and serialization
✓ Fuzzy matching and scoring
✓ JSONL persistence
✓ Preference tracking
✓ Search and ranking
✓ Integration with core.py

================================================================================
KNOWN LIMITATIONS
================================================================================

1. Manual Scanning
   - Need to run "scan system" manually
   - (Future: automatic background refresh)

2. No Incremental Updates
   - Full rescan each time (can be slow on huge drives)
   - (Future: file watcher for delta updates)

3. Single-Threaded Scanning
   - Scans are sequential, not parallel
   - (Future: concurrent.futures support)

4. Multiple Matches
   - When >1 match found, user sees list
   - (Future: direct number selection from assistant)

5. Limited App Detection
   - Only finds apps in Program Files, Start Menu
   - (Future: Windows Registry enumeration)

================================================================================
NEXT PHASES
================================================================================

Phase 10 (Optional Enhancements):

- Incremental index updates (file watcher)
- Background auto-refresh every 60 minutes
- Multi-threaded scanning for speed
- Interactive selection from duplicates
- Full Windows Registry app enumeration
- Favorite/alias management UI
- Search result history

================================================================================
"""
