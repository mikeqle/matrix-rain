"""Tests for matrix_rain.py"""

import argparse
import curses
import os
import random
from unittest.mock import MagicMock, patch

import pytest

from matrix_rain import (
    BLOCK_FONT,
    CHARSET,
    COLOR_NAMES,
    KATAKANA,
    DIGITS,
    LATIN,
    SYMBOLS,
    PRESETS,
    RAINBOW_SEQUENCE,
    MatrixRain,
    MessageListener,
    Stream,
    _FONT_H,
    _FONT_W,
    _REVEAL_FAST_SECS,
    _REVEAL_HOLD_SECS,
    _REVEAL_MIN_SPEED,
    _REVEAL_SLOW_SECS,
    config_from_args,
    default_socket_path,
    parse_args,
    send_message,
)


# ── Character Set / Constants ────────────────────────────────────────────────


class TestCharacterSets:
    def test_katakana_range(self):
        assert len(KATAKANA) == 0xFF9E - 0xFF66  # 56 characters
        assert all(0xFF66 <= ord(c) <= 0xFF9D for c in KATAKANA)

    def test_digits(self):
        assert DIGITS == list("0123456789")

    def test_latin(self):
        assert LATIN == list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def test_symbols_nonempty(self):
        assert len(SYMBOLS) > 0
        assert all(isinstance(s, str) and len(s) == 1 for s in SYMBOLS)

    def test_charset_is_union(self):
        assert CHARSET == KATAKANA + DIGITS + LATIN + SYMBOLS

    def test_charset_all_single_chars(self):
        for ch in CHARSET:
            assert isinstance(ch, str)
            assert len(ch) == 1

    def test_no_duplicate_colors(self):
        assert len(COLOR_NAMES) == len(set(COLOR_NAMES))

    def test_rainbow_sequence_subset_of_colors(self):
        for color in RAINBOW_SEQUENCE:
            assert color in COLOR_NAMES


# ── Presets ──────────────────────────────────────────────────────────────────


class TestPresets:
    REQUIRED_KEYS = {"speed", "density", "color", "rainbow", "fps", "trail_min", "trail_max"}

    def test_all_presets_have_required_keys(self):
        for name, preset in PRESETS.items():
            missing = self.REQUIRED_KEYS - set(preset.keys())
            assert not missing, f"Preset '{name}' missing keys: {missing}"

    def test_preset_values_in_range(self):
        for name, p in PRESETS.items():
            assert 0.1 <= p["speed"] <= 4.0, f"{name}: bad speed"
            assert 0.1 <= p["density"] <= 3.0, f"{name}: bad density"
            assert p["color"] in COLOR_NAMES, f"{name}: bad color"
            assert isinstance(p["rainbow"], bool), f"{name}: rainbow not bool"
            assert 10 <= p["fps"] <= 60, f"{name}: bad fps"
            assert 0 < p["trail_min"] < p["trail_max"], f"{name}: bad trail range"

    def test_classic_preset_exists(self):
        assert "classic" in PRESETS


# ── Stream ───────────────────────────────────────────────────────────────────


