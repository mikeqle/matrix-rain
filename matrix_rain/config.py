"""Persistent configuration for matrix-rain.

Config is stored as JSON at ~/.config/matrix-rain/config.json.
Only explicitly set values are saved; missing keys fall back to the
classic preset defaults at runtime.
"""

import json
import os
from pathlib import Path

from .constants import COLOR_NAMES, PRESETS

# Keys that can be persisted and their validation/clamping rules.
_VALID_KEYS = {
    "preset", "speed", "density", "color", "rainbow",
    "fps", "trail_min", "trail_max", "message",
}


def _default_config_path() -> Path:
    """Return the default config file path, computed lazily so that
    ``Path.home()`` is not called at import time.  This avoids crashes
    in environments where HOME is unset (containers, CI, service accounts)."""
    return Path.home() / ".config" / "matrix-rain" / "config.json"


def config_path() -> Path:
    """Return the path to the config file."""
    return _default_config_path()


def load_config(path: Path | None = None) -> dict:
    """Load saved config from disk.  Returns an empty dict if the file
    does not exist or is not valid JSON."""
    p = path or _default_config_path()
    try:
        with open(p) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        # Only return recognised keys with valid types/ranges.
        return _clamp({k: v for k, v in data.items() if k in _VALID_KEYS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(updates: dict, path: Path | None = None) -> dict:
    """Merge *updates* into the saved config and write to disk.
    Returns the resulting config dict.

    When *updates* contains a ``preset`` key, any previously saved
    override keys that the preset would set are dropped first — unless
    they also appear in *updates* (i.e. explicitly passed in the same
    command).  This ensures ``config --preset storm`` actually switches
    to the storm theme instead of being masked by stale overrides.
    """
    p = path or _default_config_path()
    existing = load_config(p)

    if "preset" in updates:
        preset_keys = set(PRESETS.get(updates["preset"], {}).keys())
        for k in preset_keys - set(updates.keys()):
            existing.pop(k, None)

    existing.update(updates)

    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(existing, f, indent=2, sort_keys=True)
        f.write("\n")
    return existing


def reset_config(path: Path | None = None) -> None:
    """Delete the config file if it exists."""
    p = path or _default_config_path()
    try:
        p.unlink()
    except FileNotFoundError:
        pass


def _clamp(updates: dict) -> dict:
    """Validate and clamp values in *updates*.  Returns a cleaned copy.
    Silently drops entries that cannot be coerced to the correct type."""
    out = {}
    for k, v in updates.items():
        try:
            if k == "speed" and v is not None:
                out[k] = max(0.1, min(4.0, float(v)))
            elif k == "density" and v is not None:
                out[k] = max(0.1, min(3.0, float(v)))
            elif k == "fps" and v is not None:
                out[k] = max(10, min(60, int(v)))
            elif k == "trail_min" and v is not None:
                out[k] = max(0.05, min(1.0, float(v)))
            elif k == "trail_max" and v is not None:
                out[k] = max(0.1, min(2.0, float(v)))
            elif k == "color" and v is not None:
                if v in COLOR_NAMES:
                    out[k] = v
            elif k == "rainbow" and v is not None:
                if isinstance(v, bool):
                    out[k] = v
                elif isinstance(v, str):
                    if v.lower() in ("true", "1", "yes"):
                        out[k] = True
                    elif v.lower() in ("false", "0", "no"):
                        out[k] = False
                    # else: drop unrecognised string
                elif isinstance(v, (int, float)):
                    out[k] = bool(v)
                # else: drop other types
            elif k == "preset" and v is not None:
                if v in PRESETS:
                    out[k] = v
            elif k == "message" and v is not None:
                out[k] = str(v)
        except (ValueError, TypeError):
            pass  # drop unparseable entries
    return out


def resolve_config(saved: dict | None = None) -> dict:
    """Build a complete runtime config by merging saved config over
    preset defaults.

    1. Start with the classic preset (or the saved preset if set).
    2. Layer saved overrides on top.
    """
    if saved is None:
        saved = load_config()

    preset_name = saved.get("preset", "classic")
    base = dict(PRESETS.get(preset_name, PRESETS["classic"]))

    for k in ("speed", "density", "color", "rainbow", "fps",
              "trail_min", "trail_max", "message"):
        if k in saved:
            base[k] = saved[k]

    return base


def format_config(saved: dict | None = None) -> str:
    """Return a human-readable representation of the current config."""
    if saved is None:
        saved = load_config()

    resolved = resolve_config(saved)
    lines = []

    if saved:
        lines.append("Saved config:")
        for k in sorted(saved):
            lines.append(f"  {k}: {saved[k]}")
        lines.append("")

    lines.append("Effective config (with defaults):")
    for k in sorted(resolved):
        marker = " *" if k in saved else ""
        lines.append(f"  {k}: {resolved[k]}{marker}")

    if saved:
        lines.append("")
        lines.append("  (* = explicitly configured)")

    return "\n".join(lines)
