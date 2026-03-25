"""Plugin discovery and loading via module path imports.

Per eng review decision: module path only for v1. entry_points deferred
until third-party plugins exist.

Plugin loading flow:
    YAML config module path → importlib → getattr(module, class_name) → instance
"""

from __future__ import annotations

import importlib
from typing import Any

from sentinelai.core.errors import PluginLoadError


def load_plugin(module_path: str, expected_base_class: type | None = None) -> Any:
    """Load a plugin class from a dotted module path.

    The module path format is: 'sentinelai.plugins.triage.claude'
    The plugin class must be the single public class in the module that
    inherits from the expected_base_class (if specified).

    Args:
        module_path: Dotted Python module path.
        expected_base_class: If provided, the loaded class must be a subclass.

    Returns:
        An instance of the plugin class (constructed with no arguments).

    Raises:
        PluginLoadError: If the module doesn't exist, has no suitable class,
            or the class doesn't implement the expected contract.
    """
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise PluginLoadError(
            f"Plugin module not found: {module_path}. Check your sentinelai.yaml pipeline config. Error: {e}"
        ) from e
    except Exception as e:
        raise PluginLoadError(f"Failed to import plugin module {module_path}: {e}") from e

    # Find the plugin class: the first public class that is a subclass
    # of expected_base_class (if specified), or any public class otherwise.
    candidates = []
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        if not isinstance(attr, type):
            continue
        if attr.__module__ != module.__name__:
            continue  # Skip re-exported imports
        if expected_base_class and not issubclass(attr, expected_base_class):
            continue
        if expected_base_class and attr is expected_base_class:
            continue  # Skip the ABC itself
        candidates.append(attr)

    if not candidates:
        base_name = expected_base_class.__name__ if expected_base_class else "any class"
        raise PluginLoadError(
            f"No plugin class found in {module_path} that implements {base_name}. "
            f"The module must contain a public class that subclasses {base_name}."
        )

    if len(candidates) > 1:
        names = [c.__name__ for c in candidates]
        raise PluginLoadError(
            f"Multiple plugin classes found in {module_path}: {names}. "
            f"Each plugin module should contain exactly one public plugin class."
        )

    plugin_class = candidates[0]

    try:
        return plugin_class()
    except Exception as e:
        raise PluginLoadError(
            f"Failed to instantiate plugin {plugin_class.__name__} from {module_path}: {e}"
        ) from e
