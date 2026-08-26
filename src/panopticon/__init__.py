"""Panopticon — local-first MCP behavior observatory.

We don't watch you. We watch your MCPs.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("panopticon-mcp")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+dev"

SCHEMA_VERSION = "1.0"
