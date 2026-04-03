"""Shared pytest fixtures for the Anticipation Layer test suite."""

import shutil
import tempfile

import pytest

from anticipation_layer.models import Anticipation, Category, Horizon, Impact
from anticipation_layer.storage import Storage
from anticipation_layer.layer import AnticipationLayer


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def tmp_storage(tmp_dir):
    return Storage(tmp_dir)


@pytest.fixture
def basic_layer(tmp_dir):
    return AnticipationLayer(storage_dir=tmp_dir)


@pytest.fixture
def layer_with_anticipations(tmp_dir):
    layer = AnticipationLayer(storage_dir=tmp_dir)
    layer.add(
        prediction="Deployment will fail on Friday due to untested hotfix",
        horizon=Horizon.SHORT_TERM,
        category=Category.RISK,
        impact=Impact.HIGH,
        confidence=0.8,
    )
    layer.add(
        prediction="Budget will be exceeded next quarter",
        horizon=Horizon.MEDIUM_TERM,
        category=Category.RISK,
        impact=Impact.MEDIUM,
        confidence=0.6,
    )
    layer.add(
        prediction="Team will grow by 30% this year",
        horizon=Horizon.LONG_TERM,
        category=Category.OPPORTUNITY,
        impact=Impact.HIGH,
        confidence=0.5,
    )
    return layer
