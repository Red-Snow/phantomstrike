"""
PhantomStrike Plugin Registry — auto-discovers and manages all tool plugins.

Scans the plugins/ subpackages, imports them, and makes them available
to the MCP server, REST API, and decision engine.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Optional

from phantomstrike.plugins.base import BaseToolPlugin, ToolCategory
from phantomstrike.utils.logging import get_logger

log = get_logger("registry")


class PluginRegistry:
    """
    Central registry for all tool plugins.

    Plugins are auto-discovered from sub-packages (network/, webapp/, etc.)
    or manually registered.
    """

    def __init__(self):
        self._plugins: dict[str, BaseToolPlugin] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, plugin: BaseToolPlugin) -> None:
        """Register a single plugin instance."""
        if plugin.name in self._plugins:
            log.warning(f"Plugin '{plugin.name}' already registered — overwriting")
        self._plugins[plugin.name] = plugin
        status = "✅ available" if plugin.is_available() else "⚠️  missing binaries"
        log.info(f"Registered plugin: [tool]{plugin.name}[/tool] ({status})")

    def auto_discover(self) -> int:
        """
        Auto-discover and register all plugins from sub-packages.

        Scans plugins/network/, plugins/webapp/, etc. for classes
        that subclass BaseToolPlugin.

        Returns:
            Number of plugins discovered.
        """
        plugins_dir = Path(__file__).parent
        count = 0

        for sub_package_info in pkgutil.iter_modules([str(plugins_dir)]):
            if not sub_package_info.ispkg:
                continue

            sub_package_path = plugins_dir / sub_package_info.name

            for module_info in pkgutil.iter_modules([str(sub_package_path)]):
                if module_info.name.startswith("_"):
                    continue

                module_path = f"phantomstrike.plugins.{sub_package_info.name}.{module_info.name}"
                try:
                    module = importlib.import_module(module_path)

                    # Find all BaseToolPlugin subclasses in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseToolPlugin)
                            and attr is not BaseToolPlugin
                            and attr.name  # Must have a name set
                        ):
                            self.register(attr())
                            count += 1
                except Exception as e:
                    log.warning(f"Failed to load plugin module {module_path}: {e}")

        log.info(f"Auto-discovery complete: {count} plugins registered")
        return count

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseToolPlugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def get_all(self) -> dict[str, BaseToolPlugin]:
        """Get all registered plugins."""
        return dict(self._plugins)

    def get_available(self) -> dict[str, BaseToolPlugin]:
        """Get only plugins whose binaries are installed."""
        return {name: p for name, p in self._plugins.items() if p.is_available()}

    def get_by_category(self, category: ToolCategory) -> dict[str, BaseToolPlugin]:
        """Get plugins filtered by category."""
        return {name: p for name, p in self._plugins.items() if p.category == category}

    def get_names(self) -> list[str]:
        """Get all registered plugin names."""
        return list(self._plugins.keys())

    # ── Info ──────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a summary of all registered plugins."""
        available = sum(1 for p in self._plugins.values() if p.is_available())
        categories: dict[str, int] = {}
        for p in self._plugins.values():
            cat = p.category.value
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_plugins": len(self._plugins),
            "available": available,
            "unavailable": len(self._plugins) - available,
            "categories": categories,
            "plugins": [p.get_metadata() for p in self._plugins.values()],
        }

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins


# ── Global singleton ──────────────────────────────────────────────────────────
registry = PluginRegistry()
