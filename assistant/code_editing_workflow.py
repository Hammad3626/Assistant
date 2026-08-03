"""
Phase 5.1: Copy→Fix→Paste Workflow

Enables seamless code editing via clipboard:
1. Read code from clipboard
2. Analyze for bugs/style issues using Ollama
3. Suggest fixes
4. Apply fixes
5. Write result back to clipboard
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from assistant.ollama_client import OllamaClient
from assistant.windows_integration import read_clipboard, write_clipboard

logger = logging.getLogger(__name__)

# Initialize Ollama client (will be created on demand)
_ollama_client: OllamaClient | None = None

def _get_ollama_client() -> OllamaClient:
    """Get or create the global Ollama client."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


@dataclass
class CodeIssue:
    """Represents a code issue found during analysis."""
    line: int
    category: str  # "bug", "style", "performance", "security"
    severity: str  # "critical", "high", "medium", "low"
    description: str
    suggestion: str


@dataclass
class CodeAnalysisResult:
    """Result of analyzing code for issues."""
    code: str
    language: str  # "python", "javascript", "cpp", etc.
    issues: list[CodeIssue]
    summary: str  # Brief summary of all issues found


@dataclass
class FixedCodeResult:
    """Result of applying fixes to code."""
    original: str
    fixed: str
    changes_applied: list[str]
    issues_resolved: int
    issues_remaining: int


def detect_language(code: str) -> str:
    """Auto-detect code language from content."""
    code_lower = code.lower()
    
    # Language-specific keywords
    indicators = {
        "python": ["def ", "class ", "import ", "from ", "if __name__"],
        "javascript": ["function ", "const ", "let ", "var ", "=>", "require("],
        "cpp": ["#include", "using namespace", "std::", "int main"],
        "csharp": ["using System", "public class", "public static void"],
        "java": ["public class", "public static void main", "import java"],
        "rust": ["fn main", "let ", "mut ", "impl "],
        "go": ["package main", "func ", "import "],
    }
    
    scores = {}
    for lang, keywords in indicators.items():
        scores[lang] = sum(1 for kw in keywords if kw in code_lower)
    
    if not any(scores.values()):
        return "unknown"
    
    return max(scores, key=scores.get)


def analyze_code(code: str) -> CodeAnalysisResult:
    """
    Analyze code for bugs, style issues, and potential improvements.
    
    Args:
        code: Source code to analyze
    
    Returns:
        CodeAnalysisResult with detected issues
    """
    if not code or not code.strip():
        return CodeAnalysisResult(
            code=code,
            language="unknown",
            issues=[],
            summary="No code to analyze"
        )
    
    language = detect_language(code)
    
    # Build analysis prompt
    prompt = f"""Analyze this {language} code for bugs, style issues, and improvements.
Be concise and specific. Focus on actual problems, not minor style.

Code:
```{language}
{code}
```

Respond with a JSON object:
{{
  "issues": [
    {{"line": 1, "category": "bug|style|performance|security", "severity": "critical|high|medium|low", "description": "...", "suggestion": "..."}}
  ],
  "summary": "Brief overall assessment"
}}

If no issues found, return {{"issues": [], "summary": "No issues found"}}.
"""
    
    response = _get_ollama_client().generate(prompt, memory_context={})
    
    # Handle error response from Ollama
    if isinstance(response, str) and response.startswith("Error:"):
        logger.warning(f"Ollama analysis failed: {response}")
        return CodeAnalysisResult(
            code=code,
            language=language,
            issues=[],
            summary=f"Analysis unavailable: {response}"
        )
    
    try:
        # Extract JSON from response
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start == -1 or json_end == 0:
            logger.warning("No JSON found in Ollama response")
            return CodeAnalysisResult(code=code, language=language, issues=[], summary="Could not parse analysis")
        
        analysis = json.loads(response[json_start:json_end])
        
        # Convert to CodeIssue objects
        issues = []
        for issue_dict in analysis.get("issues", []):
            try:
                issue = CodeIssue(
                    line=issue_dict.get("line", 0),
                    category=issue_dict.get("category", "style"),
                    severity=issue_dict.get("severity", "low"),
                    description=issue_dict.get("description", ""),
                    suggestion=issue_dict.get("suggestion", "")
                )
                issues.append(issue)
            except (KeyError, TypeError) as e:
                logger.debug(f"Skipped malformed issue: {e}")
        
        return CodeAnalysisResult(
            code=code,
            language=language,
            issues=issues,
            summary=analysis.get("summary", "Analysis complete")
        )
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Ollama JSON response: {e}")
        return CodeAnalysisResult(
            code=code,
            language=language,
            issues=[],
            summary="Failed to parse analysis"
        )


def generate_fixes(analysis: CodeAnalysisResult) -> dict[str, str]:
    """
    Generate fixed version of code based on analysis results.
    
    Args:
        analysis: Result from analyze_code()
    
    Returns:
        Dictionary mapping issue descriptions to suggested fixes
    """
    if not analysis.issues:
        return {}
    
    # Build list of issues for the fix prompt
    issues_text = "\n".join([
        f"Line {issue.line}: [{issue.severity.upper()}] {issue.description}\n  Suggestion: {issue.suggestion}"
        for issue in analysis.issues
    ])
    
    prompt = f"""Fix these issues in the {analysis.language} code:

Issues found:
{issues_text}

Original code:
```{analysis.language}
{analysis.code}
```

Provide corrected code that fixes all issues while preserving functionality.
Return ONLY the fixed code, no explanation.
"""
    
    response = _get_ollama_client().generate(prompt, memory_context={})
    
    # Handle error response
    if isinstance(response, str) and response.startswith("Error:"):
        logger.warning(f"Ollama fix generation failed: {response}")
        return {}
    
    # Extract code block from response
    code_start = response.find(f"```{analysis.language}")
    code_end = response.find("```", code_start + 1)
    
    if code_start != -1 and code_end != -1:
        fixed_code = response[code_start + len(f"```{analysis.language}"):code_end].strip()
        return {"fixed_code": fixed_code}
    
    # If no code block, treat entire response as fixed code
    return {"fixed_code": response.strip()}


