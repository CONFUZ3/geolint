"""
Interactive mode for GeoLint.

Provides a stateful REPL shell (`geolint` / `geolint shell`) and a guided
wizard (`geolint wizard`) built on top of the same core engine. The
:class:`~geolint.interactive.session.GeoLintSession` holds the working
dataset and is UI-agnostic; rendering lives in
:mod:`geolint.interactive.ui`.
"""

from geolint.interactive.session import GeoLintSession, SessionError

__all__ = ["GeoLintSession", "SessionError"]
