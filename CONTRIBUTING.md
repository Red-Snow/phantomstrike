# Contributing to PhantomStrike

Thank you for your interest in contributing! Here's how to get started.

## Quick Start

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/Red-Snow/phantomstrike.git`
3. **Install** in dev mode:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```
4. **Create** a feature branch: `git checkout -b feature/your-feature`
5. **Make** your changes
6. **Test**: `pytest`
7. **Submit** a Pull Request

## Adding a New Tool Plugin

The easiest and most impactful contribution is adding a new tool plugin.

### Steps

1. Choose a category: `network/`, `webapp/`, `cloud/`, `osint/`, `password/`, or `binary/`
2. Create a new file: `src/phantomstrike/plugins/<category>/your_tool.py`
3. Implement the `BaseToolPlugin` interface (see [Plugin Development](README.md#-plugin-development))
4. Test locally — the plugin is auto-discovered on startup

### Plugin Checklist

- [ ] Inherits from `BaseToolPlugin`
- [ ] Has `name`, `category`, `description`, `required_binaries` set
- [ ] Has a typed `InputSchema` with `Field` descriptions
- [ ] `build_command()` returns a list (no `shell=True`)
- [ ] `parse_output()` returns structured `ToolResult` with `Finding` objects
- [ ] Uses machine-parseable output format where possible (JSON, XML)

## Code Style

- Python 3.10+ features are welcome
- Follow PEP 8 (enforced by `ruff`)
- Use type hints everywhere
- Write docstrings for public methods

## Reporting Issues

- Search existing issues first
- Include your OS, Python version, and PhantomStrike version
- Include the full error traceback if applicable
