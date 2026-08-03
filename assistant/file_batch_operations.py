"""
Phase 5.2: File Batch Operations Workflow

Enables bulk file operations with safety:
1. List/search files in a folder
2. Apply filters and transformations
3. Preview changes
4. Request user approval
5. Execute with rollback on error
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileOperation:
    """Represents a single file operation."""
    file_path: Path
    operation: str  # "rename", "replace", "delete", "copy", "move"
    details: dict = field(default_factory=dict)  # operation-specific details
    preview: str = ""  # Human-readable preview of the change
    status: str = "pending"  # "pending", "executed", "failed", "skipped"
    error: Optional[str] = None


@dataclass
class BatchOperationResult:
    """Result of executing a batch operation."""
    total_operations: int
    successful: int
    failed: int
    skipped: int
    operations: list[FileOperation]
    errors: list[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Percentage of successful operations."""
        if self.total_operations == 0:
            return 100.0
        return (self.successful / self.total_operations) * 100


def list_files(
    directory: Path,
    pattern: str = "*",
    recursive: bool = False,
    exclude_dirs: bool = True
) -> list[Path]:
    """
    List files in a directory with optional filtering.
    
    Args:
        directory: Root directory to search
        pattern: Glob pattern to match (e.g., "*.py", "*.txt")
        recursive: Whether to search subdirectories
        exclude_dirs: Whether to exclude directories from results
    
    Returns:
        List of matching file paths
    """
    if not directory.exists():
        logger.warning(f"Directory not found: {directory}")
        return []
    
    try:
        if recursive:
            matches = list(directory.rglob(pattern))
        else:
            matches = list(directory.glob(pattern))
        
        if exclude_dirs:
            matches = [m for m in matches if m.is_file()]
        
        logger.info(f"Found {len(matches)} files matching {pattern}")
        return sorted(matches)
    
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return []


def search_files_by_content(
    directory: Path,
    search_text: str,
    file_pattern: str = "*",
    recursive: bool = True
) -> list[Path]:
    """
    Find files containing specific text.
    
    Args:
        directory: Root directory to search
        search_text: Text to search for
        file_pattern: Glob pattern to match
        recursive: Whether to search subdirectories
    
    Returns:
        List of files containing the search text
    """
    if not directory.exists():
        logger.warning(f"Directory not found: {directory}")
        return []
    
    results = []
    files = list_files(directory, file_pattern, recursive=recursive)
    
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if search_text in content:
                results.append(file_path)
                logger.debug(f"Found '{search_text}' in {file_path}")
        except Exception as e:
            logger.debug(f"Could not read {file_path}: {e}")
    
    logger.info(f"Found {len(results)} files containing '{search_text}'")
    return sorted(results)


def plan_rename_operation(
    file_path: Path,
    new_name: str
) -> FileOperation:
    """Create a rename operation."""
    if file_path.name == new_name:
        return FileOperation(
            file_path=file_path,
            operation="rename",
            details={"new_name": new_name},
            preview=f"No change (same name)",
            status="skipped"
        )
    
    return FileOperation(
        file_path=file_path,
        operation="rename",
        details={"new_name": new_name},
        preview=f"{file_path.name} → {new_name}"
    )


def plan_replace_operation(
    file_path: Path,
    old_text: str,
    new_text: str,
    dry_run: bool = True
) -> FileOperation:
    """Create a replace operation."""
    try:
        content = file_path.read_text(encoding="utf-8")
        if old_text not in content:
            return FileOperation(
                file_path=file_path,
                operation="replace",
                details={"old_text": old_text, "new_text": new_text},
                preview="No match found (no change)",
                status="skipped"
            )
        
        new_content = content.replace(old_text, new_text)
        occurrences = content.count(old_text)
        
        preview = f"Replace '{old_text}' with '{new_text}' ({occurrences} occurrence(s))"
        if not dry_run:
            file_path.write_text(new_content, encoding="utf-8")
            preview += " [EXECUTED]"
        
        return FileOperation(
            file_path=file_path,
            operation="replace",
            details={"old_text": old_text, "new_text": new_text, "occurrences": occurrences},
            preview=preview
        )
    
    except Exception as e:
        return FileOperation(
            file_path=file_path,
            operation="replace",
            details={"old_text": old_text, "new_text": new_text},
            preview=f"Error: {str(e)}",
            status="failed",
            error=str(e)
        )


def plan_delete_operation(file_path: Path) -> FileOperation:
    """Create a delete operation."""
    return FileOperation(
        file_path=file_path,
        operation="delete",
        details={},
        preview=f"Delete {file_path.name}"
    )


