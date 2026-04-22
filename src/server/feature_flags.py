"""Centralized feature flag registry and helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.config import ServerConfig

FEATURE_FLAG_DEFAULTS: dict[str, bool] = {
    # Top-level features
    "memory": True,
    "moments": True,
    "seeker": False,
    "tabracadabra": True,
    "tinker": False,
    # Connectors — flags on so the toggles show in Settings; initial on/off state is
    # controlled via `disabled_connectors` in tada-config.defaults.json so connectors
    # don't auto-start and trigger TCC prompts on first launch.
    "connector_screen": True,
    "connector_gmail": True,
    "connector_calendar": True,
    "connector_outlook_email": True,
    "connector_outlook_calendar": True,
    "connector_notifications": True,
    "connector_filesystem": True,
    # Audio connectors
    "connector_microphone": True,
    "connector_system_audio": True,
    # OS-level permissions
    "permission_screen": True,
    "permission_notifications": True,
    "permission_accessibility": True,
    "permission_browser_cookies": True,
    "permission_microphone": True,
    "permission_system_audio": True,
}


def is_enabled(config: ServerConfig, flag_name: str) -> bool:
    """Return whether *flag_name* is enabled, falling back to the registry default."""
    return config.feature_flags.get(flag_name, FEATURE_FLAG_DEFAULTS.get(flag_name, True))
