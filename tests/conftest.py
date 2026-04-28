"""
PhantomStrike Test Fixtures
"""

import pytest
from phantomstrike.plugins.registry import PluginRegistry


@pytest.fixture
def fresh_registry():
    """A clean plugin registry for each test."""
    return PluginRegistry()


@pytest.fixture
def loaded_registry():
    """A registry with auto-discovered plugins."""
    reg = PluginRegistry()
    reg.auto_discover()
    return reg