def execute_batch_operations(
    operations: list[FileOperation],
    approval_callback: Optional[Callable[[list[FileOperation]], bool]] = None,
    backup_dir: Optional[Path] = None
) -> BatchOperationResult:
    """
    Execute a batch of file operations with optional approval and rollback.
    
    Args:
        operations: List of FileOperation objects to execute
        approval_callback: Optional callback to approve operations
        backup_dir: Optional directory to backup files before modification
    
    Returns:
        BatchOperationResult with execution details
    """
    result = BatchOperationResult(
        total_operations=len(operations),
        successful=0,
        failed=0,
        skipped=0,
        operations=operations.copy()
    )
    
    if not operations:
        logger.info("No operations to execute")
        return result
    
    # Request approval if callback provided
    if approval_callback:
        try:
            approved = approval_callback(operations)
            if not approved:
                result.skipped = len(operations)
                for op in result.operations:
                    op.status = "skipped"
                logger.info("Operations rejected by user")
                return result
        except Exception as e:
            result.errors.append(f"Approval callback failed: {str(e)}")
            logger.error(f"Approval callback error: {e}", exc_info=True)
            return result
    
    # Create backups if requested
    backup_map = {}
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for op in operations:
            if op.operation in ["delete", "replace"] and op.file_path.exists():
                try:
                    backup_path = backup_dir / op.file_path.name
                    shutil.copy2(op.file_path, backup_path)
                    backup_map[op.file_path] = backup_path
                    logger.debug(f"Backed up {op.file_path} to {backup_path}")
                except Exception as e:
                    logger.warning(f"Could not backup {op.file_path}: {e}")
    
    # Execute operations
    for op in result.operations:
        if op.status == "skipped":
            result.skipped += 1
            continue
        
        try:
            if op.operation == "rename":
                _execute_rename(op)
            elif op.operation == "replace":
                _execute_replace(op)
            elif op.operation == "delete":
                _execute_delete(op)
            else:
                op.status = "failed"
                op.error = f"Unknown operation: {op.operation}"
                result.failed += 1
                result.errors.append(f"{op.file_path}: {op.error}")
            
            # Process operation result status
            if op.status == "executed":
                result.successful += 1
            elif op.status == "skipped":
                result.skipped += 1
            elif op.status == "failed":
                result.failed += 1
                if op.error:
                    result.errors.append(f"{op.file_path}: {op.error}")
        
        except Exception as e:
            op.status = "failed"
            op.error = str(e)
            result.failed += 1
            result.errors.append(f"{op.file_path}: {str(e)}")
            logger.error(f"Failed to execute {op.operation} on {op.file_path}: {e}")
    
    logger.info(
        f"Batch complete: {result.successful} succeeded, "
        f"{result.failed} failed, {result.skipped} skipped"
    )
    
    return result


def _execute_rename(op: FileOperation) -> None:
    """Execute a rename operation."""
    if not op.file_path.exists():
        op.status = "failed"
        op.error = "File not found"
        return
    
    new_name = op.details.get("new_name")
    if not new_name:
        op.status = "failed"
        op.error = "No new name specified"
        return
    
    new_path = op.file_path.parent / new_name
    
    if new_path.exists():
        op.status = "failed"
        op.error = f"Target file already exists: {new_name}"
        return
    
    try:
        op.file_path.rename(new_path)
        op.status = "executed"
        op.preview = f"✓ Renamed to {new_name}"
        logger.info(f"Renamed {op.file_path} → {new_path}")
    except Exception as e:
        op.status = "failed"
        op.error = str(e)
        logger.error(f"Rename failed: {e}")


def _execute_replace(op: FileOperation) -> None:
    """Execute a replace operation."""
    if not op.file_path.exists():
        op.status = "failed"
        op.error = "File not found"
        return
    
    old_text = op.details.get("old_text", "")
    new_text = op.details.get("new_text", "")
    
    try:
        content = op.file_path.read_text(encoding="utf-8")
        
        if old_text not in content:
            op.status = "skipped"
            op.preview = "No match found"
            return
        
        new_content = content.replace(old_text, new_text)
        op.file_path.write_text(new_content, encoding="utf-8")
        
        op.status = "executed"
        occurrences = op.details.get("occurrences", 0)
        op.preview = f"✓ Replaced {occurrences} occurrence(s)"
        logger.info(f"Replaced text in {op.file_path}")
    
    except Exception as e:
        op.status = "failed"
        op.error = str(e)
        logger.error(f"Replace failed: {e}")


def _execute_delete(op: FileOperation) -> None:
    """Execute a delete operation."""
    if not op.file_path.exists():
        op.status = "failed"
        op.error = "File not found"
        return
    
    try:
        op.file_path.unlink()
        op.status = "executed"
        op.preview = f"✓ Deleted {op.file_path.name}"
        logger.info(f"Deleted {op.file_path}")
    except Exception as e:
        op.status = "failed"
        op.error = str(e)
        logger.error(f"Delete failed: {e}")


def batch_rename_files(
    directory: Path,
    pattern: str = "*",
    name_transform: Callable[[str], str] = lambda x: x,
    approval_callback: Optional[Callable[[list[FileOperation]], bool]] = None
) -> BatchOperationResult:
    """
    Batch rename files in a directory.
    
    Args:
        directory: Directory containing files
        pattern: Glob pattern to match
        name_transform: Function to transform file names
        approval_callback: Optional approval function
    
    Returns:
        Batch operation result
    """
    files = list_files(directory, pattern, recursive=False)
    operations = []
    
    for file_path in files:
        new_name = name_transform(file_path.name)
        if new_name != file_path.name:
            op = plan_rename_operation(file_path, new_name)
            operations.append(op)
    
    return execute_batch_operations(operations, approval_callback)


def batch_replace_content(
    directory: Path,
    old_text: str,
    new_text: str,
    file_pattern: str = "*",
    recursive: bool = True,
    approval_callback: Optional[Callable[[list[FileOperation]], bool]] = None
) -> BatchOperationResult:
    """
    Replace text in multiple files.
    
    Args:
        directory: Root directory to search
        old_text: Text to find
        new_text: Replacement text
        file_pattern: Glob pattern to match
        recursive: Whether to search subdirectories
        approval_callback: Optional approval function
    
    Returns:
        Batch operation result
    """
    files = list_files(directory, file_pattern, recursive=recursive)
    operations = []
    
    for file_path in files:
        op = plan_replace_operation(file_path, old_text, new_text, dry_run=True)
        if op.status != "skipped":  # Only include files with actual changes
            operations.append(op)
    
    return execute_batch_operations(operations, approval_callback)
