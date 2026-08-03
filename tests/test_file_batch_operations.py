"""
Tests for Phase 5.2: File Batch Operations Workflow
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from assistant.file_batch_operations import (
    list_files,
    search_files_by_content,
    plan_rename_operation,
    plan_replace_operation,
    plan_delete_operation,
    execute_batch_operations,
    batch_rename_files,
    batch_replace_content,
    FileOperation,
    BatchOperationResult,
)


class FileListingTests(unittest.TestCase):
    """Test file listing and searching."""
    
    def setUp(self):
        """Create temporary directory with test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        
        # Create test files
        (self.test_dir / "file1.txt").write_text("content1")
        (self.test_dir / "file2.txt").write_text("content2")
        (self.test_dir / "file3.py").write_text("def func(): pass")
        (self.test_dir / "subdir").mkdir()
        (self.test_dir / "subdir" / "nested.txt").write_text("nested content")
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_list_all_files(self):
        """List all files in directory."""
        files = list_files(self.test_dir, recursive=False)
        self.assertEqual(len(files), 3)
        self.assertTrue(all(f.is_file() for f in files))
    
    def test_list_with_pattern(self):
        """List files matching pattern."""
        files = list_files(self.test_dir, pattern="*.txt", recursive=False)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.suffix == ".txt" for f in files))
    
    def test_list_recursive(self):
        """List files recursively in subdirectories."""
        files = list_files(self.test_dir, pattern="*.txt", recursive=True)
        self.assertEqual(len(files), 3)
    
    def test_list_nonexistent_directory(self):
        """Handle non-existent directory gracefully."""
        files = list_files(Path("/nonexistent/path"))
        self.assertEqual(len(files), 0)
    
    def test_search_by_content(self):
        """Find files containing specific text."""
        files = search_files_by_content(self.test_dir, "content", recursive=True)
        self.assertEqual(len(files), 3)  # All .txt files contain "content"
    
    def test_search_by_specific_text(self):
        """Find files with specific unique text."""
        files = search_files_by_content(self.test_dir, "nested", recursive=True)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "nested.txt")
    
    def test_search_no_matches(self):
        """Search with no matching files."""
        files = search_files_by_content(self.test_dir, "NONEXISTENT", recursive=True)
        self.assertEqual(len(files), 0)


class OperationPlanningTests(unittest.TestCase):
    """Test file operation planning."""
    
    def setUp(self):
        """Create temporary directory with test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.test_file = self.test_dir / "test.txt"
        self.test_file.write_text("original content")
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_plan_rename_operation(self):
        """Plan a file rename."""
        op = plan_rename_operation(self.test_file, "renamed.txt")
        
        self.assertEqual(op.operation, "rename")
        self.assertEqual(op.status, "pending")
        self.assertEqual(op.details["new_name"], "renamed.txt")
        self.assertIn("renamed.txt", op.preview)
    
    def test_plan_rename_same_name(self):
        """Plan rename with same name skips operation."""
        op = plan_rename_operation(self.test_file, "test.txt")
        
        self.assertEqual(op.status, "skipped")
        self.assertIn("No change", op.preview)
    
    def test_plan_replace_operation(self):
        """Plan a text replacement."""
        op = plan_replace_operation(self.test_file, "original", "modified")
        
        self.assertEqual(op.operation, "replace")
        self.assertEqual(op.status, "pending")
        self.assertEqual(op.details["old_text"], "original")
        self.assertEqual(op.details["new_text"], "modified")
        self.assertEqual(op.details["occurrences"], 1)
    
    def test_plan_replace_no_match(self):
        """Plan replace with no matching text skips."""
        op = plan_replace_operation(self.test_file, "NOTFOUND", "replacement")
        
        self.assertEqual(op.status, "skipped")
        self.assertIn("No match", op.preview)
    
    def test_plan_delete_operation(self):
        """Plan a file deletion."""
        op = plan_delete_operation(self.test_file)
        
        self.assertEqual(op.operation, "delete")
        self.assertEqual(op.status, "pending")
        self.assertIn("Delete", op.preview)


class BatchExecutionTests(unittest.TestCase):
    """Test batch operation execution."""
    
    def setUp(self):
        """Create temporary directory with test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.backup_dir = self.test_dir / "backups"
        
        # Create test files
        self.file1 = self.test_dir / "file1.txt"
        self.file1.write_text("content1")
        self.file2 = self.test_dir / "file2.txt"
        self.file2.write_text("content2")
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_execute_rename(self):
        """Execute a rename operation."""
        op = plan_rename_operation(self.file1, "renamed.txt")
        result = execute_batch_operations([op])
        
        self.assertTrue((self.test_dir / "renamed.txt").exists())
        self.assertFalse(self.file1.exists())
        self.assertEqual(result.successful, 1)
        self.assertEqual(result.failed, 0)
    
    def test_execute_replace(self):
        """Execute a text replacement."""
        op = plan_replace_operation(self.file1, "content1", "REPLACED")
        result = execute_batch_operations([op])
        
        content = self.file1.read_text()
        self.assertIn("REPLACED", content)
        self.assertNotIn("content1", content)
        self.assertEqual(result.successful, 1)
    
    def test_execute_delete(self):
        """Execute a file deletion."""
        op = plan_delete_operation(self.file1)
        result = execute_batch_operations([op])
        
        self.assertFalse(self.file1.exists())
        self.assertEqual(result.successful, 1)
    
    def test_execute_with_approval_callback_rejected(self):
        """Reject operations in approval callback."""
        op = plan_rename_operation(self.file1, "renamed.txt")
        
        def reject_callback(ops):
            return False
        
        result = execute_batch_operations([op], approval_callback=reject_callback)
        
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.successful, 0)
        self.assertTrue(self.file1.exists())  # File should not be renamed
    
    def test_execute_with_approval_callback_approved(self):
        """Approve operations in callback."""
        op = plan_rename_operation(self.file1, "renamed.txt")
        
        def approve_callback(ops):
            return True
        
        result = execute_batch_operations([op], approval_callback=approve_callback)
        
        self.assertEqual(result.successful, 1)
        self.assertTrue((self.test_dir / "renamed.txt").exists())
    
    def test_execute_with_backup(self):
        """Execute operations with backup creation."""
        self.backup_dir.mkdir(exist_ok=True)
        op = plan_delete_operation(self.file1)
        result = execute_batch_operations([op], backup_dir=self.backup_dir)
        
        # File should be deleted
        self.assertFalse(self.file1.exists())
        # But backup should exist
        self.assertTrue((self.backup_dir / "file1.txt").exists())
        self.assertEqual(result.successful, 1)
    
    def test_execute_multiple_operations(self):
        """Execute multiple operations in sequence."""
        op1 = plan_replace_operation(self.file1, "content1", "MODIFIED")
        op2 = plan_rename_operation(self.file2, "renamed.txt")
        
        result = execute_batch_operations([op1, op2])
        
        self.assertEqual(result.successful, 2)
        self.assertEqual(result.total_operations, 2)
        self.assertIn("MODIFIED", self.file1.read_text())
        self.assertTrue((self.test_dir / "renamed.txt").exists())
    
    def test_execute_mixed_skipped_and_executed(self):
        """Execute batch with skipped and executed operations."""
        op1 = plan_replace_operation(self.file1, "NOTFOUND", "replacement")  # Will skip
        op2 = plan_rename_operation(self.file2, "renamed.txt")  # Will execute
        
        result = execute_batch_operations([op1, op2])
        
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.successful, 1)
    
    def test_execute_missing_file_error(self):
        """Handle missing file gracefully."""
        fake_file = self.test_dir / "nonexistent.txt"
        op = plan_rename_operation(fake_file, "new.txt")
        result = execute_batch_operations([op])
        
        self.assertEqual(result.failed, 1)
        self.assertGreater(len(result.errors), 0)