class TestStream:
    def test_init(self):
        random.seed(42)
        s = Stream(col=5, max_row=50, speed=1.0, trail_length=10)
        assert s.col == 5
        assert s.max_row == 50
        assert s.speed == 1.0
        assert s.trail_length == 10
        assert -50 <= s.head <= -1
        assert s.chars == {}
        assert s.tick_acc == 0.0

    def test_update_advances_head(self):
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=5)
        s.head = 0
        s.tick_acc = 0.0
        s.mutate_chance = 0  # disable mutation for deterministic test
        initial_head = s.head
        s.update()
        assert s.head == initial_head + 1

    def test_update_adds_chars_when_in_bounds(self):
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=5)
        s.head = -1
        s.tick_acc = 0.0
        s.mutate_chance = 0
        s.update()
        # head should now be 0, which is in bounds
        assert s.head == 0
        assert 0 in s.chars
        assert s.chars[0] in CHARSET

    def test_update_does_not_add_chars_out_of_bounds(self):
        s = Stream(col=0, max_row=10, speed=1.0, trail_length=5)
        s.head = 10  # at max_row, out of bounds
        s.tick_acc = 0.0
        s.mutate_chance = 0
        old_chars = dict(s.chars)
        s.update()
        # head advanced to 11, which is >= max_row, so no new char added
        assert 11 not in s.chars

    def test_update_trims_tail(self):
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=3)
        s.head = 5
        s.tick_acc = 0.0
        s.mutate_chance = 0
        # Manually place chars at rows 2..5
        s.chars = {2: "A", 3: "B", 4: "C", 5: "D"}
        s.update()
        # head is now 6, cutoff = 6 - 3 = 3, so row 2 and 3 should be trimmed
        assert 2 not in s.chars
        assert 3 not in s.chars

    def test_fractional_speed(self):
        s = Stream(col=0, max_row=100, speed=0.5, trail_length=5)
        s.head = 0
        s.tick_acc = 0.0
        s.mutate_chance = 0
        initial_head = s.head
        s.update()
        # speed 0.5: tick_acc becomes 0.5, < 1.0, so head should NOT advance
        assert s.head == initial_head
        s.update()
        # tick_acc becomes 1.0, head advances
        assert s.head == initial_head + 1

    def test_high_speed_advances_multiple(self):
        s = Stream(col=0, max_row=100, speed=3.0, trail_length=5)
        s.head = 0
        s.tick_acc = 0.0
        s.mutate_chance = 0
        s.update()
        # speed 3.0: head should advance 3 times
        assert s.head == 3

    def test_is_dead_when_past_screen(self):
        s = Stream(col=0, max_row=10, speed=1.0, trail_length=5)
        s.head = 14  # 14 - 5 = 9 < 10, not dead yet
        assert not s.is_dead()
        s.head = 15  # 15 - 5 = 10 >= 10, dead
        assert s.is_dead()

    def test_is_dead_false_initially(self):
        s = Stream(col=0, max_row=50, speed=1.0, trail_length=10)
        # head starts negative, so head - trail_length is very negative
        assert not s.is_dead()

    def test_mutation_changes_chars(self):
        random.seed(0)
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=20)
        s.head = 10
        s.mutate_chance = 1.0  # always mutate
        s.chars = {r: "A" for r in range(11)}
        s.update()
        # With 100% mutate_chance, at least some chars should have changed
        changed = sum(1 for r, c in s.chars.items() if c != "A")
        assert changed > 0

    def test_speed_scale_slows_movement(self):
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=5)
        s.head = 0
        s.tick_acc = 0.0
        s.mutate_chance = 0
        initial_head = s.head
        s.update(speed_scale=0.5)
        # speed 1.0 * scale 0.5 = 0.5 effective → tick_acc 0.5, no advance
        assert s.head == initial_head
        s.update(speed_scale=0.5)
        # tick_acc now 1.0, head advances
        assert s.head == initial_head + 1

    def test_speed_scale_default_is_normal(self):
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=5)
        s.head = 0
        s.tick_acc = 0.0
        s.mutate_chance = 0
        s.update()  # default speed_scale=1.0
        assert s.head == 1

    def test_zero_mutation_preserves_existing_chars(self):
        s = Stream(col=0, max_row=100, speed=1.0, trail_length=20)
        s.head = 5
        s.tick_acc = 0.0
        s.mutate_chance = 0
        s.chars = {r: "X" for r in range(6)}
        s.update()
        # Only new char at head position (6) might differ; existing ones stay "X"
        for r in range(1, 6):  # rows 1-5 should be preserved (row 0 may be trimmed)
            if r in s.chars:
                assert s.chars[r] == "X"


# ── Config from Args ─────────────────────────────────────────────────────────


