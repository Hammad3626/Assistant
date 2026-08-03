"""
Tests for Phase 5.1: Copy→Fix→Paste Workflow
"""

import json
import unittest
from unittest.mock import Mock, patch, MagicMock

from assistant.code_editing_workflow import (
    detect_language,
    analyze_code,
    generate_fixes,
    apply_code_fixes,
    copy_fix_paste_workflow,
    CodeIssue,
    CodeAnalysisResult,
)


class LanguageDetectionTests(unittest.TestCase):
    """Test automatic language detection."""
    
    def test_detect_python(self):
        code = "def hello():\n    print('world')\n\nif __name__ == '__main__':\n    hello()"
        self.assertEqual(detect_language(code), "python")
    
    def test_detect_javascript(self):
        code = "const greet = () => {\n  console.log('hello');\n};\nrequire('fs');"
        self.assertEqual(detect_language(code), "javascript")
    
    def test_detect_cpp(self):
        code = "#include <iostream>\nusing namespace std;\nint main() { return 0; }"
        self.assertEqual(detect_language(code), "cpp")
    
    def test_detect_csharp(self):
        code = "using System;\npublic class Program {\n    public static void Main() { }\n}"
        self.assertEqual(detect_language(code), "csharp")
    
    def test_unknown_language(self):
        code = "some random text without any code indicators"
        self.assertEqual(detect_language(code), "unknown")
    
    def test_empty_code(self):
        code = ""
        self.assertEqual(detect_language(code), "unknown")


class CodeAnalysisTests(unittest.TestCase):
    """Test code analysis functionality."""
    
    def test_empty_code_analysis(self):
        result = analyze_code("")
        self.assertEqual(result.language, "unknown")
        self.assertEqual(len(result.issues), 0)
        self.assertIn("No code", result.summary)
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    def test_successful_analysis(self, mock_get_client):
        # Mock Ollama client
        mock_client = Mock()
        mock_client.generate.return_value = json.dumps({
            "issues": [
                {
                    "line": 1,
                    "category": "bug",
                    "severity": "high",
                    "description": "Variable not initialized",
                    "suggestion": "Initialize x before use"
                }
            ],
            "summary": "Found 1 issue"
        })
        mock_get_client.return_value = mock_client
        
        code = "def test():\n    return x + 1"
        result = analyze_code(code)
        
        self.assertEqual(result.language, "python")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].category, "bug")
        self.assertEqual(result.issues[0].severity, "high")
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    def test_analysis_no_issues(self, mock_get_client):
        mock_client = Mock()
        mock_client.generate.return_value = json.dumps({
            "issues": [],
            "summary": "No issues found"
        })
        mock_get_client.return_value = mock_client
        
        code = "def hello():\n    print('world')"
        result = analyze_code(code)
        
        self.assertEqual(len(result.issues), 0)
        self.assertIn("No issues", result.summary)
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    def test_analysis_ollama_error(self, mock_get_client):
        # Simulate Ollama connection error
        mock_client = Mock()
        mock_client.generate.return_value = "Error: Ollama is not running"
        mock_get_client.return_value = mock_client
        
        code = "def test(): pass"
        result = analyze_code(code)
        
        self.assertEqual(len(result.issues), 0)
        self.assertIn("unavailable", result.summary)
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    def test_analysis_json_decode_error(self, mock_get_client):
        # Return invalid JSON
        mock_client = Mock()
        mock_client.generate.return_value = "This is not JSON at all"
        mock_get_client.return_value = mock_client
        
        code = "def test(): pass"
        result = analyze_code(code)
        
        self.assertEqual(len(result.issues), 0)
        self.assertIn("parse", result.summary.lower())


class FixGenerationTests(unittest.TestCase):
    """Test fix generation."""
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    def test_generate_fixes_with_issues(self, mock_get_client):
        mock_client = Mock()
        mock_client.generate.return_value = """
Here's the fixed code:

```python
def greet(name):
    return f"Hello, {name}!"
```
"""
        mock_get_client.return_value = mock_client
        
        analysis = CodeAnalysisResult(
            code="def greet(name):\n    return 'Hello, ' + name",
            language="python",
            issues=[CodeIssue(1, "style", "low", "Use f-strings", "Use f-string syntax")],
            summary="Found style issue"
        )
        
        fixes = generate_fixes(analysis)
        
        self.assertIn("fixed_code", fixes)
        self.assertIn("def greet", fixes["fixed_code"])
    
    def test_generate_fixes_no_issues(self):
        analysis = CodeAnalysisResult(
            code="print('hello')",
            language="python",
            issues=[],
            summary="No issues"
        )
        
        fixes = generate_fixes(analysis)
        self.assertEqual(len(fixes), 0)
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    def test_generate_fixes_ollama_error(self, mock_get_client):
        mock_client = Mock()
        mock_client.generate.return_value = "Error: Ollama unavailable"
        mock_get_client.return_value = mock_client
        
        analysis = CodeAnalysisResult(
            code="x = 1",
            language="python",
            issues=[CodeIssue(1, "bug", "high", "Bad variable name", "Use better name")],
            summary="Issues found"
        )
        
        fixes = generate_fixes(analysis)
        self.assertEqual(len(fixes), 0)


