"""Tests for the Anticipation Layer core functionality."""

import os
import json
import pytest
from datetime import datetime, timedelta

from anticipation_layer.models import (
    Anticipation, Horizon, Category, Impact, Status, DECAY_RATES, DEFAULT_TTL,
)
from anticipation_layer.storage import Storage
from anticipation_layer.update_engine import UpdateEngine
from anticipation_layer.context_assembly import ContextAssembly
from anticipation_layer.layer import AnticipationLayer


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


# ─── Context Assembly — Token Budget Tests ───────────────────────


class TestContextAssemblyTruncation:
    def test_top_k_not_mutated_after_truncation(self, tmp_dir):
        """Regression: top_k must not be permanently decremented on self."""
        storage = Storage(tmp_dir)
        # Add enough anticipations with long predictions to exceed a tiny budget
        for i in range(8):
            storage.add(Anticipation(
                prediction=f"Anticipation number {i}: " + "x" * 120,
                horizon=Horizon.SHORT_TERM,
                category=Category.RISK,
                impact=Impact.HIGH,
                confidence=0.9,
            ))

        assembly = ContextAssembly(storage=storage, top_k=8, max_tokens=50)
        original_top_k = assembly.top_k

        # Call multiple times — each call should be idempotent
        assembly.format_context("deployment risk")
        assembly.format_context("deployment risk")
        assembly.format_context("deployment risk")

        assert assembly.top_k == original_top_k, (
            f"self.top_k was mutated: {original_top_k} → {assembly.top_k}"
        )


# ─── Update Engine — Cascade Tests ───────────────────────────────


class TestCascadeReappraisal:
    def test_cascade_expires_medium_when_short_invalidated_above_threshold(self, tmp_dir):
        storage = Storage(tmp_dir)

        # Add 5 short-term anticipations
        short_ids = []
        for i in range(5):
            ant = Anticipation(
                prediction=f"Short term risk number {i} will happen soon",
                horizon=Horizon.SHORT_TERM,
            )
            storage.add(ant)
            short_ids.append(ant.id)

        # Add 2 medium-term anticipations
        for i in range(2):
            storage.add(Anticipation(
                prediction=f"Medium term plan {i} will proceed",
                horizon=Horizon.MEDIUM_TERM,
            ))

        engine = UpdateEngine(storage=storage, cascade_thresholds={
            Horizon.SHORT_TERM: 0.3,
            Horizon.MEDIUM_TERM: 0.5,
        })

        # Invalidate 3 out of 5 short-term (60% > 30% threshold)
        for ant_id in short_ids[:3]:
            for ant in storage.load_horizon(Horizon.SHORT_TERM):
                if ant.id == ant_id:
                    ant.invalidate("contradicting event")
                    storage.update(ant)

        invalidated = [a for a in storage.load_horizon(Horizon.SHORT_TERM)
                       if a.status == Status.INVALIDATED]
        engine._check_cascade(invalidated)

        # Medium-term anticipations should now be expired (cascade-triggered)
        medium = storage.load_horizon(Horizon.MEDIUM_TERM)
        assert all(a.status == Status.EXPIRED for a in medium), (
            "Expected all medium-term anticipations to be expired after cascade"
        )

    def test_no_cascade_below_threshold(self, tmp_dir):
        storage = Storage(tmp_dir)

        for i in range(5):
            storage.add(Anticipation(
                prediction=f"Short term risk {i}",
                horizon=Horizon.SHORT_TERM,
            ))
        for i in range(2):
            storage.add(Anticipation(
                prediction=f"Medium term plan {i}",
                horizon=Horizon.MEDIUM_TERM,
            ))

        engine = UpdateEngine(storage=storage)

        # Invalidate only 1 out of 5 (20% < 30% threshold)
        short = storage.load_horizon(Horizon.SHORT_TERM)
        short[0].invalidate("minor event")
        storage.update(short[0])

        engine._check_cascade([short[0]])

        medium = storage.load_horizon(Horizon.MEDIUM_TERM)
        assert all(a.status == Status.ACTIVE for a in medium), (
            "Medium-term should remain active when cascade threshold not reached"
        )


# ─── Async Consolidation Tests ────────────────────────────────────


