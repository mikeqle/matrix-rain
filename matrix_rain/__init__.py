"""Matrix Digital Rain — Terminal Effect."""

from .cli import cli_entry, config_from_args, handle_config_command, main, parse_args
from .config import (
    config_path,
    format_config,
    load_config,
    reset_config,
    resolve_config,
    save_config,
)
from .constants import (
    BLOCK_FONT,
    CHARSET,
    COLOR_NAMES,
    DIGITS,
    FONT_GAP,
    FONT_H,
    FONT_W,
    KATAKANA,
    LATIN,
    PRESETS,
    RAINBOW_SEQUENCE,
    REVEAL_FAST_SECS,
    REVEAL_HOLD_SECS,
    REVEAL_MIN_SPEED,
    REVEAL_SLOW_SECS,
    SYMBOLS,
)
from .engine import MatrixRain
from .ipc import MessageListener, default_socket_path, send_message
from .stream import Stream

# Backwards-compatible aliases for the old underscore-prefixed names
_FONT_H = FONT_H
_FONT_W = FONT_W
_FONT_GAP = FONT_GAP
_REVEAL_SLOW_SECS = REVEAL_SLOW_SECS
_REVEAL_HOLD_SECS = REVEAL_HOLD_SECS
_REVEAL_FAST_SECS = REVEAL_FAST_SECS
_REVEAL_MIN_SPEED = REVEAL_MIN_SPEED