class ApplyFixesTests(unittest.TestCase):
    """Test fix application."""
    
    @patch('assistant.code_editing_workflow.generate_fixes')
    def test_apply_fixes_with_issues(self, mock_generate_fixes):
        mock_generate_fixes.return_value = {"fixed_code": "def greet(name):\n    print(f'Hello, {name}!')"}
        
        analysis = CodeAnalysisResult(
            code="def greet(name):\n    print('Hello, ' + name)",
            language="python",
            issues=[
                CodeIssue(1, "style", "low", "Use f-strings", ""),
                CodeIssue(2, "style", "low", "Use f-strings", "")
            ],
            summary="Found style issues"
        )
        
        result = apply_code_fixes(analysis)
        
        self.assertEqual(result.issues_resolved, 2)
        self.assertEqual(result.issues_remaining, 0)
        self.assertGreater(len(result.changes_applied), 0)
    
    def test_apply_fixes_no_issues(self):
        analysis = CodeAnalysisResult(
            code="print('hello')",
            language="python",
            issues=[],
            summary="No issues"
        )
        
        result = apply_code_fixes(analysis)
        
        self.assertEqual(result.original, result.fixed)
        self.assertEqual(result.issues_resolved, 0)
        self.assertEqual(len(result.changes_applied), 0)


