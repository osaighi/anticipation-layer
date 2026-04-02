"""
Similarity functions for comparing events against anticipations.

Provides multiple strategies from simple (keyword overlap) to 
sophisticated (embedding-based semantic similarity).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def keyword_similarity(a: str, b: str) -> float:
    """
    Simple Jaccard similarity on word sets.
    No dependencies required. Fast but imprecise.

    Returns:
        Float between 0.0 and 1.0
    """
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def weighted_keyword_similarity(a: str, b: str, boost_words: Optional[set[str]] = None) -> float:
    """
    Keyword similarity with optional boosting for domain-specific terms.

    Args:
        a, b: Strings to compare.
        boost_words: Set of important words that get 2x weight.

    Returns:
        Float between 0.0 and 1.0
    """
    boost_words = boost_words or set()
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b

    # Boost score if important words match
    boosted = intersection & boost_words
    base_score = len(intersection) / len(union)
    boost = len(boosted) * 0.1  # Each boost word adds 0.1

    return min(1.0, base_score + boost)


def tfidf_similarity(a: str, b: str, corpus: Optional[list[str]] = None) -> float:
    """
    TF-IDF based cosine similarity. Better than keyword overlap
    because it downweights common words.

    No external dependencies — pure Python implementation.

    Args:
        a, b: Strings to compare.
        corpus: Optional background corpus for IDF computation.
                If None, IDF is computed from just a and b.

    Returns:
        Float between 0.0 and 1.0
    """
    import re
    from collections import Counter

    def tokenize(text: str) -> list[str]:
        return re.findall(r'\b[a-z]+\b', text.lower())

    tokens_a = tokenize(a)
    tokens_b = tokenize(b)

    if not tokens_a or not tokens_b:
        return 0.0

    # Build corpus for IDF
    docs = [tokens_a, tokens_b]
    if corpus:
        docs.extend(tokenize(doc) for doc in corpus)
    n_docs = len(docs)

    # Document frequency
    df = Counter()
    for doc in docs:
        unique = set(doc)
        for word in unique:
            df[word] += 1

    # TF-IDF vectors
    def tfidf_vector(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        total = len(tokens)
        vec = {}
        for word, count in tf.items():
            idf = math.log(n_docs / (1 + df.get(word, 0)))
            vec[word] = (count / total) * idf
        return vec

    vec_a = tfidf_vector(tokens_a)
    vec_b = tfidf_vector(tokens_b)

    # Cosine similarity
    all_words = set(vec_a.keys()) | set(vec_b.keys())
    dot = sum(vec_a.get(w, 0) * vec_b.get(w, 0) for w in all_words)
    norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


class EmbeddingSimilarity:
    """
    Semantic similarity using sentence-transformers embeddings.

    Requires: pip install anticipation-layer[embeddings]

    This is the most accurate method but requires downloading a model
    (~80MB) on first use.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for EmbeddingSimilarity. "
                "Install with: pip install anticipation-layer[embeddings]"
            )

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self._cache: dict[str, list[float]] = {}

    def _embed(self, text: str) -> list[float]:
        """Get embedding for text, with caching."""
        if text not in self._cache:
            self._cache[text] = self.model.encode(text).tolist()
        return self._cache[text]

    def __call__(self, a: str, b: str) -> float:
        """
        Compute semantic similarity between two texts.

        Returns:
            Float between 0.0 and 1.0
        """
        emb_a = self._embed(a)
        emb_b = self._embed(b)

        # Cosine similarity
        dot = sum(x * y for x, y in zip(emb_a, emb_b))
        norm_a = math.sqrt(sum(x ** 2 for x in emb_a))
        norm_b = math.sqrt(sum(x ** 2 for x in emb_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        sim = dot / (norm_a * norm_b)
        # Normalize from [-1, 1] to [0, 1]
        return (sim + 1) / 2

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()