class BatchRenameTests(unittest.TestCase):
    """Test batch rename functionality."""
    
    def setUp(self):
        """Create temporary directory with test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        
        (self.test_dir / "old_name1.txt").write_text("content1")
        (self.test_dir / "old_name2.txt").write_text("content2")
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_batch_rename_with_transform(self):
        """Rename multiple files using transform function."""
        def transform(name):
            return name.replace("old_", "new_")
        
        result = batch_rename_files(self.test_dir, pattern="*.txt", name_transform=transform)
        
        self.assertEqual(result.successful, 2)
        self.assertTrue((self.test_dir / "new_name1.txt").exists())
        self.assertTrue((self.test_dir / "new_name2.txt").exists())
    
    def test_batch_rename_with_approval(self):
        """Batch rename with user approval."""
        def transform(name):
            return name.replace("old_", "approved_")
        
        def approve_callback(ops):
            self.assertEqual(len(ops), 2)
            return True
        
        result = batch_rename_files(
            self.test_dir,
            pattern="*.txt",
            name_transform=transform,
            approval_callback=approve_callback
        )
        
        self.assertEqual(result.successful, 2)


class BatchReplaceTests(unittest.TestCase):
    """Test batch replace functionality."""
    
    def setUp(self):
        """Create temporary directory with test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        
        (self.test_dir / "file1.txt").write_text("This is OLD and needs change")
        (self.test_dir / "file2.txt").write_text("This is OLD content")
        (self.test_dir / "file3.py").write_text("# No OLD here")
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_batch_replace_content(self):
        """Replace content in multiple files."""
        result = batch_replace_content(
            self.test_dir,
            old_text="OLD",
            new_text="NEW",
            file_pattern="*.txt"
        )
        
        self.assertEqual(result.successful, 2)
        self.assertIn("NEW", (self.test_dir / "file1.txt").read_text())
        self.assertIn("NEW", (self.test_dir / "file2.txt").read_text())
        self.assertIn("OLD", (self.test_dir / "file3.py").read_text())  # Unchanged
    
    def test_batch_replace_with_approval(self):
        """Batch replace with approval callback."""
        def approve_callback(ops):
            self.assertEqual(len(ops), 2)
            return True
        
        result = batch_replace_content(
            self.test_dir,
            old_text="OLD",
            new_text="APPROVED",
            file_pattern="*.txt",
            approval_callback=approve_callback
        )
        
        self.assertEqual(result.successful, 2)
        self.assertIn("APPROVED", (self.test_dir / "file1.txt").read_text())


class BatchOperationResultTests(unittest.TestCase):
    """Test result tracking."""
    
    def test_success_rate_calculation(self):
        """Calculate success rate correctly."""
        result = BatchOperationResult(
            total_operations=10,
            successful=8,
            failed=2,
            skipped=0,
            operations=[]
        )
        
        self.assertEqual(result.success_rate, 80.0)
    
    def test_success_rate_all_operations_passed(self):
        """Success rate is 100% when all passed."""
        result = BatchOperationResult(
            total_operations=5,
            successful=5,
            failed=0,
            skipped=0,
            operations=[]
        )
        
        self.assertEqual(result.success_rate, 100.0)
    
    def test_success_rate_zero_operations(self):
        """Success rate is 100% when no operations."""
        result = BatchOperationResult(
            total_operations=0,
            successful=0,
            failed=0,
            skipped=0,
            operations=[]
        )
        
        self.assertEqual(result.success_rate, 100.0)


if __name__ == "__main__":
    unittest.main()