class ClipboardWorkflowTests(unittest.TestCase):
    """Test end-to-end clipboard workflow."""
    
    @patch('assistant.code_editing_workflow.write_clipboard')
    @patch('assistant.code_editing_workflow.read_clipboard')
    @patch('assistant.code_editing_workflow.apply_code_fixes')
    @patch('assistant.code_editing_workflow.analyze_code')
    def test_workflow_success_with_fixes(self, mock_analyze, mock_apply, mock_read, mock_write):
        # Setup mocks
        original_code = "x = 1; y = 2"
        fixed_code = "x = 1\ny = 2"
        
        mock_read.return_value = original_code
        
        mock_analyze.return_value = CodeAnalysisResult(
            code=original_code,
            language="python",
            issues=[CodeIssue(1, "style", "low", "Semicolon", "")],
            summary="Found 1 issue"
        )
        
        mock_apply.return_value = MagicMock(
            original=original_code,
            fixed=fixed_code,
            changes_applied=["Fixed semicolon"],
            issues_resolved=1,
            issues_remaining=0
        )
        
        mock_write.return_value = True
        
        # Run workflow
        result = copy_fix_paste_workflow()
        
        # Verify
        self.assertTrue(result["success"])
        self.assertEqual(result["original_code"], original_code)
        self.assertEqual(result["fixed_code"], fixed_code)
        self.assertGreater(len(result["changes_applied"]), 0)
        mock_write.assert_called_once()
    
    @patch('assistant.code_editing_workflow.read_clipboard')
    def test_workflow_empty_clipboard(self, mock_read):
        mock_read.return_value = ""
        
        result = copy_fix_paste_workflow()
        
        self.assertFalse(result["success"])
        self.assertIn("empty", result["error"].lower())
    
    @patch('assistant.code_editing_workflow.write_clipboard')
    @patch('assistant.code_editing_workflow.read_clipboard')
    @patch('assistant.code_editing_workflow.analyze_code')
    def test_workflow_no_issues_found(self, mock_analyze, mock_read, mock_write):
        original_code = "def hello():\n    print('world')"
        
        mock_read.return_value = original_code
        mock_analyze.return_value = CodeAnalysisResult(
            code=original_code,
            language="python",
            issues=[],
            summary="No issues found"
        )
        
        result = copy_fix_paste_workflow()
        
        self.assertTrue(result["success"])
        self.assertEqual(result["fixed_code"], original_code)
        self.assertEqual(result["analysis"]["issues_found"], 0)
    
    @patch('assistant.code_editing_workflow.write_clipboard')
    @patch('assistant.code_editing_workflow.read_clipboard')
    @patch('assistant.code_editing_workflow.apply_code_fixes')
    @patch('assistant.code_editing_workflow.analyze_code')
    def test_workflow_with_approval_callback(self, mock_analyze, mock_apply, mock_read, mock_write):
        original = "x=1"
        fixed = "x = 1"
        
        mock_read.return_value = original
        mock_analyze.return_value = CodeAnalysisResult(
            code=original,
            language="python",
            issues=[CodeIssue(1, "style", "low", "Spacing", "")],
            summary="Found 1 issue"
        )
        mock_apply.return_value = MagicMock(fixed=fixed, changes_applied=["Fixed spacing"])
        mock_write.return_value = True
        
        # Approval callback that rejects changes
        def reject_callback(orig, new):
            return False
        
        result = copy_fix_paste_workflow(approval_callback=reject_callback)
        
        self.assertFalse(result["success"])
        self.assertIn("rejected", result["status"].lower())
        mock_write.assert_not_called()  # Should not write if rejected
    
    @patch('assistant.code_editing_workflow.write_clipboard')
    @patch('assistant.code_editing_workflow.read_clipboard')
    @patch('assistant.code_editing_workflow.apply_code_fixes')
    @patch('assistant.code_editing_workflow.analyze_code')
    def test_workflow_approval_callback_approves(self, mock_analyze, mock_apply, mock_read, mock_write):
        original = "x=1"
        fixed = "x = 1"
        
        mock_read.return_value = original
        mock_analyze.return_value = CodeAnalysisResult(
            code=original,
            language="python",
            issues=[CodeIssue(1, "style", "low", "Spacing", "")],
            summary="Found 1 issue"
        )
        mock_apply.return_value = MagicMock(fixed=fixed, changes_applied=["Fixed spacing"])
        mock_write.return_value = True
        
        # Approval callback that approves changes
        def approve_callback(orig, new):
            return True
        
        result = copy_fix_paste_workflow(approval_callback=approve_callback)
        
        self.assertTrue(result["success"])
        mock_write.assert_called_once_with(fixed)
    
    @patch('assistant.code_editing_workflow.read_clipboard')
    @patch('assistant.code_editing_workflow.analyze_code')
    def test_workflow_analysis_error(self, mock_analyze, mock_read):
        mock_read.return_value = "some code"
        mock_analyze.side_effect = Exception("Analysis crashed")
        
        result = copy_fix_paste_workflow()
        
        self.assertFalse(result["success"])
        self.assertIn("Could not analyze", result["status"])
    
    @patch('assistant.code_editing_workflow.write_clipboard')
    @patch('assistant.code_editing_workflow.read_clipboard')
    @patch('assistant.code_editing_workflow.apply_code_fixes')
    @patch('assistant.code_editing_workflow.analyze_code')
    def test_workflow_clipboard_write_fails(self, mock_analyze, mock_apply, mock_read, mock_write):
        original = "x=1"
        fixed = "x = 1"
        
        mock_read.return_value = original
        mock_analyze.return_value = CodeAnalysisResult(
            code=original,
            language="python",
            issues=[CodeIssue(1, "style", "low", "Spacing", "")],
            summary="Found 1 issue"
        )
        mock_apply.return_value = MagicMock(fixed=fixed, changes_applied=["Fixed spacing"])
        mock_write.return_value = False  # Clipboard write fails
        
        result = copy_fix_paste_workflow()
        
        self.assertFalse(result["success"])
        self.assertIn("Could not write", result["status"])


class WorkflowIntegrationTests(unittest.TestCase):
    """Integration tests combining multiple components."""
    
    @patch('assistant.code_editing_workflow._get_ollama_client')
    @patch('assistant.code_editing_workflow.write_clipboard')
    @patch('assistant.code_editing_workflow.read_clipboard')
    def test_full_workflow_python_bug_fix(self, mock_read, mock_write, mock_get_client):
        """Test complete workflow: read buggy Python, analyze, fix, write back."""
        
        original_code = """def calculate(x, y):
    result = x + y
    print result
    return result
"""
        
        fixed_code = """def calculate(x, y):
    result = x + y
    print(result)
    return result
"""
        
        mock_read.return_value = original_code
        mock_write.return_value = True
        
        # Mock Ollama client
        mock_client = Mock()
        
        # Mock Ollama responses
        analysis_response = json.dumps({
            "issues": [{
                "line": 3,
                "category": "bug",
                "severity": "high",
                "description": "Python 3 syntax: print requires parentheses",
                "suggestion": "Use print(result) instead of print result"
            }],
            "summary": "Found 1 bug"
        })
        
        fix_response = f"""
Here's the corrected code:

```python
{fixed_code}
```
"""
        
        # First call for analysis, second for fix generation
        mock_client.generate.side_effect = [analysis_response, fix_response]
        mock_get_client.return_value = mock_client
        
        result = copy_fix_paste_workflow()
        
        self.assertTrue(result["success"])
        self.assertEqual(result["analysis"]["issues_found"], 1)
        self.assertIn("print", result["fixed_code"])
        mock_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
