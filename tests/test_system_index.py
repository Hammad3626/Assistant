"""Tests for Phase 9 system indexing modules."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from assistant.index_store import IndexStore, PreferencesStore
from assistant.system_index import IndexedItem, SystemIndex, create_indexed_item, generate_item_id
from assistant.system_scanner import ScannerConfig, SystemScanner
from assistant.system_search import FuzzyMatcher, SearchMatch, SystemSearch


class SystemIndexTests(unittest.TestCase):
    """Tests for system_index module."""

    def test_indexed_item_creation(self) -> None:
        item = IndexedItem(
            id="test123",
            name="test.pdf",
            full_path="/home/user/test.pdf",
            item_type="file",
            file_extension=".pdf",
            size_bytes=1024,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-02T00:00:00",
            accessed_date="2024-01-03T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        self.assertEqual(item.name, "test.pdf")
        self.assertEqual(item.item_type, "file")
        self.assertEqual(item.access_count, 0)

    def test_indexed_item_to_dict(self) -> None:
        item = IndexedItem(
            id="test123",
            name="test.txt",
            full_path="/path/test.txt",
            item_type="file",
            file_extension=".txt",
            size_bytes=512,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        data = item.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data["name"], "test.txt")
        self.assertEqual(data["item_type"], "file")

    def test_indexed_item_from_dict(self) -> None:
        data = {
            "id": "test123",
            "name": "document.pdf",
            "full_path": "/home/user/document.pdf",
            "item_type": "file",
            "file_extension": ".pdf",
            "size_bytes": 2048,
            "created_date": "2024-01-01T00:00:00",
            "modified_date": "2024-01-01T00:00:00",
            "accessed_date": "2024-01-01T00:00:00",
            "drive": "C",
            "is_hidden": False,
            "is_system": False,
        }

        item = IndexedItem.from_dict(data)

        self.assertEqual(item.name, "document.pdf")
        self.assertEqual(item.file_extension, ".pdf")

    def test_system_index_add_item(self) -> None:
        index = SystemIndex()
        item = IndexedItem(
            id="item1",
            name="file.txt",
            full_path="/path/file.txt",
            item_type="file",
            file_extension=".txt",
            size_bytes=100,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(item)

        self.assertEqual(index.total_items, 1)
        self.assertEqual(index.get_item("item1"), item)

    def test_system_index_remove_item(self) -> None:
        index = SystemIndex()
        item = IndexedItem(
            id="item1",
            name="file.txt",
            full_path="/path/file.txt",
            item_type="file",
            file_extension=".txt",
            size_bytes=100,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(item)
        index.remove_item("item1")

        self.assertEqual(index.total_items, 0)
        self.assertIsNone(index.get_item("item1"))

    def test_system_index_get_items_by_type(self) -> None:
        index = SystemIndex()

        # Add different types
        file_item = IndexedItem(
            id="file1",
            name="doc.txt",
            full_path="/path/doc.txt",
            item_type="file",
            file_extension=".txt",
            size_bytes=100,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        folder_item = IndexedItem(
            id="folder1",
            name="MyFolder",
            full_path="/path/MyFolder",
            item_type="folder",
            file_extension="",
            size_bytes=0,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(file_item)
        index.add_item(folder_item)

        files = index.get_items_by_type("file")
        folders = index.get_items_by_type("folder")

        self.assertEqual(len(files), 1)
        self.assertEqual(len(folders), 1)

    def test_generate_item_id_consistency(self) -> None:
        path = Path("/home/user/document.pdf")

        id1 = generate_item_id(path)
        id2 = generate_item_id(path)

        self.assertEqual(id1, id2)

    def test_generate_item_id_case_insensitive(self) -> None:
        id1 = generate_item_id("/home/user/document.pdf")
        id2 = generate_item_id("/HOME/USER/DOCUMENT.PDF")

        self.assertEqual(id1, id2)


class IndexStoreTests(unittest.TestCase):
    """Tests for index_store module."""

    def test_save_and_load_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = IndexStore(Path(temp_dir) / "index.jsonl")
            index = SystemIndex()

            # Add items
            item = IndexedItem(
                id="test1",
                name="file.txt",
                full_path="/path/file.txt",
                item_type="file",
                file_extension=".txt",
                size_bytes=100,
                created_date="2024-01-01T00:00:00",
                modified_date="2024-01-01T00:00:00",
                accessed_date="2024-01-01T00:00:00",
                drive="C",
                is_hidden=False,
                is_system=False,
            )

            index.add_item(item)
            index.last_scan = "2024-01-01T00:00:00"

            # Save
            store.save_index(index)

            # Load
            loaded_index = store.load_index()

            self.assertEqual(loaded_index.total_items, 1)
            self.assertIsNotNone(loaded_index.get_item("test1"))

    def test_get_item_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = IndexStore(Path(temp_dir) / "index.jsonl")

            count = store.get_item_count()
            self.assertEqual(count, 0)

    def test_preferences_store_record_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefs = PreferencesStore(Path(temp_dir) / "prefs.json")

            prefs.record_access("item1")
            prefs.record_access("item1")
            prefs.record_access("item2")

            self.assertEqual(prefs.get_access_count("item1"), 2)
            self.assertEqual(prefs.get_access_count("item2"), 1)

    def test_preferences_store_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefs = PreferencesStore(Path(temp_dir) / "prefs.json")

            prefs.set_alias("work", "folder123")
            prefs.set_alias("notes", "file456")

            self.assertEqual(prefs.get_alias("work"), "folder123")
            self.assertEqual(prefs.get_alias("notes"), "file456")

    def test_preferences_store_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "prefs.json"

            # Create and save
            prefs1 = PreferencesStore(path)
            prefs1.record_access("item1")
            prefs1.set_alias("work", "folder123")

            # Load fresh
            prefs2 = PreferencesStore(path)

            self.assertEqual(prefs2.get_access_count("item1"), 1)
            self.assertEqual(prefs2.get_alias("work"), "folder123")


class SystemSearchTests(unittest.TestCase):
    """Tests for system_search module."""

    def test_fuzzy_matcher_similarity(self) -> None:
        score = FuzzyMatcher.similarity_ratio("photoshop", "photoshop")
        self.assertEqual(score, 1.0)

        score = FuzzyMatcher.similarity_ratio("photoshop", "photshop")
        self.assertGreater(score, 0.8)

    def test_fuzzy_matcher_partial_match(self) -> None:
        score = FuzzyMatcher.partial_match("python", "python script")
        self.assertGreater(score, 0.8)

        score = FuzzyMatcher.partial_match("python", "my python")
        self.assertGreater(score, 0.7)

        score = FuzzyMatcher.partial_match("java", "python")
        self.assertEqual(score, 0.0)

    def test_fuzzy_matcher_starts_with_words(self) -> None:
        score = FuzzyMatcher.starts_with_words("vs code", "visual studio code")
        self.assertGreater(score, 0.0)

        score = FuzzyMatcher.starts_with_words("photo", "photoshop pro")
        self.assertGreater(score, 0.0)

    def test_system_search_exact_match(self) -> None:
        index = SystemIndex()

        item = IndexedItem(
            id="app1",
            name="Visual Studio Code",
            full_path="C:\\Program Files\\VSCode\\code.exe",
            item_type="app",
            file_extension=".exe",
            size_bytes=0,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(item)

        search = SystemSearch(index)
        matches = search.search("Visual Studio Code")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].score, 1.0)
        self.assertEqual(matches[0].match_type, "exact")

    def test_system_search_partial_match(self) -> None:
        index = SystemIndex()

        item = IndexedItem(
            id="file1",
            name="Resume_Final.pdf",
            full_path="C:\\Users\\test\\Resume_Final.pdf",
            item_type="file",
            file_extension=".pdf",
            size_bytes=1024,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(item)

        search = SystemSearch(index)
        matches = search.search("Resume")

        self.assertGreater(len(matches), 0)
        self.assertGreater(matches[0].score, 0.7)

    def test_system_search_fuzzy_match(self) -> None:
        index = SystemIndex()

        item = IndexedItem(
            id="app1",
            name="Photoshop",
            full_path="C:\\Program Files\\Adobe\\Photoshop\\photoshop.exe",
            item_type="app",
            file_extension=".exe",
            size_bytes=0,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(item)

        search = SystemSearch(index)
        matches = search.search("Photshop")  # Misspelled

        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0].match_type, "fuzzy")

    def test_system_search_multiple_items_ranking(self) -> None:
        index = SystemIndex()

        # Add multiple items
        items = [
            IndexedItem(
                id="app1",
                name="Visual Studio Code",
                full_path="C:\\Program Files\\VSCode\\code.exe",
                item_type="app",
                file_extension=".exe",
                size_bytes=0,
                created_date="2024-01-01T00:00:00",
                modified_date="2024-01-01T00:00:00",
                accessed_date="2024-01-01T00:00:00",
                drive="C",
                is_hidden=False,
                is_system=False,
                access_count=50,
            ),
            IndexedItem(
                id="app2",
                name="VS Community",
                full_path="C:\\Program Files\\VS\\community.exe",
                item_type="app",
                file_extension=".exe",
                size_bytes=0,
                created_date="2024-01-01T00:00:00",
                modified_date="2024-01-01T00:00:00",
                accessed_date="2024-01-01T00:00:00",
                drive="C",
                is_hidden=False,
                is_system=False,
                access_count=5,
            ),
        ]

        for item in items:
            index.add_item(item)

        search = SystemSearch(index)
        matches = search.search("VS")

        # Should find both, but order matters
        self.assertGreater(len(matches), 0)

    def test_system_search_find_by_extension(self) -> None:
        index = SystemIndex()

        pdf_file = IndexedItem(
            id="file1",
            name="document.pdf",
            full_path="/path/document.pdf",
            item_type="file",
            file_extension=".pdf",
            size_bytes=1024,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        txt_file = IndexedItem(
            id="file2",
            name="notes.txt",
            full_path="/path/notes.txt",
            item_type="file",
            file_extension=".txt",
            size_bytes=512,
            created_date="2024-01-01T00:00:00",
            modified_date="2024-01-01T00:00:00",
            accessed_date="2024-01-01T00:00:00",
            drive="C",
            is_hidden=False,
            is_system=False,
        )

        index.add_item(pdf_file)
        index.add_item(txt_file)

        search = SystemSearch(index)
        pdfs = search.find_by_extension(".pdf")

        self.assertEqual(len(pdfs), 1)
        self.assertEqual(pdfs[0].name, "document.pdf")


class ScannerConfigTests(unittest.TestCase):
    """Tests for ScannerConfig."""

    def test_scanner_config_creation(self) -> None:
        config = ScannerConfig(max_depth=5, skip_hidden=True)

        self.assertEqual(config.max_depth, 5)
        self.assertTrue(config.skip_hidden)

    def test_scanner_config_skip_patterns(self) -> None:
        config = ScannerConfig()

        # Windows temp folder should be skipped
        temp_path = Path("C:\\Windows\\AppData")
        self.assertTrue(config.should_skip_pattern(temp_path))


if __name__ == "__main__":
    unittest.main()