def apply_code_fixes(analysis: CodeAnalysisResult) -> FixedCodeResult:
    """
    Analyze code and generate fixes.
    
    Args:
        analysis: Result from analyze_code()
    
    Returns:
        FixedCodeResult with original, fixed, and summary
    """
    if not analysis.issues:
        return FixedCodeResult(
            original=analysis.code,
            fixed=analysis.code,
            changes_applied=[],
            issues_resolved=0,
            issues_remaining=0
        )
    
    # Generate fixes
    fixes = generate_fixes(analysis)
    fixed_code = fixes.get("fixed_code", analysis.code)
    
    # Categorize issues by severity
    critical = [i for i in analysis.issues if i.severity == "critical"]
    high = [i for i in analysis.issues if i.severity == "high"]
    medium = [i for i in analysis.issues if i.severity == "medium"]
    low = [i for i in analysis.issues if i.severity == "low"]
    
    changes = []
    if critical:
        changes.append(f"Fixed {len(critical)} critical bug(s)")
    if high:
        changes.append(f"Fixed {len(high)} high-priority issue(s)")
    if medium:
        changes.append(f"Improved {len(medium)} medium-priority item(s)")
    if low:
        changes.append(f"Addressed {len(low)} low-priority suggestion(s)")
    
    return FixedCodeResult(
        original=analysis.code,
        fixed=fixed_code,
        changes_applied=changes,
        issues_resolved=len(analysis.issues),
        issues_remaining=0  # Assumes all issues are fixed
    )


def copy_fix_paste_workflow(
    approval_callback: Optional[Callable[[str, str], bool]] = None
) -> dict:
    """
    Main workflow: Read code from clipboard, analyze, fix, write back.
    
    Args:
        approval_callback: Optional function(original, fixed) -> bool to approve changes
    
    Returns:
        Workflow result dict with status, changes, error info
    """
    result = {
        "success": False,
        "status": "",
        "original_code": "",
        "fixed_code": "",
        "analysis": None,
        "changes_applied": [],
        "error": None
    }
    
    # Step 1: Read from clipboard
    original = read_clipboard()
    if not original:
        result["error"] = "Clipboard is empty"
        result["status"] = "Failed: No code to analyze"
        return result
    
    result["original_code"] = original
    logger.info(f"Read {len(original)} chars from clipboard")
    
    # Step 2: Analyze code
    try:
        analysis = analyze_code(original)
        result["analysis"] = {
            "language": analysis.language,
            "issues_found": len(analysis.issues),
            "summary": analysis.summary,
            "issues": [
                {
                    "line": issue.line,
                    "category": issue.category,
                    "severity": issue.severity,
                    "description": issue.description
                }
                for issue in analysis.issues
            ]
        }
        logger.info(f"Analysis complete: {len(analysis.issues)} issues found")
    except Exception as e:
        result["error"] = f"Analysis failed: {str(e)}"
        result["status"] = "Failed: Could not analyze code"
        logger.error(f"Code analysis error: {e}", exc_info=True)
        return result
    
    # Step 3: If no issues, return original
    if not analysis.issues:
        result["success"] = True
        result["status"] = "No issues found - code is clean"
        result["fixed_code"] = original
        return result
    
    # Step 4: Generate fixes
    try:
        fixed_result = apply_code_fixes(analysis)
        result["fixed_code"] = fixed_result.fixed
        result["changes_applied"] = fixed_result.changes_applied
        logger.info(f"Fixes generated: {len(fixed_result.changes_applied)} change groups")
    except Exception as e:
        result["error"] = f"Fix generation failed: {str(e)}"
        result["status"] = "Failed: Could not generate fixes"
        logger.error(f"Fix generation error: {e}", exc_info=True)
        return result
    
    # Step 5: Request approval if callback provided
    if approval_callback:
        try:
            approved = approval_callback(original, fixed_result.fixed)
            if not approved:
                result["status"] = "Changes rejected by user"
                return result
        except Exception as e:
            result["error"] = f"Approval callback failed: {str(e)}"
            logger.error(f"Approval callback error: {e}")
            return result
    
    # Step 6: Write fixed code back to clipboard
    try:
        if write_clipboard(fixed_result.fixed):
            result["success"] = True
            result["status"] = "Fixes applied and pasted to clipboard"
            logger.info("Fixed code written to clipboard")
        else:
            result["error"] = "Failed to write clipboard"
            result["status"] = "Failed: Could not write to clipboard"
            logger.error("Clipboard write failed")
    except Exception as e:
        result["error"] = f"Clipboard write failed: {str(e)}"
        result["status"] = "Failed: Could not write to clipboard"
        logger.error(f"Clipboard write error: {e}", exc_info=True)
    
    return result
