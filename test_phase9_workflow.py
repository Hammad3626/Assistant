"""Test script for Phase 9 system indexing with unrestricted launches."""

import sys
from pathlib import Path

# Add the assistant module to path
sys.path.insert(0, str(Path(__file__).parent))

from assistant.system_index import SystemIndex
from assistant.index_store import IndexStore, PreferencesStore
from assistant.system_search import SystemSearch
from assistant.core import LocalAssistant


def demo_workflow():
    """Demonstrate Phase 9 indexing workflow."""
    
    print("=== Phase 9 System Indexing Demo ===\n")
    
    # Create a test index with mock items
    print("1. Creating test index with sample items...")
    index = SystemIndex()
    
    # Add some sample items (simulating what would be found during scanning)
    # Using direct IndexedItem creation to avoid file existence checks
    from assistant.system_index import IndexedItem, generate_item_id
    from datetime import datetime
    
    sample_data = [
        ("C:/Program Files/Google/Chrome/chrome.exe", "Chrome", "app", ".exe", 0.8),
        ("C:/Program Files/Microsoft VS Code/Code.exe", "Visual Studio Code", "app", ".exe", 0.8),
        ("C:/Program Files/Adobe/Photoshop/Photoshop.exe", "Photoshop", "app", ".exe", 0.8),
        ("C:/Users/Test/Documents/Resume.pdf", "Resume.pdf", "file", ".pdf", 0.5),
        ("C:/Users/Test/Documents/Resume_Final.pdf", "Resume_Final.pdf", "file", ".pdf", 0.5),
        ("C:/Users/Test/Desktop/Spider-Man", "Spider-Man", "folder", "", 0.6),
        ("C:/Users/Test/Downloads", "Downloads", "folder", "", 0.6),
    ]
    
    iso_time = datetime.now().isoformat()
    
    for full_path, name, item_type, ext, priority in sample_data:
        item = IndexedItem(
            id=generate_item_id(full_path),
            name=name,
            full_path=full_path,
            item_type=item_type,
            file_extension=ext,
            size_bytes=1024 if item_type == "file" else 0,
            created_date=iso_time,
            modified_date=iso_time,
            accessed_date=iso_time,
            drive=full_path[0],
            is_hidden=False,
            is_system=False,
            priority_score=priority,
        )
        index.add_item(item)
    
    # Save index
    index_path = Path("data/test_index.jsonl")
    index_path.parent.mkdir(exist_ok=True)
    
    store = IndexStore(index_path)
    store.save_index(index)
    
    print(f"   ✓ Created index with {index.total_items} items")
    print(f"   ✓ Saved to {index_path}\n")
    
    # Test search
    print("2. Testing search functionality...")
    search = SystemSearch(index)
    
    test_queries = [
        "Chrome",
        "Photoshop",
        "Resume",
        "VS Code",
        "Spider-Man",
        "Downloads",
    ]
    
    for query in test_queries:
        results = search.search(query, limit=3)
        if results:
            top = results[0]
            print(f"   '{query}' -> Found: {top.item.name} ({top.score:.0%} match)")
        else:
            print(f"   '{query}' -> No matches")
    
    print()
    
    # Test fuzzy matching
    print("3. Testing fuzzy matching...")
    fuzzy_queries = [
        "Chrom",      # Substring
        "photshop",   # Typo
        "Code",       # Partial
        "Spiderman",  # No hyphen
    ]
    
    for query in fuzzy_queries:
        results = search.search(query, limit=1)
        if results:
            match = results[0]
            print(f"   '{query}' -> {match.item.name} (type: {match.match_type}, score: {match.score:.0%})")
        else:
            print(f"   '{query}' -> No match")
    
    print()
    
    # Test preference tracking
    print("4. Testing preference tracking...")
    prefs_path = Path("data/test_preferences.json")
    prefs = PreferencesStore(prefs_path)
    
    # Simulate accessing items
    items = index.get_all_items()
    for item in items[:3]:
        prefs.record_access(item.id)
        prefs.record_access(item.id)
    
    print(f"   ✓ Recorded access history")
    print(f"   ✓ Top items: {prefs.get_frequently_accessed(limit=3)}")
    print()
    
    # Test ranking with preferences
    print("5. Testing ranking with preferences...")
    search_with_prefs = SystemSearch(index)
    results = search_with_prefs.search("Resume", limit=5)
    print(f"   Raw search results for 'Resume':")
    for i, match in enumerate(results, 1):
        print(f"      {i}. {match.item.name} (score: {match.score:.2f})")
    
    # Get access counts
    access_counts = {}
    for item in items:
        count = prefs.get_access_count(item.id)
        if count > 0:
            access_counts[item.id] = count
    
    results_ranked = search_with_prefs.search("Resume", limit=5)
    results_ranked = search_with_prefs.rank_results(results_ranked, access_counts=access_counts)
    print(f"   Ranked results with preferences:")
    for i, match in enumerate(results_ranked, 1):
        print(f"      {i}. {match.item.name} (score: {match.score:.2f})")
    
    print("\n✓ Phase 9 workflow test complete!")
    print("\nNext steps:")
    print("  - User runs: 'scan system' to populate index with actual files")
    print("  - User runs: 'open Spider-Man' to search index")
    print("  - Assistant finds match and asks for confirmation")
    print("  - User responds: 'yes' to execute with full path")
    print("  - Access count is recorded for future ranking")


if __name__ == "__main__":
    demo_workflow()
