"""BM25 sparse vector generation using bm25s.

Fits a BM25 model on the corpus vocabulary and generates sparse vectors
compatible with Qdrant's sparse vector format.
"""

import json
import logging
from pathlib import Path

import bm25s
from qdrant_client.models import SparseVector

logger = logging.getLogger(__name__)


class BM25Model:
    """BM25 sparse vector generator for corpus chunks."""

    def __init__(self) -> None:
        self._model: bm25s.BM25 | None = None
        self._vocab: dict[str, int] = {}

    @property
    def is_fitted(self) -> bool:
        return self._model is not None

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    def fit(self, corpus_texts: list[str]) -> None:
        """Fit the BM25 model on corpus texts."""
        tokenized = bm25s.tokenize(corpus_texts)
        self._model = bm25s.BM25()
        self._model.index(tokenized)
        self._vocab = dict(self._model.vocab_dict)
        logger.info(
            "BM25 model fitted: %d documents, %d vocab tokens",
            len(corpus_texts),
            len(self._vocab),
        )

    def get_doc_sparse_vectors(self, texts: list[str]) -> list[SparseVector]:
        """Generate sparse vectors for document texts.

        The texts must be the same corpus used in fit(), in the same order.
        This extracts per-document BM25 score vectors from the fitted model.
        """
        if self._model is None:
            raise RuntimeError("BM25 model not fitted. Call fit() first.")

        scores = self._model.scores
        data = scores["data"]
        indices = scores["indices"]
        indptr = scores["indptr"]
        num_tokens = len(indptr) - 1

        sparse_vectors = []
        for doc_idx in range(len(texts)):
            doc_token_ids = []
            doc_values = []
            for token_id in range(num_tokens):
                col_start = indptr[token_id]
                col_end = indptr[token_id + 1]
                for j in range(col_start, col_end):
                    if indices[j] == doc_idx:
                        doc_token_ids.append(token_id)
                        doc_values.append(float(data[j]))
                        break

            sparse_vectors.append(SparseVector(indices=doc_token_ids, values=doc_values))

        return sparse_vectors

    def get_query_sparse_vector(self, query: str) -> SparseVector:
        """Generate a sparse vector for a query string.

        Maps query tokens to the model vocabulary and creates a sparse vector
        with value 1.0 for each matched token. The dot product with document
        vectors then sums the BM25 scores for matching tokens.
        """
        if self._model is None:
            raise RuntimeError("BM25 model not fitted. Call fit() first.")

        # Tokenize query using same tokenizer
        query_tokenized = bm25s.tokenize([query])
        query_token_strs = []
        query_vocab = query_tokenized.vocab
        for token_id in query_tokenized.ids[0]:
            for word, idx in query_vocab.items():
                if idx == token_id:
                    query_token_strs.append(word)
                    break

        # Map to model vocabulary
        matched_ids = []
        for word in query_token_strs:
            if word in self._vocab:
                matched_ids.append(self._vocab[word])

        if not matched_ids:
            return SparseVector(indices=[0], values=[0.0])

        # Deduplicate
        matched_ids = sorted(set(matched_ids))
        values = [1.0] * len(matched_ids)

        return SparseVector(indices=matched_ids, values=values)

    def save(self, path: Path) -> None:
        """Save the fitted BM25 model to disk."""
        if self._model is None:
            raise RuntimeError("BM25 model not fitted. Call fit() first.")

        path.mkdir(parents=True, exist_ok=True)
        self._model.save(str(path / "bm25s_model"))

        # Also save vocab separately for quick loading
        with open(path / "vocab.json", "w") as f:
            json.dump(self._vocab, f)

        logger.info("BM25 model saved to %s", path)

    def load(self, path: Path) -> None:
        """Load a previously fitted BM25 model from disk."""
        self._model = bm25s.BM25.load(str(path / "bm25s_model"))
        self._vocab = dict(self._model.vocab_dict)

        with open(path / "vocab.json") as f:
            saved_vocab = json.load(f)
            # Verify consistency
            if set(saved_vocab.keys()) != set(self._vocab.keys()):
                logger.warning("Vocab mismatch between saved and loaded model")

        logger.info("BM25 model loaded from %s (%d vocab tokens)", path, len(self._vocab))
