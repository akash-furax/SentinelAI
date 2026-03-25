"""Tests for plugin loading."""

import pytest

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.errors import PluginLoadError
from sentinelai.core.plugin import load_plugin


class TestLoadPlugin:
    def test_loads_file_source(self):
        plugin = load_plugin("sentinelai.plugins.sources.file_source", AlertSource)
        assert isinstance(plugin, AlertSource)

    def test_loads_claude_triage(self):
        plugin = load_plugin("sentinelai.plugins.triage.claude", TriageEngine)
        assert isinstance(plugin, TriageEngine)

    def test_invalid_module_raises(self):
        with pytest.raises(PluginLoadError, match="Plugin module not found"):
            load_plugin("sentinelai.plugins.nonexistent", AlertSource)

    def test_wrong_base_class_raises(self):
        with pytest.raises(PluginLoadError, match="No plugin class found"):
            load_plugin("sentinelai.plugins.sources.file_source", TriageEngine)
