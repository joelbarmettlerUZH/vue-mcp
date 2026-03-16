"""Query-time dictionary matching with rapidfuzz for API entities.

Provides fast, deterministic entity extraction from user queries:
- Exact case-insensitive matching against the API entity dictionary
- Bigram matching for compound names (e.g., "watchEffect", "defineProps")
- Fuzzy matching via rapidfuzz (Levenshtein distance <= 2) for typo tolerance
- Synonym/alias table lookup for conceptual phrases

Ambiguous entity names (common English words like "component", "template",
"key") only match when they appear in code context: wrapped in backticks,
prefixed with `v-` or `<`, etc.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from vue_docs_core.config import FUZZY_MIN_SCORE
from vue_docs_core.models.entity import EntityIndex

# Minimum token length for fuzzy matching — avoids false positives
# on common short words. Tokens shorter than this are exact-only.
FUZZY_MIN_TOKEN_LENGTH = 6

# Minimum entity name length for fuzzy matching — avoids false positives
# on very short names like "h", "is", "key", "ref".
FUZZY_MIN_LENGTH = 6

# Entity names that are common English words. These only match when they
# appear in code context (backticks, v- prefix, < prefix, etc.), not as
# bare words in natural language queries.
_AMBIGUOUS_NAMES: set[str] = {
    "$options",
    "component",
    "components",
    "data",
    "h",
    "inject",
    "is",
    "key",
    "methods",
    "name",
    "props",
    "provide",
    "render",
    "slot",
    "template",
    "watch",
}


@dataclass
class EntityMatchResult:
    """Result of entity detection on a query."""

    entities: list[str] = field(default_factory=list)
    match_sources: dict[str, str] = field(default_factory=dict)
    """Maps entity name -> how it was matched (exact, fuzzy, synonym, bigram)."""


class EntityMatcher:
    """Fast, deterministic API entity matcher for query-time use.

    Initialized once at server startup with the entity dictionary and
    synonym table. Matching runs in sub-millisecond time per query.
    """

    def __init__(
        self,
        entity_index: EntityIndex,
        synonym_table: dict[str, list[str]],
    ):
        self.entity_index = entity_index
        self.synonym_table = synonym_table

        # Build lookup structures
        self._entity_names: list[str] = list(entity_index.entities.keys())
        self._name_lower_map: dict[str, str] = {name.lower(): name for name in self._entity_names}
        # Separate short names (exact only) from long names (fuzzy eligible).
        # Store lowercased for case-insensitive comparison, map back to original.
        self._fuzzy_candidates_lower: list[str] = [
            name.lower() for name in self._entity_names if len(name) >= FUZZY_MIN_LENGTH
        ]
        self._fuzzy_lower_to_original: dict[str, str] = {
            name.lower(): name for name in self._entity_names if len(name) >= FUZZY_MIN_LENGTH
        }

    def match(self, query: str) -> EntityMatchResult:
        """Detect API entity names in a query string.

        Applies matching in priority order:
        1. Exact case-insensitive match against entity dictionary
        2. Bigram matching for compound camelCase names
        3. Synonym/alias table lookup
        4. Fuzzy matching (Levenshtein) for typo tolerance
        """
        result = EntityMatchResult()

        # Extract code-context names from the raw query before normalizing.
        # These are names that appear in backticks, after v-, <, or .
        code_names = _extract_code_context_names(query)

        query_clean = _normalize_query(query)
        query_tokens = _tokenize(query_clean)

        # 1. Exact matching — check each entity name against query
        self._match_exact(query_clean, code_names, result)

        # 2. Bigram matching — join adjacent tokens to catch compound names
        self._match_bigrams(query_tokens, result)

        # 3. Synonym table — conceptual phrase matching
        self._match_synonyms(query_clean, result)

        # 4. Fuzzy matching — catch typos like "definProps", "onmounted"
        self._match_fuzzy(query_tokens, result)

        return result

    def _match_exact(
        self,
        query_clean: str,
        code_names: set[str],
        result: EntityMatchResult,
    ) -> None:
        """Case-insensitive substring match against entity names.

        Ambiguous names (common English words) only match if they appeared
        in code context in the original query.
        """
        for name_lower, name_original in self._name_lower_map.items():
            if name_original in result.match_sources:
                continue
            if name_lower not in query_clean:
                continue

            # Short names: require word boundary
            if len(name_lower) <= 3 and not _is_word_boundary(query_clean, name_lower):
                continue

            # Ambiguous names: require code context
            if name_lower in _AMBIGUOUS_NAMES and name_lower not in code_names:
                continue

            result.entities.append(name_original)
            result.match_sources[name_original] = "exact"

    def _match_bigrams(self, tokens: list[str], result: EntityMatchResult) -> None:
        """Join adjacent tokens to match camelCase/compound names.

        Catches queries like "watch effect" -> "watchEffect",
        "define props" -> "defineProps".
        """
        if len(tokens) < 2:
            return

        for i in range(len(tokens) - 1):
            # Try joining adjacent tokens in camelCase style
            bigram = tokens[i] + tokens[i + 1]
            if bigram in self._name_lower_map:
                name = self._name_lower_map[bigram]
                if name not in result.match_sources:
                    result.entities.append(name)
                    result.match_sources[name] = "bigram"

    def _match_synonyms(self, query_clean: str, result: EntityMatchResult) -> None:
        """Match conceptual phrases from the synonym table."""
        for phrase, api_names in self.synonym_table.items():
            if phrase.lower() in query_clean:
                for api_name in api_names:
                    if api_name not in result.match_sources:
                        result.entities.append(api_name)
                        result.match_sources[api_name] = "synonym"

    def _match_fuzzy(self, tokens: list[str], result: EntityMatchResult) -> None:
        """Fuzzy match query tokens against entity names for typo tolerance.

        Only applied to tokens of sufficient length and entity names of
        sufficient length to avoid false positives.
        """
        if not self._fuzzy_candidates_lower:
            return

        for token in tokens:
            if len(token) < FUZZY_MIN_TOKEN_LENGTH:
                continue

            matches = process.extract(
                token,
                self._fuzzy_candidates_lower,
                scorer=fuzz.ratio,
                limit=3,
                score_cutoff=FUZZY_MIN_SCORE,
            )

            for match_lower, _score, _ in matches:
                original_name = self._fuzzy_lower_to_original[match_lower]
                # Skip if already matched by a higher-priority method
                if original_name in result.match_sources:
                    continue
                # Skip exact matches (already handled)
                if match_lower == token:
                    continue
                # Skip ambiguous names — fuzzy should not promote common words
                if match_lower in _AMBIGUOUS_NAMES:
                    continue
                result.entities.append(original_name)
                result.match_sources[original_name] = "fuzzy"


def _normalize_query(query: str) -> str:
    """Normalize a query for matching: lowercase, strip backticks/punctuation."""
    query = query.lower().strip()
    query = query.replace("`", "")
    return query


def _tokenize(query: str) -> list[str]:
    """Split query into lowercase tokens on whitespace and punctuation."""
    return [t for t in re.split(r"[\s\-_.,;:!?()]+", query) if t]


def _is_word_boundary(text: str, term: str) -> bool:
    """Check that term appears at word boundaries in text (not as substring of larger word)."""
    pattern = rf"(?:^|[\s\-_.,;:!?()`]){re.escape(term)}(?:$|[\s\-_.,;:!?()`])"
    return bool(re.search(pattern, text))


def _extract_code_context_names(raw_query: str) -> set[str]:
    """Extract entity names that appear in code context in the raw query.

    Code context means:
    - Wrapped in backticks: `component`, `v-model`
    - Prefixed with v-: v-model, v-if
    - Prefixed with <: <component>, <slot>
    - Prefixed with .: .component, .provide (method chaining)

    Returns lowercased names for comparison.
    """
    names: set[str] = set()

    # Backtick-wrapped: `component`, `v-model`, `defineProps`
    for m in re.finditer(r"`([^`]+)`", raw_query):
        content = m.group(1).strip().lower()
        # Strip v- prefix for directive matching
        names.add(content)
        if content.startswith("v-"):
            names.add(content[2:])

    # v- prefixed (without backticks): v-model, v-if
    for m in re.finditer(r"\bv-(\w+)", raw_query, re.IGNORECASE):
        names.add(m.group(1).lower())
        names.add(f"v-{m.group(1).lower()}")

    # < prefixed: <component>, <Transition>
    for m in re.finditer(r"<(\w+)", raw_query):
        names.add(m.group(1).lower())

    # . prefixed: .component(), .provide()
    for m in re.finditer(r"\.(\w+)", raw_query):
        names.add(m.group(1).lower())

    return names