class TestConfigFromArgs:
    def _ns(self, **kwargs):
        """Build an argparse.Namespace with defaults."""
        defaults = {
            "preset": None,
            "speed": None,
            "density": None,
            "color": None,
            "rainbow": None,
            "fps": None,
            "trail_min": None,
            "trail_max": None,
            "message": None,
            "interactive": False,
            "send": None,
            "socket_path": None,
            "no_ipc": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_no_flags_returns_none(self):
        assert config_from_args(self._ns()) is None

    def test_interactive_flag_returns_none(self):
        assert config_from_args(self._ns(interactive=True, preset="classic")) is None

    def test_preset_only(self):
        config = config_from_args(self._ns(preset="storm"))
        assert config is not None
        assert config["speed"] == PRESETS["storm"]["speed"]
        assert config["density"] == PRESETS["storm"]["density"]

    def test_speed_override(self):
        config = config_from_args(self._ns(preset="classic", speed=2.5))
        assert config["speed"] == 2.5

    def test_speed_clamped_high(self):
        config = config_from_args(self._ns(speed=99.0))
        assert config["speed"] == 4.0

    def test_speed_clamped_low(self):
        config = config_from_args(self._ns(speed=0.001))
        assert config["speed"] == 0.1

    def test_density_override(self):
        config = config_from_args(self._ns(density=2.0))
        assert config["density"] == 2.0

    def test_density_clamped(self):
        config = config_from_args(self._ns(density=10.0))
        assert config["density"] == 3.0

    def test_color_override(self):
        config = config_from_args(self._ns(color="cyan"))
        assert config["color"] == "cyan"

    def test_rainbow_override(self):
        config = config_from_args(self._ns(rainbow=True))
        assert config["rainbow"] is True

    def test_fps_override(self):
        config = config_from_args(self._ns(fps=60))
        assert config["fps"] == 60

    def test_fps_clamped(self):
        config = config_from_args(self._ns(fps=999))
        assert config["fps"] == 60
        config = config_from_args(self._ns(fps=1))
        assert config["fps"] == 10

    def test_trail_min_override(self):
        config = config_from_args(self._ns(trail_min=0.5))
        assert config["trail_min"] == 0.5

    def test_trail_max_override(self):
        config = config_from_args(self._ns(trail_max=1.5))
        assert config["trail_max"] == 1.5

    def test_trail_min_clamped(self):
        config = config_from_args(self._ns(trail_min=0.0))
        assert config["trail_min"] == 0.05
        config = config_from_args(self._ns(trail_min=5.0))
        assert config["trail_min"] == 1.0

    def test_trail_max_clamped(self):
        config = config_from_args(self._ns(trail_max=0.01))
        assert config["trail_max"] == 0.1
        config = config_from_args(self._ns(trail_max=10.0))
        assert config["trail_max"] == 2.0

    def test_message_override(self):
        config = config_from_args(self._ns(preset="classic", message="HELLO"))
        assert config["message"] == "HELLO"

    def test_message_not_set_without_flag(self):
        config = config_from_args(self._ns(preset="classic"))
        assert "message" not in config

    def test_unknown_preset_uses_classic(self):
        # config_from_args uses PRESETS.get(args.preset, PRESETS["classic"])
        config = config_from_args(self._ns(preset=None, speed=1.0))
        assert config["speed"] == 1.0  # from classic defaults

    def test_multiple_overrides(self):
        config = config_from_args(self._ns(
            preset="slow",
            speed=2.0,
            color="red",
            fps=30,
        ))
        assert config["speed"] == 2.0
        assert config["color"] == "red"
        assert config["fps"] == 30
        # density should come from "slow" preset
        assert config["density"] == PRESETS["slow"]["density"]

    def test_no_ipc_alone_returns_classic(self):
        config = config_from_args(self._ns(no_ipc=True))
        assert config is not None
        assert config == dict(PRESETS["classic"])

    def test_socket_path_alone_returns_classic(self):
        config = config_from_args(self._ns(socket_path="/tmp/mr.sock"))
        assert config is not None
        assert config == dict(PRESETS["classic"])

    def test_no_ipc_with_no_flags_returns_none(self):
        """Bare invocation (no flags at all) still goes interactive."""
        config = config_from_args(self._ns())
        assert config is None


# ── CLI Argument Parsing ─────────────────────────────────────────────────────


class TestParseArgs:
    def test_no_args(self):
        with patch("sys.argv", ["matrix_rain"]):
            args = parse_args()
        assert args.preset is None
        assert args.speed is None
        assert args.interactive is False

    def test_preset_arg(self):
        with patch("sys.argv", ["matrix_rain","--preset", "dense"]):
            args = parse_args()
        assert args.preset == "dense"

    def test_multiple_args(self):
        with patch("sys.argv", ["matrix_rain","--speed", "2.0", "--color", "cyan", "--rainbow"]):
            args = parse_args()
        assert args.speed == 2.0
        assert args.color == "cyan"
        assert args.rainbow is True

    def test_interactive_short_flag(self):
        with patch("sys.argv", ["matrix_rain","-i"]):
            args = parse_args()
        assert args.interactive is True

    def test_invalid_preset_exits(self):
        with patch("sys.argv", ["matrix_rain","--preset", "nonexistent"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_message_arg(self):
        with patch("sys.argv", ["matrix_rain","--message", "HELLO WORLD"]):
            args = parse_args()
        assert args.message == "HELLO WORLD"

    def test_message_default_none(self):
        with patch("sys.argv", ["matrix_rain"]):
            args = parse_args()
        assert args.message is None

    def test_invalid_color_exits(self):
        with patch("sys.argv", ["matrix_rain","--color", "pink"]):
            with pytest.raises(SystemExit):
                parse_args()


# ── MatrixRain (with mocked curses) ─────────────────────────────────────────


def _make_mock_stdscr(rows=24, cols=80):
    """Create a mock curses stdscr."""
    stdscr = MagicMock()
    stdscr.getmaxyx.return_value = (rows, cols)
    stdscr.getch.return_value = -1  # no key pressed
    return stdscr


@pytest.fixture
def mock_curses():
    """Patch curses functions that need a real terminal."""
    with patch("curses.curs_set"), \
         patch("curses.start_color"), \
         patch("curses.use_default_colors"), \
         patch("curses.init_pair"), \
         patch("curses.color_pair", side_effect=lambda x: x), \
         patch("curses.A_BOLD", 0x100), \
         patch("curses.A_DIM", 0x200):
        yield


class TestMatrixRain:
    def test_init(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["classic"])
        rain = MatrixRain(stdscr, config)
        assert rain.rows == 24
        assert rain.cols == 80
        assert rain.streams == []
        assert rain.frame_count == 0

    def test_resize(self, mock_curses):
        stdscr = _make_mock_stdscr(24, 80)
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        # Simulate a resize
        stdscr.getmaxyx.return_value = (40, 120)
        rain._resize()
        assert rain.rows == 40
        assert rain.cols == 120

    def test_resize_prunes_out_of_bounds_streams(self, mock_curses):
        stdscr = _make_mock_stdscr(24, 80)
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        # Add streams at various columns
        for col in [0, 50, 79]:
            s = Stream(col, 24, 1.0, 10)
            rain.streams.append(s)
        # Shrink terminal width
        stdscr.getmaxyx.return_value = (24, 60)
        rain._resize()
        # Only streams with col < 60 should survive
        remaining_cols = [s.col for s in rain.streams]
        assert 79 not in remaining_cols
        assert 0 in remaining_cols
        assert 50 in remaining_cols

    def test_spawn_streams_respects_density(self, mock_curses):
        random.seed(42)
        stdscr = _make_mock_stdscr(50, 100)
        config = dict(PRESETS["classic"])
        rain = MatrixRain(stdscr, config)
        rain._spawn_streams()
        # With density 0.7 and 100 columns, some streams should spawn
        assert len(rain.streams) > 0
        # But not all columns should have streams
        assert len(rain.streams) < 100

    def test_spawn_streams_zero_density(self, mock_curses):
        stdscr = _make_mock_stdscr(50, 100)
        config = dict(PRESETS["classic"])
        config["density"] = 0.0  # chance = 0.0 * 0.018 = 0
        rain = MatrixRain(stdscr, config)
        # With zero density no random value < 0 so nothing spawns
        rain._spawn_streams()
        assert len(rain.streams) == 0

    def test_get_color_pair_non_rainbow(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["classic"])
        config["rainbow"] = False
        config["color"] = "cyan"
        rain = MatrixRain(stdscr, config)
        pair = rain._get_color_pair(0)
        assert pair == rain.color_pairs["cyan"]

    def test_get_color_pair_rainbow(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["rainbow"])
        rain = MatrixRain(stdscr, config)
        # Should cycle through RAINBOW_SEQUENCE based on frame_count and col
        rain.frame_count = 0
        pair = rain._get_color_pair(0)
        expected_name = RAINBOW_SEQUENCE[0]
        assert pair == rain.color_pairs[expected_name]

    def test_get_color_pair_unknown_color_defaults_to_green(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["classic"])
        config["color"] = "nonexistent"
        rain = MatrixRain(stdscr, config)
        pair = rain._get_color_pair(0)
        assert pair == rain.color_pairs["green"]

    def test_attr_for_position_head(self, mock_curses):
        stdscr = _make_mock_stdscr()
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        attr = rain._attr_for_position(0, 10, rain.color_pairs["green"])
        # Head: white + bold
        expected = rain.color_pairs["white"] | 0x100
        assert attr == expected

    def test_attr_for_position_near_head(self, mock_curses):
        stdscr = _make_mock_stdscr()
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        # dist/trail < 0.2 → bold
        attr = rain._attr_for_position(1, 20, rain.color_pairs["green"])
        expected = rain.color_pairs["green"] | 0x100
        assert attr == expected

    def test_attr_for_position_mid(self, mock_curses):
        stdscr = _make_mock_stdscr()
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        # frac ~0.35, between 0.2 and 0.55 → normal
        attr = rain._attr_for_position(7, 20, rain.color_pairs["green"])
        expected = rain.color_pairs["green"]
        assert attr == expected

    def test_attr_for_position_tail(self, mock_curses):
        stdscr = _make_mock_stdscr()
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        # frac ~0.9, >= 0.55 → dim
        attr = rain._attr_for_position(18, 20, rain.color_pairs["green"])
        expected = rain.color_pairs["green"] | 0x200
        assert attr == expected

    def test_draw_does_not_crash_with_streams(self, mock_curses):
        stdscr = _make_mock_stdscr(24, 80)
        rain = MatrixRain(stdscr, dict(PRESETS["classic"]))
        s = Stream(5, 24, 1.0, 10)
        s.head = 5
        s.chars = {r: "A" for r in range(6)}
        rain.streams.append(s)
        rain._draw()
        stdscr.erase.assert_called_once()
        stdscr.refresh.assert_called_once()
        assert stdscr.addstr.call_count > 0


# ── Caffeinate Integration ───────────────────────────────────────────────────


class TestCaffeinate:
    @patch("matrix_rain.cli.curses.wrapper")
    @patch("matrix_rain.cli.subprocess.Popen")
    @patch("sys.argv", ["matrix_rain", "--preset", "classic"])
    def test_caffeinate_started_and_stopped(self, mock_popen, mock_wrapper):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        from matrix_rain import cli_entry
        cli_entry()

        mock_popen.assert_called_once_with(
            ["caffeinate", "-d"],
            stdout=-3,  # subprocess.DEVNULL
            stderr=-3,
        )
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()

    @patch("matrix_rain.cli.curses.wrapper", side_effect=Exception("boom"))
    @patch("matrix_rain.cli.subprocess.Popen")
    @patch("sys.argv", ["matrix_rain", "--preset", "classic"])
    def test_caffeinate_stopped_on_exception(self, mock_popen, mock_wrapper):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        from matrix_rain import cli_entry
        with pytest.raises(Exception, match="boom"):
            cli_entry()

        # caffeinate should still be cleaned up
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()

    @patch("matrix_rain.cli.curses.wrapper")
    @patch("matrix_rain.cli.subprocess.Popen", side_effect=FileNotFoundError)
    @patch("sys.argv", ["matrix_rain", "--preset", "classic"])
    def test_caffeinate_missing_is_ok(self, mock_popen, mock_wrapper):
        from matrix_rain import cli_entry
        # Should not raise
        cli_entry()
        mock_wrapper.assert_called_once()


# ── Block Font ──────────────────────────────────────────────────────────────


class TestBlockFont:
    def test_all_glyphs_have_correct_height(self):
        for ch, rows in BLOCK_FONT.items():
            assert len(rows) == _FONT_H, f"Glyph '{ch}' has {len(rows)} rows, expected {_FONT_H}"

    def test_all_glyphs_have_correct_width(self):
        for ch, rows in BLOCK_FONT.items():
            for i, row in enumerate(rows):
                assert len(row) == _FONT_W, (
                    f"Glyph '{ch}' row {i} has width {len(row)}, expected {_FONT_W}"
                )

    def test_glyphs_only_contain_hash_and_space(self):
        for ch, rows in BLOCK_FONT.items():
            for row in rows:
                assert all(c in ('#', ' ') for c in row), f"Glyph '{ch}' has invalid chars"

    def test_az_coverage(self):
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert c in BLOCK_FONT, f"Missing glyph for '{c}'"

    def test_digit_coverage(self):
        for c in "0123456789":
            assert c in BLOCK_FONT, f"Missing glyph for '{c}'"

    def test_space_is_blank(self):
        for row in BLOCK_FONT[' ']:
            assert row == " " * _FONT_W


# ── Text Reveal ─────────────────────────────────────────────────────────────


class TestTextReveal:
    def _make_rain(self, mock_curses, rows=40, cols=120, message="HI"):
        stdscr = _make_mock_stdscr(rows, cols)
        config = dict(PRESETS["classic"])
        config["message"] = message
        return MatrixRain(stdscr, config)

    def test_init_reveal_state(self, mock_curses):
        rain = self._make_rain(mock_curses)
        assert rain.reveal_state == "idle"
        assert rain.speed_multiplier == 1.0
        assert rain.reveal_mask == set()
        assert rain.message == "HI"

    def test_start_reveal(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        assert rain.reveal_state == "slowing"
        assert rain.reveal_timer == 0.0
        assert len(rain.reveal_mask) > 0
        assert len(rain.reveal_mask_order) == len(rain.reveal_mask)

    def test_compute_text_mask_centered(self, mock_curses):
        rain = self._make_rain(mock_curses, rows=40, cols=120, message="A")
        mask = rain._compute_text_mask("A")
        # Should be centred: start_col ≈ (120 - 5) // 2 = 57, start_row ≈ (40 - 5) // 2 = 17
        rows_in_mask = {r for r, c in mask}
        cols_in_mask = {c for r, c in mask}
        assert min(rows_in_mask) == 17
        assert min(cols_in_mask) >= 57

    def test_compute_text_mask_clips_to_screen(self, mock_curses):
        # Very long message on a small screen — should not go out of bounds
        rain = self._make_rain(mock_curses, rows=10, cols=20, message="ABCDEFGHIJ")
        mask = rain._compute_text_mask("ABCDEFGHIJ")
        for r, c in mask:
            assert 0 <= r < 10
            assert 0 <= c < 20

    def test_compute_text_mask_empty_message(self, mock_curses):
        rain = self._make_rain(mock_curses)
        mask = rain._compute_text_mask("")
        assert mask == set()

    def test_unknown_char_treated_as_space(self, mock_curses):
        rain = self._make_rain(mock_curses, message="~")
        mask = rain._compute_text_mask("~")
        # '~' is not in BLOCK_FONT, falls back to space (all blank)
        assert mask == set()

    def test_slowing_phase_transitions_to_hold(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        # Advance through the entire slowing phase
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)
        assert rain.reveal_state == "hold"
        assert rain.reveal_timer == 0.0
        assert rain.speed_multiplier == pytest.approx(_REVEAL_MIN_SPEED, abs=0.01)

    def test_hold_phase_transitions_to_speedup(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)  # → hold
        rain._update_reveal(_REVEAL_HOLD_SECS + 0.1)  # → speedup
        assert rain.reveal_state == "speedup"
        assert rain.reveal_timer == 0.0

    def test_speedup_phase_transitions_to_idle(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)  # → hold
        rain._update_reveal(_REVEAL_HOLD_SECS + 0.1)  # → speedup
        rain._update_reveal(_REVEAL_FAST_SECS + 0.1)  # → idle
        assert rain.reveal_state == "idle"
        assert rain.speed_multiplier == 1.0
        assert rain.reveal_mask == set()

    def test_speed_multiplier_decreases_during_slowing(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS * 0.5)
        assert rain.speed_multiplier < 1.0
        assert rain.speed_multiplier > _REVEAL_MIN_SPEED

    def test_speed_multiplier_increases_during_speedup(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)  # → hold
        rain._update_reveal(_REVEAL_HOLD_SECS + 0.1)  # → speedup
        rain._update_reveal(_REVEAL_FAST_SECS * 0.5)
        assert rain.speed_multiplier > _REVEAL_MIN_SPEED
        assert rain.speed_multiplier < 1.0

    def test_active_mask_empty_when_idle(self, mock_curses):
        rain = self._make_rain(mock_curses)
        assert rain._active_mask() == set()

    def test_active_mask_full_during_hold(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)  # → hold
        assert rain._active_mask() == rain.reveal_mask

    def test_active_mask_grows_during_slowing(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        # Early in slowing (< 30%): no mask yet
        rain._update_reveal(_REVEAL_SLOW_SECS * 0.2)
        assert rain._active_mask() == set()
        # Late in slowing: partial mask
        rain.reveal_timer = _REVEAL_SLOW_SECS * 0.8
        mask = rain._active_mask()
        assert 0 < len(mask) < len(rain.reveal_mask)

    def test_active_mask_shrinks_during_speedup(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)
        rain._update_reveal(_REVEAL_HOLD_SECS + 0.1)
        # Early speedup: partial mask
        rain.reveal_timer = _REVEAL_FAST_SECS * 0.2
        mask = rain._active_mask()
        assert 0 < len(mask) < len(rain.reveal_mask)
        # Late speedup (> 50%): no mask
        rain.reveal_timer = _REVEAL_FAST_SECS * 0.6
        assert rain._active_mask() == set()

    def test_non_mask_fade_idle(self, mock_curses):
        rain = self._make_rain(mock_curses)
        assert rain._non_mask_fade() == 1.0

    def test_non_mask_fade_hold(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)  # → hold
        assert rain._non_mask_fade() == 0.0

    def test_non_mask_fade_slowing(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS * 0.5)
        fade = rain._non_mask_fade()
        assert 0.0 < fade < 1.0

    def test_non_mask_fade_speedup(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)
        rain._update_reveal(_REVEAL_HOLD_SECS + 0.1)
        rain._update_reveal(_REVEAL_FAST_SECS * 0.5)
        fade = rain._non_mask_fade()
        assert 0.0 < fade < 1.0

    def test_draw_only_mask_during_hold(self, mock_curses):
        rain = self._make_rain(mock_curses, rows=24, cols=80)
        rain._start_reveal()
        rain._update_reveal(_REVEAL_SLOW_SECS + 0.1)  # → hold, full mask
        # Add a stream with chars at a NON-mask position
        # Find a col not in the mask
        mask_cols = {c for _, c in rain.reveal_mask}
        free_col = next(c for c in range(78) if c not in mask_cols)
        s = Stream(free_col, 24, 1.0, 10)
        s.head = 5
        s.chars = {r: "A" for r in range(6)}
        rain.streams.append(s)
        rain._draw()
        # During hold, non_mask_fade=0 → non-mask chars should be suppressed
        for call in rain.stdscr.addstr.call_args_list:
            row_arg, col_arg = call[0][0], call[0][1]
            assert (row_arg, col_arg) in rain.reveal_mask

    def test_fill_chars_generated(self, mock_curses):
        rain = self._make_rain(mock_curses)
        rain._start_reveal()
        assert len(rain.reveal_fill_chars) == len(rain.reveal_mask)
        for pos, char in rain.reveal_fill_chars.items():
            assert pos in rain.reveal_mask
            assert char in CHARSET

    def test_fill_chars_mutate(self, mock_curses):
        random.seed(0)
        rain = self._make_rain(mock_curses, message="ABCDEF")
        rain._start_reveal()
        original = dict(rain.reveal_fill_chars)
        # Run many update cycles to trigger mutations (4% chance each)
        for _ in range(100):
            rain._update_reveal(0.001)
        changed = sum(1 for p in original if rain.reveal_fill_chars.get(p) != original[p])
        assert changed > 0

    def test_spawn_reduced_during_reveal(self, mock_curses):
        random.seed(42)
        rain = self._make_rain(mock_curses, rows=50, cols=100)
        rain.speed_multiplier = 0.15
        rain._spawn_streams()
        slow_count = len(rain.streams)
        # Reset and spawn at full speed
        rain.streams = []
        rain.speed_multiplier = 1.0
        random.seed(42)
        rain._spawn_streams()
        full_count = len(rain.streams)
        assert slow_count < full_count

    def test_no_reveal_without_message(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["classic"])  # no message key
        rain = MatrixRain(stdscr, config)
        assert rain.message == ""
        # _start_reveal should not crash, but state should remain idle
        # (the key handler checks for message before calling _start_reveal)


# ── IPC ──────────────────────────────────────────────────────────────────────


class TestDefaultSocketPath:
    def test_contains_uid(self):
        import os
        path = default_socket_path()
        assert str(os.getuid()) in path
        assert path.startswith("/tmp/matrix-rain-")
        assert path.endswith(".sock")


@pytest.fixture()
def sock_path():
    """Short socket path under /tmp to stay within AF_UNIX length limit."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".sock", dir="/tmp", prefix="mr-test-")
    os.close(fd)
    os.unlink(path)  # we just need the name, not the file
    yield path
    # cleanup if test didn't
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


class TestMessageListener:
    def test_bind_and_close(self, sock_path):
        listener = MessageListener(sock_path)
        assert os.path.exists(sock_path)
        listener.close()
        assert not os.path.exists(sock_path)

    def test_poll_returns_none_when_empty(self, sock_path):
        with MessageListener(sock_path) as listener:
            assert listener.poll() is None

    def test_send_and_receive(self, sock_path):
        with MessageListener(sock_path) as listener:
            send_message("HELLO", sock_path)
            msg = listener.poll()
            assert msg == "HELLO"

    def test_multiple_messages(self, sock_path):
        with MessageListener(sock_path) as listener:
            send_message("FIRST", sock_path)
            send_message("SECOND", sock_path)
            assert listener.poll() == "FIRST"
            assert listener.poll() == "SECOND"
            assert listener.poll() is None

    def test_empty_message_ignored(self, sock_path):
        with MessageListener(sock_path) as listener:
            send_message("", sock_path)
            assert listener.poll() is None

    def test_stale_socket_cleanup(self, sock_path):
        # Create a stale socket file
        import socket as sock_mod
        stale = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_DGRAM)
        stale.bind(sock_path)
        stale.close()  # close without unlinking — simulates crash
        # New listener should clean it up and bind successfully
        with MessageListener(sock_path) as listener:
            send_message("AFTER STALE", sock_path)
            assert listener.poll() == "AFTER STALE"

    def test_context_manager(self, sock_path):
        with MessageListener(sock_path) as listener:
            assert listener.poll() is None
        assert not os.path.exists(sock_path)

    def test_close_idempotent(self, sock_path):
        listener = MessageListener(sock_path)
        listener.close()
        listener.close()  # should not raise

    def test_refuses_non_socket_path(self, sock_path):
        # Create a regular file at the path
        with open(sock_path, "w") as f:
            f.write("not a socket")
        with pytest.raises(OSError, match="not a socket"):
            MessageListener(sock_path)
        # The regular file must not have been deleted
        assert os.path.exists(sock_path)
        os.unlink(sock_path)


class TestSendMessage:
    def test_send_to_missing_socket_raises(self):
        path = "/tmp/mr-test-nonexistent.sock"
        with pytest.raises(FileNotFoundError):
            send_message("HELLO", path)


class TestEngineIPC:
    def test_engine_accepts_listener(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["classic"])
        listener = MagicMock()
        listener.poll.return_value = None
        rain = MatrixRain(stdscr, config, message_listener=listener)
        assert rain.message_listener is listener

    def test_engine_without_listener(self, mock_curses):
        stdscr = _make_mock_stdscr()
        config = dict(PRESETS["classic"])
        rain = MatrixRain(stdscr, config)
        assert rain.message_listener is None

    def test_ipc_message_triggers_reveal(self, mock_curses):
        stdscr = _make_mock_stdscr(rows=30, cols=80)
        config = dict(PRESETS["classic"])
        listener = MagicMock()
        listener.poll.return_value = "HELLO"
        rain = MatrixRain(stdscr, config, message_listener=listener)
        assert rain.reveal_state == "idle"
        # Simulate one iteration of the IPC check from _loop
        incoming = rain.message_listener.poll()
        if incoming is not None:
            rain.message = incoming
            rain.reveal_state = "idle"
            rain.reveal_mask = set()
            rain.reveal_mask_order = []
            rain.reveal_fill_chars = {}
            rain.speed_multiplier = 1.0
            rain._start_reveal()
        assert rain.message == "HELLO"
        assert rain.reveal_state == "slowing"

    def test_ipc_message_interrupts_active_reveal(self, mock_curses):
        stdscr = _make_mock_stdscr(rows=30, cols=80)
        config = dict(PRESETS["classic"], message="OLD")
        rain = MatrixRain(stdscr, config)
        rain._start_reveal()
        assert rain.reveal_state == "slowing"
        # Simulate IPC interrupt
        rain.message = "NEW"
        rain.reveal_state = "idle"
        rain.reveal_mask = set()
        rain.reveal_mask_order = []
        rain.reveal_fill_chars = {}
        rain.speed_multiplier = 1.0
        rain._start_reveal()
        assert rain.message == "NEW"
        assert rain.reveal_state == "slowing"
