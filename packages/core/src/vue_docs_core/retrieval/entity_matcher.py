"""Query-time dictionary matching with rapidfuzz for API entities.

Provides fast, deterministic entity extraction from user queries:
- Exact case-insensitive matching against the API entity dictionary
- Bigram matching for compound names (e.g., "watchEffect", "defineProps")
- Fuzzy matching via rapidfuzz (Levenshtein distance <= 2) for typo tolerance
- Synonym/alias table lookup for conceptual phrases
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from vue_docs_core.models.entity import EntityIndex


# Minimum fuzzy match score (0-100) to accept a match.
# rapidfuzz uses ratio scoring; 80 roughly corresponds to Levenshtein distance <= 2
# for typical API name lengths (5-15 chars).
FUZZY_MIN_SCORE = 80

# Minimum entity name length for fuzzy matching — avoids false positives
# on very short names like "h", "is", "key", "ref".
FUZZY_MIN_LENGTH = 5


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
        self._name_lower_map: dict[str, str] = {
            name.lower(): name for name in self._entity_names
        }
        # Separate short names (exact only) from long names (fuzzy eligible)
        self._fuzzy_candidates: list[str] = [
            name for name in self._entity_names if len(name) >= FUZZY_MIN_LENGTH
        ]

    def match(self, query: str) -> EntityMatchResult:
        """Detect API entity names in a query string.

        Applies matching in priority order:
        1. Exact case-insensitive match against entity dictionary
        2. Bigram matching for compound camelCase names
        3. Synonym/alias table lookup
        4. Fuzzy matching (Levenshtein) for typo tolerance

        Returns:
            EntityMatchResult with deduplicated entity names and match sources.
        """
        result = EntityMatchResult()
        query_clean = _normalize_query(query)
        query_tokens = _tokenize(query_clean)

        # 1. Exact matching — check each entity name against query
        self._match_exact(query_clean, result)

        # 2. Bigram matching — join adjacent tokens to catch compound names
        self._match_bigrams(query_tokens, result)

        # 3. Synonym table — conceptual phrase matching
        self._match_synonyms(query_clean, result)

        # 4. Fuzzy matching — catch typos like "definProps", "onmounted"
        self._match_fuzzy(query_tokens, result)

        return result

    def _match_exact(self, query_clean: str, result: EntityMatchResult) -> None:
        """Case-insensitive substring match against entity names."""
        for name_lower, name_original in self._name_lower_map.items():
            if name_original in result.match_sources:
                continue
            if name_lower in query_clean:
                # Verify it's not a substring of a longer word for short names
                if len(name_lower) <= 3 and not _is_word_boundary(query_clean, name_lower):
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
        if not self._fuzzy_candidates:
            return

        for token in tokens:
            if len(token) < FUZZY_MIN_LENGTH:
                continue

            matches = process.extract(
                token,
                self._fuzzy_candidates,
                scorer=fuzz.ratio,
                limit=3,
                score_cutoff=FUZZY_MIN_SCORE,
            )

            for match_name, score, _ in matches:
                # Skip if already matched by a higher-priority method
                if match_name in result.match_sources:
                    continue
                # Skip exact matches (already handled)
                if match_name.lower() == token:
                    continue
                result.entities.append(match_name)
                result.match_sources[match_name] = "fuzzy"


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
    pattern = r"(?:^|[\s\-_.,;:!?()`]){}(?:$|[\s\-_.,;:!?()`])".format(re.escape(term))
    return bool(re.search(pattern, text))
