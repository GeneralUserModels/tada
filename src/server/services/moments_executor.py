"""Thin wrapper around apps.moments.execute for the server scheduler."""

from __future__ import annotations

from apps.moments.execute import run as execute_moment, _parse_frontmatter as parse_frontmatter

__all__ = ["execute_moment", "parse_frontmatter"]
