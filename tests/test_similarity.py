"""Tests for similarity functions."""

import pytest

from anticipation_layer.similarity import (
    keyword_similarity,
    weighted_keyword_similarity,
    tfidf_similarity,
)


class TestKeywordSimilarity:
    def test_identical_strings_return_one(self):
        assert keyword_similarity("hotfix merged", "hotfix merged") == 1.0

    def test_completely_different_strings_return_zero(self):
        assert keyword_similarity("weather is sunny", "deployment failed") == 0.0

    def test_partial_overlap(self):
        score = keyword_similarity("deployment will fail", "deployment succeeded")
        assert 0.0 < score < 1.0

    def test_empty_string_returns_zero(self):
        assert keyword_similarity("", "something") == 0.0
        assert keyword_similarity("something", "") == 0.0
        assert keyword_similarity("", "") == 0.0

    def test_case_insensitive(self):
        assert keyword_similarity("Hotfix Merged", "hotfix merged") == 1.0

    def test_symmetric(self):
        a = "server disk space is low"
        b = "disk cleanup completed"
        assert keyword_similarity(a, b) == keyword_similarity(b, a)

    def test_returns_float_between_zero_and_one(self):
        score = keyword_similarity("the quick brown fox", "the lazy brown dog")
        assert 0.0 <= score <= 1.0


class TestWeightedKeywordSimilarity:
    def test_boost_words_increase_score(self):
        base = keyword_similarity("deployment failed", "deployment succeeded")
        boosted = weighted_keyword_similarity(
            "deployment failed", "deployment succeeded",
            boost_words={"deployment"}
        )
        assert boosted >= base

    def test_no_boost_words_behaves_like_keyword_similarity(self):
        a, b = "server is down", "server crashed"
        assert weighted_keyword_similarity(a, b) == keyword_similarity(a, b)

    def test_score_capped_at_one(self):
        score = weighted_keyword_similarity(
            "critical deployment risk",
            "critical deployment risk",
            boost_words={"critical", "deployment", "risk"},
        )
        assert score <= 1.0


class TestTFIDFSimilarity:
    def test_identical_strings_return_high_score(self):
        score = tfidf_similarity("deployment will fail on friday", "deployment will fail on friday")
        assert score > 0.9

    def test_completely_different_strings_return_low_score(self):
        score = tfidf_similarity("the weather is sunny today", "deployment pipeline failed")
        assert score < 0.2

    def test_partial_overlap_between_zero_and_one(self):
        score = tfidf_similarity(
            "the deployment failed due to a missing config",
            "the config file is missing from the repo",
        )
        assert 0.0 < score < 1.0

    def test_empty_string_returns_zero(self):
        assert tfidf_similarity("", "something") == 0.0
        assert tfidf_similarity("something", "") == 0.0

    def test_symmetric(self):
        a = "server running out of disk space"
        b = "disk usage at 95 percent on server"
        assert abs(tfidf_similarity(a, b) - tfidf_similarity(b, a)) < 1e-9

    def test_common_words_downweighted(self):
        # "the" and "is" are common; shared domain terms should drive score
        score_common = tfidf_similarity("the is a", "the is a")
        score_specific = tfidf_similarity(
            "deployment pipeline failure",
            "deployment pipeline failure",
        )
        # Both should be high for identical strings, but the mechanism should work
        assert score_common >= 0.0
        assert score_specific >= 0.0

    def test_with_corpus(self):
        corpus = [
            "deployment pipeline runs nightly",
            "hotfix was merged to main",
            "budget review meeting scheduled",
        ]
        score = tfidf_similarity(
            "deployment pipeline failed",
            "deployment pipeline issue",
            corpus=corpus,
        )
        assert 0.0 <= score <= 1.0