class TestConsolidationAsync:
    async def test_consolidate_generates_when_below_minimum(self, tmp_dir):
        """consolidate() should call generate_fn when active count < 3."""
        generated_calls = []

        async def mock_generate_fn(context, horizon, count):
            generated_calls.append((horizon, count))
            return [
                Anticipation(
                    prediction=f"Generated anticipation for {horizon.value}",
                    horizon=horizon,
                    confidence=0.7,
                )
                for _ in range(count)
            ]

        layer = AnticipationLayer(storage_dir=tmp_dir, generate_fn=mock_generate_fn)
        summary = await layer.consolidate(current_context="Sprint ends Friday")

        assert summary["generated"] > 0
        assert len(generated_calls) > 0

    async def test_consolidate_archives_non_active(self, tmp_dir):
        """consolidate() should archive anticipations that are already non-active."""
        storage = Storage(tmp_dir)
        ant = Anticipation(prediction="Old prediction", horizon=Horizon.SHORT_TERM)
        ant.expire()  # Mark as EXPIRED before storing so step 1 picks it up
        storage.add(ant)

        layer = AnticipationLayer(storage_dir=tmp_dir)
        summary = await layer.consolidate()

        assert summary["archived"] >= 1

    async def test_consolidate_reinforces_surviving_anticipations(self, tmp_dir):
        """Anticipations older than 24h should receive a confidence boost."""
        storage = Storage(tmp_dir)
        ant = Anticipation(
            prediction="Surviving prediction",
            horizon=Horizon.SHORT_TERM,
            confidence=0.5,
        )
        ant.created = datetime.utcnow() - timedelta(hours=30)
        storage.add(ant)

        layer = AnticipationLayer(storage_dir=tmp_dir)
        await layer.consolidate()

        updated = storage.load_horizon(Horizon.SHORT_TERM)
        assert updated[0].confidence > 0.5


# ─── LangGraph Integration Tests ─────────────────────────────────


class TestLangGraphIntegration:
    def test_inject_node_adds_anticipation_context(self, layer_with_anticipations):
        from anticipation_layer.integrations.langgraph import create_anticipation_nodes

        nodes = create_anticipation_nodes(layer_with_anticipations)
        result = nodes.inject({"query": "deployment risk on Friday"})

        assert "anticipation_context" in result
        assert isinstance(result["anticipation_context"], str)

    def test_inject_node_with_messages_state(self, layer_with_anticipations):
        from anticipation_layer.integrations.langgraph import create_anticipation_nodes

        nodes = create_anticipation_nodes(layer_with_anticipations)
        state = {"messages": [{"role": "user", "content": "What are the deployment risks?"}]}
        result = nodes.inject(state)

        assert "anticipation_context" in result

    def test_inject_node_empty_query_returns_empty(self, basic_layer):
        from anticipation_layer.integrations.langgraph import create_anticipation_nodes

        nodes = create_anticipation_nodes(basic_layer)
        result = nodes.inject({})

        assert result["anticipation_context"] == ""

    def test_register_event_node_clears_pending_events(self, layer_with_anticipations):
        from anticipation_layer.integrations.langgraph import create_anticipation_nodes

        nodes = create_anticipation_nodes(layer_with_anticipations)
        result = nodes.register_event({"pending_events": ["Weather is sunny today"]})

        assert result["pending_events"] == []
        assert "needs_refresh" in result

    def test_should_consolidate_routing(self, basic_layer):
        from anticipation_layer.integrations.langgraph import create_anticipation_nodes

        nodes = create_anticipation_nodes(basic_layer)
        assert nodes.should_consolidate({"needs_refresh": True}) == "consolidate"
        assert nodes.should_consolidate({"needs_refresh": False}) == "proceed"
        assert nodes.should_consolidate({}) == "proceed"


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

    def test_config_path_overrides_defaults(self, tmp_dir, tmp_path):
        import yaml

        config = {
            "context_injection": {"top_k": 3, "min_relevance": 0.2, "max_tokens": 200},
            "update_engine": {
                "invalidation_threshold": 0.8,
                "cascade_threshold_short": 0.4,
                "cascade_threshold_medium": 0.6,
                "weight_floor": 0.2,
            },
        }
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml.dump(config))

        layer = AnticipationLayer(storage_dir=tmp_dir, config_path=str(config_file))

        assert layer.context_assembly.top_k == 3
        assert layer.context_assembly.min_relevance == 0.2
        assert layer.context_assembly.max_tokens == 200
        assert layer.engine.invalidation_threshold == 0.8
        assert layer.engine.weight_floor == 0.2
