"""
Configuration management for the overlay window.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict


CONFIG_FILE = "overlay_config.json"


@dataclass
class OverlayConfig:
    """Configuration for the overlay window."""

    # Mini circular button
    mini_size: int = 50
    mini_x: int = 10
    mini_y: int = 10
    mini_opacity: float = 0.90

    # Expanded panel (percentage of screen width)
    expanded_width_pct: float = 0.30
    expanded_opacity: float = 0.92

    # Appearance
    font_family: str = "Segoe UI"
    font_size: int = 13
    bg_color: str = "#1e1e1e"
    fg_color: str = "#ffffff"
    accent_color: str = "#0078d4"

    @classmethod
    def load(cls) -> "OverlayConfig":
        """Load config from disk, or return defaults."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        """Save config to disk."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)