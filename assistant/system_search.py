"""Smart search and matching for indexed items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from assistant.system_index import IndexedItem, SystemIndex


class SystemSearchError(RuntimeError):
    """Raised when search operations fail."""


@dataclass
class SearchMatch:
    """Represents a search result with matching information."""

    item: IndexedItem
    score: float  # 0.0-1.0 relevance score
    match_type: Literal["exact", "fuzzy", "partial", "substring"]
    reason: str


class FuzzyMatcher:
    """Fuzzy matching algorithm for finding similar strings."""

    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return FuzzyMatcher.levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # j+1 instead of j since previous_row and current_row are one character longer than s2
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    @staticmethod
    def similarity_ratio(s1: str, s2: str) -> float:
        """Calculate similarity ratio between two strings (0.0-1.0)."""
        s1_lower = s1.lower()
        s2_lower = s2.lower()

        if s1_lower == s2_lower:
            return 1.0

        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 0.0

        distance = FuzzyMatcher.levenshtein_distance(s1_lower, s2_lower)
        return 1.0 - (distance / max_len)

    @staticmethod
    def normalize(text: str) -> str:
        """Lowercase and turn separators like '-', '_', '.' into spaces so that
        'Spider-Man', 'Spider_Man', and 'spider man' all compare equal. Also
        splits camelCase boundaries ('SpiderMan' -> 'spider man') so squashed
        together app/game names are still matchable.
        """
        import re as _re

        # Insert a space at lower->Upper camelCase boundaries first, while the
        # original casing is still available.
        spaced = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
        # Replace common separators with spaces.
        spaced = _re.sub(r"[-_.]+", " ", spaced)
        return " ".join(spaced.lower().split())

    @staticmethod
    def partial_match(query: str, text: str) -> float:
        """Check if query is a substring of text, return partial score."""
        query_lower = query.lower()
        text_lower = text.lower()

        if query_lower == text_lower:
            return 1.0

        if query_lower in text_lower:
            # Bonus for substring at start
            if text_lower.startswith(query_lower):
                return 0.95
            return 0.8

        # Fall back to normalized forms so separators (-, _, .) and camelCase
        # boundaries don't prevent an otherwise obvious match, e.g. query
        # "spider man" against "Spider-Man Remastered.exe" or "SpiderMan.exe".
        norm_query = FuzzyMatcher.normalize(query)
        norm_text = FuzzyMatcher.normalize(text)
        if norm_query and norm_query == norm_text:
            return 1.0
        if norm_query and norm_query in norm_text:
            if norm_text.startswith(norm_query):
                return 0.9
            return 0.7

        return 0.0

    @staticmethod
    def starts_with_words(query: str, text: str) -> float:
        """Check if words in query appear at start of words in text."""
        query_words = FuzzyMatcher.normalize(query).split()
        text_words = FuzzyMatcher.normalize(text).split()

        if not query_words:
            return 0.0

        matches = 0
        for query_word in query_words:
            for text_word in text_words:
                if text_word.startswith(query_word):
                    matches += 1
                    break

        return matches / len(query_words) if query_words else 0.0


class SystemSearch:
    """Smart search engine for finding items in the index."""

    def __init__(self, index: SystemIndex) -> None:
        self.index = index

    def search(self, query: str, limit: int = 10) -> list[SearchMatch]:
        """Search for items by name using fuzzy matching."""
        if not query or not query.strip():
            raise SystemSearchError("Search query cannot be empty")

        query = query.strip()
        matches = self._find_matches(query)

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        return matches[:limit]

    def _find_matches(self, query: str) -> list[SearchMatch]:
        """Find all matching items for a query."""
        matches: list[SearchMatch] = []

        for item in self.index.get_all_items():
            score, match_type, reason = self._score_match(query, item)

            if score > 0:
                matches.append(
                    SearchMatch(
                        item=item,
                        score=score,
                        match_type=match_type,
                        reason=reason,
                    )
                )

        return matches

    def _score_match(self, query: str, item: IndexedItem) -> tuple[float, Literal["exact", "fuzzy", "partial", "substring"], str]:
        """Score how well an item matches a query."""
        query_lower = query.lower()
        name_lower = item.name.lower()

        # Exact match
        if query_lower == name_lower:
            return 1.0, "exact", "Exact name match"

        # Exact match without extension
        name_without_ext = item.name.rsplit(".", 1)[0].lower()
        if query_lower == name_without_ext:
            return 0.99, "exact", "Exact match (without extension)"

        # Partial substring match
        partial_score = FuzzyMatcher.partial_match(query, item.name)
        if partial_score > 0:
            if partial_score == 1.0:
                return 0.98, "partial", "Substring match (exact)"
            elif partial_score > 0.9:
                return 0.90, "partial", "Substring match (start)"
            else:
                return 0.75, "substring", "Substring match"

        # Word-based matching
        word_score = FuzzyMatcher.starts_with_words(query, item.name)
        if word_score >= 0.5:
            return 0.80 * word_score, "fuzzy", f"Word match ({word_score:.0%})"

        # Fuzzy matching
        fuzzy_score = FuzzyMatcher.similarity_ratio(query, name_lower)
        if fuzzy_score > 0.7:
            return fuzzy_score * 0.9, "fuzzy", f"Fuzzy match ({fuzzy_score:.0%})"

        return 0.0, "exact", "No match"

    def find_by_name_exact(self, name: str) -> list[IndexedItem]:
        """Find items with exact name match."""
        name_lower = name.lower()
        return [item for item in self.index.get_all_items() if item.name.lower() == name_lower]

    def find_by_type(self, item_type: str) -> list[IndexedItem]:
        """Find items by type (file, folder, app, shortcut)."""
        return [item for item in self.index.get_all_items() if item.item_type == item_type]

    def find_by_extension(self, extension: str) -> list[IndexedItem]:
        """Find items by file extension."""
        ext_lower = extension.lower()
        if not ext_lower.startswith("."):
            ext_lower = "." + ext_lower
        return [item for item in self.index.get_all_items() if item.file_extension.lower() == ext_lower]

    def find_by_name_contains(self, substring: str) -> list[IndexedItem]:
        """Find items whose name contains a substring."""
        substring_lower = substring.lower()
        return [item for item in self.index.get_all_items() if substring_lower in item.name.lower()]

    def find_duplicates(self) -> dict[str, list[IndexedItem]]:
        """Find items with the same name."""
        duplicates: dict[str, list[IndexedItem]] = {}

        for item in self.index.get_all_items():
            key = item.name.lower()
            if key not in duplicates:
                duplicates[key] = []
            duplicates[key].append(item)

        # Remove singles
        return {k: v for k, v in duplicates.items() if len(v) > 1}

    def rank_results(
        self,
        matches: list[SearchMatch],
        access_counts: dict[str, int] | None = None,
        prioritize_types: list[str] | None = None,
    ) -> list[SearchMatch]:
        """Rank results with additional factors."""
        access_counts = access_counts or {}
        prioritize_types = prioritize_types or []

        def calculate_rank_score(match: SearchMatch) -> float:
            score = match.score

            # Boost by access frequency
            access_count = access_counts.get(match.item.id, 0)
            access_boost = min(access_count * 0.05, 0.2)  # Max 0.2 boost
            score += access_boost

            # Boost by priority score
            score += match.item.priority_score * 0.1

            # Boost by type prioritization
            if prioritize_types and match.item.item_type in prioritize_types:
                score += 0.15

            return min(score, 1.0)  # Cap at 1.0

        # Calculate ranks
        for match in matches:
            match.score = calculate_rank_score(match)

        # Sort by new scores
        matches.sort(key=lambda m: m.score, reverse=True)

        return matches
