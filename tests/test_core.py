"""Tests for the Anticipation Layer core functionality."""

import os
import json
import shutil
import tempfile
import pytest
from datetime import datetime, timedelta

from anticipation_layer.models import (
    Anticipation, Horizon, Category, Impact, Status, DECAY_RATES, DEFAULT_TTL,
)
from anticipation_layer.storage import Storage
from anticipation_layer.update_engine import UpdateEngine
from anticipation_layer.context_assembly import ContextAssembly
from anticipation_layer.layer import AnticipationLayer


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


# ─── Model Tests ──────────────────────────────────────────────────


class TestAnticipation:
    def test_create_basic(self):
        ant = Anticipation(
            prediction="Deployment may fail",
            horizon=Horizon.SHORT_TERM,
        )
        assert ant.status == Status.ACTIVE
        assert ant.confidence == 0.5
        assert ant.horizon == Horizon.SHORT_TERM
        assert ant.id.startswith("ant-")

    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            Anticipation(prediction="test", horizon=Horizon.SHORT_TERM, confidence=1.5)

    def test_default_expiry(self):
        ant = Anticipation(prediction="test", horizon=Horizon.SHORT_TERM)
        expected = ant.created + DEFAULT_TTL[Horizon.SHORT_TERM]
        assert abs((ant.expires - expected).total_seconds()) < 1

    def test_weight_decreases_over_time(self):
        ant = Anticipation(
            prediction="test",
            horizon=Horizon.SHORT_TERM,
            confidence=0.8,
            impact=Impact.HIGH,
        )
        initial_weight = ant.weight
        # Simulate aging by backdating creation
        ant.created = datetime.utcnow() - timedelta(days=3)
        assert ant.weight < initial_weight

    def test_invalidate(self):
        ant = Anticipation(prediction="test", horizon=Horizon.SHORT_TERM)
        ant.invalidate("contradicting event")
        assert ant.status == Status.INVALIDATED
        assert ant.invalidated_by == "contradicting event"

    def test_realize(self):
        ant = Anticipation(prediction="test", horizon=Horizon.SHORT_TERM)
        ant.realize()
        assert ant.status == Status.REALIZED
        assert ant.realized is True
        assert ant.realization_date is not None

    def test_serialization_roundtrip(self):
        ant = Anticipation(
            prediction="Budget will be exceeded",
            horizon=Horizon.MEDIUM_TERM,
            category=Category.RISK,
            impact=Impact.HIGH,
            confidence=0.75,
            domain="finance",
            suggested_actions=["Review spending"],
        )
        data = ant.to_dict()
        restored = Anticipation.from_dict(data)
        assert restored.prediction == ant.prediction
        assert restored.horizon == ant.horizon
        assert restored.confidence == ant.confidence
        assert restored.domain == ant.domain

    def test_context_string_format(self):
        ant = Anticipation(
            prediction="Risk detected",
            horizon=Horizon.SHORT_TERM,
            category=Category.RISK,
            impact=Impact.HIGH,
            confidence=0.8,
        )
        ctx = ant.to_context_string()
        assert "⚠️" in ctx
        assert "[HIGH]" in ctx
        assert "80%" in ctx


# ─── Storage Tests ────────────────────────────────────────────────


class TestStorage:
    def test_init_creates_files(self, tmp_dir):
        storage = Storage(tmp_dir)
        assert (storage.storage_dir / "short_term.json").exists()
        assert (storage.storage_dir / "medium_term.json").exists()
        assert (storage.storage_dir / "long_term.json").exists()
        assert (storage.storage_dir / "meta.json").exists()
        assert (storage.storage_dir / "invalidations.log").exists()

    def test_add_and_load(self, tmp_dir):
        storage = Storage(tmp_dir)
        ant = Anticipation(prediction="test", horizon=Horizon.SHORT_TERM)
        storage.add(ant)

        loaded = storage.load_horizon(Horizon.SHORT_TERM)
        assert len(loaded) == 1
        assert loaded[0].prediction == "test"

    def test_load_all_active(self, tmp_dir):
        storage = Storage(tmp_dir)
        storage.add(Anticipation(prediction="short", horizon=Horizon.SHORT_TERM))
        storage.add(Anticipation(prediction="medium", horizon=Horizon.MEDIUM_TERM))
        storage.add(Anticipation(prediction="long", horizon=Horizon.LONG_TERM))

        active = storage.load_all_active()
        assert len(active) == 3

    def test_meta_increments(self, tmp_dir):
        storage = Storage(tmp_dir)
        storage.add(Anticipation(prediction="test", horizon=Horizon.SHORT_TERM))
        meta = storage.get_meta()
        assert meta["total_generated"] == 1


# ─── Update Engine Tests ──────────────────────────────────────────


class TestUpdateEngine:
    def test_invalidation_on_matching_event(self, tmp_dir):
        storage = Storage(tmp_dir)
        storage.add(Anticipation(
            prediction="Deployment will fail due to hotfix 342",
            horizon=Horizon.SHORT_TERM,
            confidence=0.8,
        ))

        engine = UpdateEngine(storage=storage)
        invalidated = engine.check_invalidation(
            "Deployment will fail because hotfix 342 not merged",
            threshold=0.3,
        )
        assert len(invalidated) >= 1

    def test_no_invalidation_on_unrelated_event(self, tmp_dir):
        storage = Storage(tmp_dir)
        storage.add(Anticipation(
            prediction="Deployment will fail",
            horizon=Horizon.SHORT_TERM,
        ))

        engine = UpdateEngine(storage=storage)
        invalidated = engine.check_invalidation(
            "The weather is sunny today",
            threshold=0.5,
        )
        assert len(invalidated) == 0

    def test_decay_detects_expired(self, tmp_dir):
        storage = Storage(tmp_dir)
        ant = Anticipation(prediction="old one", horizon=Horizon.SHORT_TERM)
        ant.expires = datetime.utcnow() - timedelta(hours=1)  # Already expired
        storage.add(ant)

        engine = UpdateEngine(storage=storage)
        result = engine.check_decay()
        assert len(result["expired"]) == 1


# ─── Context Assembly Tests ───────────────────────────────────────


class TestContextAssembly:
    def test_format_context_returns_string(self, tmp_dir):
        storage = Storage(tmp_dir)
        storage.add(Anticipation(
            prediction="Deployment risk on Thursday",
            horizon=Horizon.SHORT_TERM,
            category=Category.RISK,
            impact=Impact.HIGH,
        ))

        assembly = ContextAssembly(storage=storage)
        ctx = assembly.format_context("deployment thursday")
        assert "Anticipations" in ctx or ctx == ""

    def test_empty_context_when_no_anticipations(self, tmp_dir):
        storage = Storage(tmp_dir)
        assembly = ContextAssembly(storage=storage)
        ctx = assembly.format_context("anything")
        assert ctx == ""


# ─── Integration Tests ────────────────────────────────────────────


class TestAnticipationLayer:
    def test_full_workflow(self, tmp_dir):
        layer = AnticipationLayer(storage_dir=tmp_dir)

        # Add
        ant = layer.add(
            prediction="Server will run out of disk space within 3 days",
            horizon=Horizon.SHORT_TERM,
            category=Category.RISK,
            impact=Impact.HIGH,
            confidence=0.7,
        )
        assert ant.id is not None

        # Get context
        ctx = layer.get_context("disk space server")
        assert len(ctx) > 0

        # Register event
        invalidated = layer.register_event("Disk cleanup freed 200GB of space")
        # May or may not invalidate depending on similarity

        # Metrics
        metrics = layer.metrics()
        assert metrics["total_generated"] == 1
